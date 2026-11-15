"""Host facts from fabricated sysfs/procfs trees: no elevation, no real /sys reads."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import host_facts
import pytest

LSPCI_OUTPUT = """12:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] \
Granite Ridge [Radeon Graphics] [1002:13c0] (rev cb)
03:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] \
Navi 48 [Radeon RX 9070/9070 XT/9070 GRE] [1002:7550] (rev c0)
04:00.0 Non-Volatile memory controller [0108]: Solid State Drive [1234:5678]
"""
VRAM_BYTES = 17095983104


def _gpu_device(pci_root: Path, name: str, device_id: str, vram: int, driver: str | None) -> None:
    device = pci_root / name
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (device / "device").write_text(f"{device_id}\n")
    (device / "mem_info_vram_total").write_text(f"{vram}\n")
    if driver is not None:
        drivers = pci_root.parent / "drivers" / driver
        drivers.mkdir(parents=True, exist_ok=True)
        (device / "driver").symlink_to(drivers, target_is_directory=True)


def make_host_tree(tmp_path: Path) -> dict[str, Path]:
    """Create a minimal fake /proc, /sys, and /etc matching a real 9070 XT host."""
    proc = tmp_path / "proc"
    (proc / "sys/kernel").mkdir(parents=True)
    (proc / "sys/kernel/osrelease").write_text("7.3.0-10-generic\n")
    (proc / "cpuinfo").write_text(
        "\n".join(f"processor\t: {i}" for i in range(32))
        + "\n"
        + "\n".join(
            [
                "vendor_id\t: AuthenticAMD",
                "model name\t: AMD Ryzen 9 9950X 16-Core Processor",
                "",
            ]
        )
    )
    (proc / "meminfo").write_text(
        "MemTotal:       65461056 kB\nMemFree:         1000000 kB\nSwapTotal:             0 kB\n"
    )
    pci_root = tmp_path / "sys/bus/pci/devices"
    _gpu_device(pci_root, "0000:03:00.0", "0x7550", VRAM_BYTES, "amdgpu")
    _gpu_device(pci_root, "0000:12:00.0", "0x13c0", 268435456, "amdgpu")
    (pci_root / "0000:04:00.0").mkdir()
    (pci_root / "0000:04:00.0/vendor").write_text("0x144d\n")
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "os-release").write_text(
        'NAME="Ubuntu"\nVERSION_ID="26.04"\nPRETTY_NAME="Ubuntu 26.04 LTS"\n'
    )
    return {"proc": proc, "sys_root": tmp_path / "sys", "etc_root": etc}


def collect(tmp_path: Path, lspci: Callable[[], str] = lambda: LSPCI_OUTPUT) -> dict[str, object]:
    tree = make_host_tree(tmp_path)
    return host_facts.collect(hostname=lambda: "bench", lspci=lspci, **tree)


def test_host_facts_reads_os_kernel_gpu_cpu_and_ram_without_privileges(tmp_path: Path) -> None:
    facts = collect(tmp_path)

    assert facts["hostname"] == "bench"
    assert facts["os"] == {"name": "Ubuntu", "version": "26.04"}
    assert facts["kernel"] == "7.3.0-10-generic"
    assert facts["cpu"] == {"model": "AMD Ryzen 9 9950X 16-Core Processor", "cores": 32}
    assert facts["memory"] == {"total_gib": 62.43}


def test_gpu_block_picks_largest_amd_device_with_arch_and_driver(tmp_path: Path) -> None:
    gpu: Any = collect(tmp_path)["gpu"]

    assert gpu == {
        "model": (
            "Advanced Micro Devices, Inc. [AMD/ATI] Navi 48 [Radeon RX 9070/9070 XT/9070 GRE]"
        ),
        "gfx_arch": "gfx1201",
        "vram_total_gib": 15.92,
        "driver": "amdgpu",
        "pci_device": "0x7550",
    }


def test_gpu_block_reports_unknown_arch_for_unreviewed_device_id(tmp_path: Path) -> None:
    tree = make_host_tree(tmp_path)
    (tree["sys_root"] / "bus/pci/devices/0000:03:00.0/device").write_text("0x744c\n")

    gpu = host_facts.gpu_block(tree["sys_root"], lspci=lambda: LSPCI_OUTPUT)

    assert gpu["gfx_arch"] is None
    assert gpu["vram_total_gib"] == 15.92


def test_gpu_block_still_reports_vram_when_lspci_fails(tmp_path: Path) -> None:
    def broken_lspci() -> str:
        raise FileNotFoundError("lspci is not installed")

    gpu: Any = collect(tmp_path, lspci=broken_lspci)["gpu"]

    assert gpu["model"] is None
    assert gpu["gfx_arch"] == "gfx1201"


def test_gpu_block_fails_loudly_when_no_amd_gpu_exists(tmp_path: Path) -> None:
    tree = make_host_tree(tmp_path)
    for name in ("0000:03:00.0", "0000:12:00.0"):
        (tree["sys_root"] / "bus/pci/devices" / name / "vendor").write_text("0x8086\n")

    with pytest.raises(host_facts.HostFactsError, match="No AMD GPU"):
        host_facts.gpu_block(tree["sys_root"], lspci=lambda: LSPCI_OUTPUT)


def test_parse_gpu_description_matches_the_requested_address_only() -> None:
    navi = host_facts.parse_gpu_description(LSPCI_OUTPUT, "0000:03:00.0")
    assert navi is not None and "Navi 48" in navi
    granite = host_facts.parse_gpu_description(LSPCI_OUTPUT, "0000:12:00.0")
    assert granite is not None and "Granite Ridge" in granite
    assert host_facts.parse_gpu_description(LSPCI_OUTPUT, "0000:99:00.0") is None


def test_host_facts_missing_required_file_names_the_path(tmp_path: Path) -> None:
    with pytest.raises(host_facts.HostFactsError, match="os-release"):
        host_facts.os_block(tmp_path / "etc")
