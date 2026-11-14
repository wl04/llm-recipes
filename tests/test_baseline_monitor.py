"""Assembling telemetry sources for a server running in a cgroup."""

from pathlib import Path

from baseline import monitor
from test_baseline_sources import make_cgroup, make_drm_client, make_gpu


def names(monitoring: monitor.Monitoring) -> list[str]:
    return [source.name for source in monitoring.sources]


def test_cgroup_target_reads_cgroup_memory_and_cpu(tmp_path: Path) -> None:
    cgroup = make_cgroup(tmp_path / "cg")

    monitoring = monitor.build_monitoring(cgroup=cgroup, gpu_address=None, proc=tmp_path / "proc")

    assert names(monitoring) == ["system", "cgroup"]
    assert monitoring.target["memory_key"] == "mem_bytes"
    assert "cgroup" in monitoring.target["memory_label"]
    assert monitoring.target["cpu_label"] == "cgroup cpu.stat"


def test_without_target_memory_is_left_unattributed(tmp_path: Path) -> None:
    monitoring = monitor.build_monitoring(cgroup=None, gpu_address=None, proc=tmp_path)

    assert names(monitoring) == ["system"]
    assert monitoring.target["memory_label"] == "no server selected"


def test_gpu_address_adds_device_sensors(tmp_path: Path) -> None:
    make_gpu(tmp_path / "pci", "0000:03:00.0")

    monitoring = monitor.build_monitoring(
        cgroup=None, gpu_address="0000:03:00.0", proc=tmp_path, pci_root=tmp_path / "pci"
    )

    assert names(monitoring) == ["system", "gpu"]


def test_server_vram_is_read_from_fdinfo_of_the_cgroup_members(tmp_path: Path) -> None:
    gpu = "0000:03:00.0"
    cgroup = make_cgroup(tmp_path / "cg")
    (cgroup / "cgroup.procs").write_text("4242\n")
    make_gpu(tmp_path / "pci", gpu)
    make_drm_client(tmp_path / "proc", 4242, 3, pdev=gpu, client=9, vram="7 MiB")
    make_drm_client(tmp_path / "proc", 1, 3, pdev=gpu, client=8, vram="500 MiB")

    monitoring = monitor.build_monitoring(
        cgroup=cgroup, gpu_address=gpu, proc=tmp_path / "proc", pci_root=tmp_path / "pci"
    )

    source = next(s for s in monitoring.sources if s.name == "process-vram")
    assert source.read().values == {"proc_vram_bytes": 7 * 1048576}


def test_server_vram_follows_processes_that_join_the_cgroup_later(tmp_path: Path) -> None:
    gpu = "0000:03:00.0"
    cgroup = make_cgroup(tmp_path / "cg")
    (cgroup / "cgroup.procs").write_text("")
    make_drm_client(tmp_path / "proc", 4242, 3, pdev=gpu, client=9, vram="7 MiB")
    monitoring = monitor.build_monitoring(
        cgroup=cgroup, gpu_address=gpu, proc=tmp_path / "proc", pci_root=tmp_path
    )
    source = next(s for s in monitoring.sources if s.name == "process-vram")
    assert "no server processes" in source.read().errors["proc_vram_bytes"]

    (cgroup / "cgroup.procs").write_text("4242\n")

    assert source.read().values == {"proc_vram_bytes": 7 * 1048576}


def test_target_sources_add_cgroup_and_server_vram_to_a_running_monitor(tmp_path: Path) -> None:
    gpu = "0000:03:00.0"
    cgroup = make_cgroup(tmp_path / "cg")
    (cgroup / "cgroup.procs").write_text("4242\n")
    make_drm_client(tmp_path / "proc", 4242, 3, pdev=gpu, client=9, vram="7 MiB")

    added, target = monitor.target_sources(cgroup, gpu, proc=tmp_path / "proc")

    assert [source.name for source in added] == ["cgroup", "process-vram"]
    assert target == {
        "memory_key": "mem_bytes",
        "memory_label": "cgroup memory.current",
        "cpu_label": "cgroup cpu.stat",
    }


def test_target_sources_without_gpu_has_only_the_cgroup(tmp_path: Path) -> None:
    added, _ = monitor.target_sources(make_cgroup(tmp_path / "cg"), None)

    assert [source.name for source in added] == ["cgroup"]
