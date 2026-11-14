"""Telemetry readers over fake /proc, /sys, and cgroup trees."""

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


def test_read_system_reports_cpu_busy_and_total_ticks_without_guest_double_counting(
    tmp_path: Path,
) -> None:
    write(tmp_path / "stat", "cpu  100 10 50 800 20 5 15 0 7 0\ncpu0 1 1 1 1 1 1 1 1 1 1\n")

    reading = sources.read_system(tmp_path)

    assert reading.values["cpu_total_ticks"] == 1000
    assert reading.values["cpu_busy_ticks"] == 180


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


def make_drm_client(
    proc: Path, pid: int, fd: int, *, pdev: str, client: int, vram: str, driver: str = "amdgpu"
) -> None:
    write(
        proc / str(pid) / "fdinfo" / str(fd),
        f"pos:\t0\ndrm-driver:\t{driver}\ndrm-pdev:\t{pdev}\ndrm-client-id:\t{client}\n"
        f"drm-total-vram:\t{vram}\ndrm-memory-vram:\t{vram}\n",
    )


def test_read_drm_vram_sums_clients_of_the_server_processes_in_bytes(tmp_path: Path) -> None:
    gpu = "0000:03:00.0"
    make_drm_client(tmp_path, 10, 5, pdev=gpu, client=1, vram="15756212 KiB")
    make_drm_client(tmp_path, 11, 7, pdev=gpu, client=2, vram="2 MiB")

    reading = sources.read_drm_vram({10, 11}, gpu, tmp_path)

    assert reading.values == {"proc_vram_bytes": 15756212 * 1024 + 2 * 1024 * 1024}
    assert reading.errors == {}


def test_read_drm_vram_counts_a_client_once_when_several_descriptors_share_it(
    tmp_path: Path,
) -> None:
    gpu = "0000:03:00.0"
    make_drm_client(tmp_path, 10, 5, pdev=gpu, client=1, vram="100 KiB")
    make_drm_client(tmp_path, 10, 6, pdev=gpu, client=1, vram="100 KiB")

    reading = sources.read_drm_vram({10}, gpu, tmp_path)

    assert reading.values["proc_vram_bytes"] == 100 * 1024


def test_read_drm_vram_ignores_other_devices_and_other_drivers(tmp_path: Path) -> None:
    gpu = "0000:03:00.0"
    make_drm_client(tmp_path, 10, 5, pdev="0000:12:00.0", client=1, vram="999 KiB")
    make_drm_client(tmp_path, 10, 6, pdev=gpu, client=2, vram="999 KiB", driver="i915")
    make_drm_client(tmp_path, 10, 7, pdev=gpu, client=3, vram="4 KiB")

    reading = sources.read_drm_vram({10}, gpu, tmp_path)

    assert reading.values["proc_vram_bytes"] == 4 * 1024


def test_read_drm_vram_reports_zero_for_a_readable_process_that_does_not_use_the_gpu(
    tmp_path: Path,
) -> None:
    write(tmp_path / "10" / "fdinfo" / "0", "pos:\t0\nflags:\t02\n")

    reading = sources.read_drm_vram({10}, "0000:03:00.0", tmp_path)

    assert reading.values == {"proc_vram_bytes": 0}


def test_read_drm_vram_reports_unreadable_fdinfo_as_error_not_zero(tmp_path: Path) -> None:
    reading = sources.read_drm_vram({10}, "0000:03:00.0", tmp_path)

    assert reading.values == {}
    assert "fdinfo" in reading.errors["proc_vram_bytes"]


def test_read_drm_vram_without_server_processes_is_an_error(tmp_path: Path) -> None:
    reading = sources.read_drm_vram(set(), "0000:03:00.0", tmp_path)

    assert "no server processes" in reading.errors["proc_vram_bytes"]


def test_read_drm_vram_skips_processes_that_exit_between_listing_and_reading(
    tmp_path: Path,
) -> None:
    gpu = "0000:03:00.0"
    make_drm_client(tmp_path, 10, 5, pdev=gpu, client=1, vram="8 KiB")

    reading = sources.read_drm_vram({10, 99}, gpu, tmp_path)

    assert reading.values["proc_vram_bytes"] == 8 * 1024
