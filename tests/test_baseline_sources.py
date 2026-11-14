"""Telemetry readers over fake /proc, /sys, and cgroup trees."""

import json
import stat
import sys
import time
from pathlib import Path

import pytest
from baseline import sources


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def make_cgroup(root: Path, *, swap: bool = True) -> Path:
    cgroup = root / "docker-abc.scope"
    write(cgroup / "cpu.stat", "usage_usec 2500000\nuser_usec 2000000\nsystem_usec 500000\n")
    write(cgroup / "memory.current", "4096000\n")
    write(cgroup / "memory.stat", "anon 3000000\nfile 1000000\nkernel 96000\n")
    if swap:
        write(cgroup / "memory.swap.current", "2048\n")
    return cgroup


def make_process(proc: Path, pid: int, ppid: int, cpu_ticks: int, start: int, pages: int) -> None:
    fields = ["S", str(ppid)] + ["0"] * 9 + [str(cpu_ticks), "0"] + ["0"] * 6 + [str(start)]
    write(proc / str(pid) / "stat", f"{pid} (my proc) " + " ".join(fields) + " 0 0\n")
    write(proc / str(pid) / "statm", f"1000 {pages} 0 0 0 0 0\n")
    write(proc / str(pid) / "smaps_rollup", f"Rss: {pages * 4} kB\nPss: {pages * 2} kB\n")


def test_read_cgroup_returns_values(tmp_path: Path) -> None:
    reading = sources.read_cgroup(make_cgroup(tmp_path))

    assert reading.values == {
        "cpu_usec": 2500000,
        "mem_bytes": 4096000,
        "mem_anon_bytes": 3000000,
        "mem_file_bytes": 1000000,
        "swap_bytes": 2048,
    }
    assert reading.errors == {}


def test_read_cgroup_reports_missing_swap_accounting_as_error_not_zero(tmp_path: Path) -> None:
    reading = sources.read_cgroup(make_cgroup(tmp_path, swap=False))

    assert "swap_bytes" not in reading.values
    assert "memory.swap.current" in reading.errors["swap_bytes"]
    assert reading.values["cpu_usec"] == 2500000


def test_read_cgroup_reports_every_key_when_directory_is_gone(tmp_path: Path) -> None:
    reading = sources.read_cgroup(tmp_path / "missing")

    assert reading.values == {}
    assert set(reading.errors) == set(sources.CGROUP_KEYS)


def test_process_tree_sums_cpu_and_rss_over_descendants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sources, "PAGE_SIZE", 4096)
    monkeypatch.setattr(sources, "CLOCK_TICKS", 100)
    make_process(tmp_path, 10, 1, cpu_ticks=100, start=5, pages=100)
    make_process(tmp_path, 11, 10, cpu_ticks=50, start=6, pages=50)
    make_process(tmp_path, 12, 11, cpu_ticks=25, start=7, pages=25)
    make_process(tmp_path, 99, 1, cpu_ticks=999, start=8, pages=999)
    tree = sources.ProcessTree(10, proc=tmp_path)

    reading = tree.read_basic()

    assert reading.values["cpu_usec"] == 1_750_000
    assert reading.values["mem_rss_bytes"] == 175 * 4096
    assert tree.pids() == {10, 11, 12}


def test_process_tree_reads_pss_when_smaps_rollup_is_readable(tmp_path: Path) -> None:
    make_process(tmp_path, 10, 1, cpu_ticks=1, start=5, pages=100)
    make_process(tmp_path, 11, 10, cpu_ticks=1, start=6, pages=50)

    reading = sources.ProcessTree(10, proc=tmp_path).read_pss()

    assert reading.values["mem_pss_bytes"] == (200 + 100) * 1024


def test_process_tree_reports_unreadable_pss_as_error(tmp_path: Path) -> None:
    make_process(tmp_path, 10, 1, cpu_ticks=1, start=5, pages=100)
    (tmp_path / "10" / "smaps_rollup").unlink()

    reading = sources.ProcessTree(10, proc=tmp_path).read_pss()

    assert reading.values == {}
    assert "smaps_rollup" in reading.errors["mem_pss_bytes"]


def test_process_tree_rejects_reused_pid(tmp_path: Path) -> None:
    make_process(tmp_path, 10, 1, cpu_ticks=1, start=5, pages=1)
    tree = sources.ProcessTree(10, proc=tmp_path)
    make_process(tmp_path, 10, 1, cpu_ticks=1, start=77, pages=1)

    reading = tree.read_basic()

    assert reading.values == {}
    assert "restarted" in reading.errors["cpu_usec"]


def test_process_tree_reports_exited_process(tmp_path: Path) -> None:
    make_process(tmp_path, 10, 1, cpu_ticks=1, start=5, pages=1)
    tree = sources.ProcessTree(10, proc=tmp_path)
    for name in ("stat", "statm", "smaps_rollup"):
        (tmp_path / "10" / name).unlink()

    reading = tree.read_basic()

    assert "cpu_usec" in reading.errors


def test_read_system_reports_memory_swap_and_swap_activity(tmp_path: Path) -> None:
    write(
        tmp_path / "meminfo",
        "MemTotal: 1000 kB\nMemAvailable: 400 kB\nSwapTotal: 200 kB\nSwapFree: 150 kB\n",
    )
    write(tmp_path / "vmstat", "nr_free 1\npswpin 7\npswpout 9\n")

    reading = sources.read_system(tmp_path)

    assert reading.values == {
        "sys_available_bytes": 400 * 1024,
        "sys_used_bytes": 600 * 1024,
        "sys_swap_used_bytes": 50 * 1024,
        "pswpin": 7,
        "pswpout": 9,
    }


