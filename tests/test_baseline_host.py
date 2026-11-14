"""Preflight facts about the host and the server process."""

import subprocess
from pathlib import Path

import pytest
from baseline import host


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def fake_proc(root: Path, load: str = "0.10 0.20 0.30 1/100 1") -> Path:
    write(root / "uptime", "540.25 2000.00\n")
    write(root / "loadavg", f"{load}\n")
    write(
        root / "meminfo",
        "MemTotal: 64000000 kB\nMemAvailable: 60000000 kB\nCached: 2000000 kB\n"
        "SwapTotal: 8000000 kB\nSwapFree: 8000000 kB\n",
    )
    return root


def fake_gpu(root: Path, busy: str = "0") -> Path:
    write(root / "gpu_busy_percent", f"{busy}\n")
    write(root / "mem_info_vram_used", "1000\n")
    write(root / "mem_info_vram_total", "17000000000\n")
    write(root / "hwmon" / "hwmon1" / "power1_average", "7000000\n")
    write(root / "hwmon" / "hwmon1" / "temp1_input", "28000\n")
    return root


def test_boot_state_records_uptime_load_memory_and_idle_gpu(tmp_path: Path) -> None:
    state = host.boot_state(fake_proc(tmp_path / "proc"), fake_gpu(tmp_path / "gpu"))

    metrics = {name: metric["value"] for name, metric in state["metrics"].items()}
    assert metrics["uptime_s"] == 540.25
    assert metrics["load_1m"] == 0.1
    assert metrics["mem_total_gib"] == pytest.approx(64_000_000 / 1024 / 1024)
    assert metrics["mem_used_gib"] == pytest.approx(4_000_000 / 1024 / 1024)
    assert metrics["swap_total_gib"] == pytest.approx(8_000_000 / 1024 / 1024)
    assert metrics["gpu_vram_total_gib"] == pytest.approx(17_000_000_000 / 1024**3)
    assert "mem_available_gib" not in metrics
    assert metrics["gpu_busy_percent"] == 0
    assert metrics["gpu_temp_c"] == 28
    assert state["warnings"] == []


def test_boot_state_warns_when_the_gpu_is_busy_at_start(tmp_path: Path) -> None:
    gpu = fake_gpu(tmp_path / "gpu", busy="40")

    state = host.boot_state(fake_proc(tmp_path / "proc"), gpu)

    assert any("GPU" in warning for warning in state["warnings"])


def test_boot_state_records_but_does_not_warn_on_load_that_follows_a_server_start(
    tmp_path: Path,
) -> None:
    proc = fake_proc(tmp_path / "proc", load="3.50 2.00 1.00 1/100 1")

    state = host.boot_state(proc, fake_gpu(tmp_path / "gpu"))

    assert state["metrics"]["load_1m"]["value"] == 3.5
    assert state["warnings"] == []


def test_boot_state_marks_unreadable_sensor_unavailable_without_failing(tmp_path: Path) -> None:
    gpu = fake_gpu(tmp_path / "gpu")
    (gpu / "gpu_busy_percent").unlink()

    state = host.boot_state(fake_proc(tmp_path / "proc"), gpu)

    assert state["metrics"]["gpu_busy_percent"]["value"] is None
    assert "unavailable" in state["metrics"]["gpu_busy_percent"]


def test_boot_state_without_gpu_still_reports_host_metrics(tmp_path: Path) -> None:
    state = host.boot_state(fake_proc(tmp_path / "proc"), None)

    assert state["metrics"]["uptime_s"]["value"] == 540.25
    assert "gpu_busy_percent" not in state["metrics"]


def test_cgroup_path_of_reads_unified_hierarchy(tmp_path: Path) -> None:
    write(tmp_path / "proc" / "42" / "cgroup", "0::/system.slice/docker-abc.scope\n")

    path = host.cgroup_path_of(42, tmp_path / "proc", tmp_path / "cg")

    assert path == tmp_path / "cg" / "system.slice" / "docker-abc.scope"


def test_cgroup_path_of_rejects_legacy_hierarchy(tmp_path: Path) -> None:
    write(tmp_path / "proc" / "42" / "cgroup", "12:memory:/docker/abc\n")

    with pytest.raises(host.HostError, match="cgroup v2"):
        host.cgroup_path_of(42, tmp_path / "proc", tmp_path / "cg")


def completed(output: str, code: int = 0, error: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, output, error)


def test_resolve_container_finds_instance_by_launcher_labels(tmp_path: Path) -> None:
    write(tmp_path / "proc" / "77" / "cgroup", "0::/system.slice/docker-abc.scope\n")
    commands: list[list[str]] = []

    def run(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if "ps" in command:
            return completed("abc123\n")
        return completed("77 sha256:deadbeef repo/image:tag\n")

    info = host.resolve_container("coding", run, tmp_path / "proc", tmp_path / "cg")

    assert (info.container_id, info.pid, info.image_id, info.image) == (
        "abc123",
        77,
        "sha256:deadbeef",
        "repo/image:tag",
    )
    assert info.cgroup == tmp_path / "cg" / "system.slice" / "docker-abc.scope"
    assert "label=io.llm-recipes.instance=coding" in commands[0]
    assert commands[0][:3] == ["sudo", "-n", "docker"]


def test_resolve_container_reports_missing_instance(tmp_path: Path) -> None:
    with pytest.raises(host.HostError, match="No running instance 'coding'"):
        host.resolve_container("coding", lambda command: completed(""), tmp_path, tmp_path)


def test_resolve_container_reports_docker_failure_with_remedy(tmp_path: Path) -> None:
    def run(command: list[str]) -> subprocess.CompletedProcess[str]:
        return completed("", 1, "sudo: a password is required")

    with pytest.raises(host.HostError, match="sudo -v"):
        host.resolve_container("coding", run, tmp_path, tmp_path)


def test_repository_revision_reports_commit_and_dirty_state() -> None:
    def run(command: list[str]) -> subprocess.CompletedProcess[str]:
        if "rev-parse" in command:
            return completed("abc123\n")
        return completed(" M file.py\n")

    assert host.repository_revision(Path("."), run) == {"commit": "abc123", "dirty": True}


def test_repository_revision_is_none_outside_a_repository() -> None:
    assert host.repository_revision(Path("."), lambda command: completed("", 128)) is None


def test_file_sha256_hashes_content(tmp_path: Path) -> None:
    path = tmp_path / "f"
    path.write_bytes(b"abc")

    assert (
        host.file_sha256(path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
