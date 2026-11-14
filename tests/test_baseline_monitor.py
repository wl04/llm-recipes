"""Assembling telemetry sources for a container or a desktop server process."""

from pathlib import Path

import pytest
from baseline import monitor
from baseline.sources import SourceError
from test_baseline_sources import fake_top, make_cgroup, make_gpu, make_process, wait_for


def names(monitoring: monitor.Monitoring) -> list[str]:
    return [source.name for source in monitoring.sources]


def test_container_target_reads_cgroup_memory_and_cpu(tmp_path: Path) -> None:
    cgroup = make_cgroup(tmp_path / "cg")

    monitoring = monitor.build_monitoring(
        cgroup=cgroup, pid=None, gpu_address=None, interval_ms=500, proc=tmp_path / "proc"
    )

    assert names(monitoring) == ["system", "cgroup"]
    assert monitoring.target["memory_key"] == "mem_bytes"
    assert "cgroup" in monitoring.target["memory_label"]
    assert monitoring.target["cpu_label"] == "cgroup cpu.stat"


def test_process_target_prefers_pss_when_readable(tmp_path: Path) -> None:
    make_process(tmp_path / "proc", 10, 1, cpu_ticks=1, start=5, pages=10)

    monitoring = monitor.build_monitoring(
        cgroup=None, pid=10, gpu_address=None, interval_ms=500, proc=tmp_path / "proc"
    )

    assert names(monitoring) == ["system", "process", "process-pss"]
    assert monitoring.target["memory_key"] == "mem_pss_bytes"
    assert "PSS" in monitoring.target["memory_label"]


def test_process_target_falls_back_to_rss_and_says_so(tmp_path: Path) -> None:
    make_process(tmp_path / "proc", 10, 1, cpu_ticks=1, start=5, pages=10)
    (tmp_path / "proc" / "10" / "smaps_rollup").unlink()

    monitoring = monitor.build_monitoring(
        cgroup=None, pid=10, gpu_address=None, interval_ms=500, proc=tmp_path / "proc"
    )

    assert names(monitoring) == ["system", "process"]
    assert monitoring.target["memory_key"] == "mem_rss_bytes"
    assert "RSS" in monitoring.target["memory_label"]


def test_process_target_rejects_missing_process(tmp_path: Path) -> None:
    (tmp_path / "proc").mkdir()

    with pytest.raises(SourceError, match="process 10"):
        monitor.build_monitoring(
            cgroup=None, pid=10, gpu_address=None, interval_ms=500, proc=tmp_path / "proc"
        )


def test_gpu_address_adds_device_sensors(tmp_path: Path) -> None:
    make_gpu(tmp_path / "pci", "0000:03:00.0")

    monitoring = monitor.build_monitoring(
        cgroup=None,
        pid=None,
        gpu_address="0000:03:00.0",
        interval_ms=500,
        proc=tmp_path,
        pci_root=tmp_path / "pci",
    )

    assert names(monitoring) == ["system", "gpu"]


def test_without_target_memory_is_left_unattributed(tmp_path: Path) -> None:
    monitoring = monitor.build_monitoring(
        cgroup=None, pid=None, gpu_address=None, interval_ms=500, proc=tmp_path
    )

    assert names(monitoring) == ["system"]
    assert monitoring.target["memory_label"] == "no server process selected"


def test_process_vram_comes_from_amdgpu_top_and_cleanup_stops_it(tmp_path: Path) -> None:
    make_gpu(tmp_path / "pci", "0000:03:00.0")
    make_process(tmp_path / "proc", 4242, 1, cpu_ticks=1, start=5, pages=10)

    monitoring = monitor.build_monitoring(
        cgroup=None,
        pid=4242,
        gpu_address="0000:03:00.0",
        interval_ms=100,
        proc=tmp_path / "proc",
        pci_root=tmp_path / "pci",
        top_executable=fake_top(tmp_path),
    )
    try:
        source = next(s for s in monitoring.sources if s.name == "process-vram")
        wait_for(lambda: "proc_vram_bytes" in source.read().values)

        assert source.read().values["proc_vram_bytes"] == 7 * 1048576
    finally:
        monitoring.cleanup()


def test_cleanup_is_safe_without_amdgpu_top(tmp_path: Path) -> None:
    monitoring = monitor.build_monitoring(
        cgroup=None, pid=None, gpu_address=None, interval_ms=500, proc=tmp_path
    )

    monitoring.cleanup()
    monitoring.cleanup()