def make_gpu(root: Path, address: str = "0000:03:00.0", vram_total: int = 17_000_000_000) -> Path:
    device = root / address
    write(device / "vendor", "0x1002\n")
    write(device / "gpu_busy_percent", "37\n")
    write(device / "mem_info_vram_used", "1000\n")
    write(device / "mem_info_vram_total", f"{vram_total}\n")
    write(device / "mem_info_gtt_used", "2000\n")
    write(device / "hwmon" / "hwmon3" / "power1_average", "36000000\n")
    write(device / "hwmon" / "hwmon3" / "temp1_input", "41000\n")
    return device


def test_read_gpu_reads_load_memory_power_and_temperature(tmp_path: Path) -> None:
    reading = sources.read_gpu(make_gpu(tmp_path))

    assert reading.values == {
        "gpu_busy_percent": 37,
        "vram_bytes": 1000,
        "gtt_bytes": 2000,
        "gpu_power_uw": 36_000_000,
        "gpu_temp_mc": 41_000,
    }


def test_read_gpu_reports_missing_sensor_without_inventing_zero(tmp_path: Path) -> None:
    device = make_gpu(tmp_path)
    (device / "hwmon" / "hwmon3" / "power1_average").unlink()

    reading = sources.read_gpu(device)

    assert "gpu_power_uw" not in reading.values
    assert "power1_average" in reading.errors["gpu_power_uw"]
    assert reading.values["vram_bytes"] == 1000


def test_find_gpu_prefers_the_device_with_most_vram_and_lists_candidates(tmp_path: Path) -> None:
    make_gpu(tmp_path, "0000:12:00.0", vram_total=500_000_000)
    make_gpu(tmp_path, "0000:03:00.0", vram_total=17_000_000_000)
    write(tmp_path / "0000:00:1f.0" / "vendor", "0x8086\n")

    address, candidates = sources.find_gpu(tmp_path)

    assert address == "0000:03:00.0"
    assert candidates == ["0000:03:00.0", "0000:12:00.0"]


def test_find_gpu_rejects_machine_without_amd_gpu(tmp_path: Path) -> None:
    write(tmp_path / "0000:00:1f.0" / "vendor", "0x8086\n")

    with pytest.raises(sources.SourceError, match="AMD GPU"):
        sources.find_gpu(tmp_path)


def test_parse_top_line_sums_process_vram_per_pid_in_bytes() -> None:
    line = json.dumps(
        {
            "devices": [
                {
                    "fdinfo": {
                        "100": {
                            "name": "a",
                            "usage": {"name": "a", "usage": {"VRAM": {"unit": "MiB", "value": 2}}},
                        },
                        "200": {
                            "name": "b",
                            "usage": {"name": "b", "usage": {"VRAM": {"unit": "MiB", "value": 5}}},
                        },
                        "300": {"name": "c", "usage": {"name": "c", "usage": {"VRAM": None}}},
                    }
                }
            ]
        }
    )

    assert sources.parse_top_line(line) == {100: 2 * 1048576, 200: 5 * 1048576}


@pytest.mark.parametrize("line", ["not json", "{}", '{"devices": []}'])
def test_parse_top_line_rejects_unexpected_output(line: str) -> None:
    with pytest.raises(sources.SourceError):
        sources.parse_top_line(line)


FAKE_TOP = """#!{python}
import json, sys, time
doc = {{"devices": [{{"fdinfo": {{"4242": {{"name": "srv", "usage": {{"name": "srv",
    "usage": {{"VRAM": {{"unit": "MiB", "value": 7}}}}}}}}}}}}]}}
print(json.dumps(doc), flush=True)
time.sleep(60)
"""


def fake_top(tmp_path: Path) -> str:
    script = tmp_path / "fake_top.py"
    script.write_text(FAKE_TOP.format(python=sys.executable))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def wait_for(condition: object, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():  # type: ignore[operator]
            return
        time.sleep(0.02)
    raise AssertionError("condition not met in time")


def available(top: sources.TopReader) -> bool:
    try:
        top.latest()
    except sources.SourceError:
        return False
    return True


def test_top_reader_exposes_latest_process_vram_and_stops_its_child(tmp_path: Path) -> None:
    top = sources.TopReader("0000:03:00.0", 100, executable=fake_top(tmp_path))
    top.start()
    try:
        wait_for(lambda: available(top))

        usage = top.latest()
        process = top._process

        assert usage == {4242: 7 * 1048576}
        assert process is not None and process.poll() is None
    finally:
        top.stop()
    assert process.poll() is not None


def test_top_reader_reports_missing_executable_as_source_error(tmp_path: Path) -> None:
    top = sources.TopReader("0000:03:00.0", 100, executable=str(tmp_path / "absent"))
    top.start()

    with pytest.raises(sources.SourceError, match="could not start"):
        top.latest()


def test_read_process_vram_sums_only_server_processes(tmp_path: Path) -> None:
    top = sources.TopReader("0000:03:00.0", 100, executable=fake_top(tmp_path))
    top.start()
    try:
        wait_for(lambda: available(top))

        reading = sources.read_process_vram(top, lambda: {4242, 1})
        missing = sources.read_process_vram(top, lambda: {1})
    finally:
        top.stop()

    assert reading.values == {"proc_vram_bytes": 7 * 1048576}
    assert "not yet listed" in missing.errors["proc_vram_bytes"]
