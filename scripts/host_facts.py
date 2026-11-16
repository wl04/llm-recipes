"""Deterministic host facts from unprivileged reads: OS, kernel, CPU, memory, and GPU.

Every fact comes from a path that Docker runs already rely on (``/proc``, ``/sys``),
so no command in this module needs elevation.  Each reader takes its filesystem root
as an argument so tests can pass a fabricated tree.
"""

import contextlib
import os
import re
import socket
import subprocess
from collections.abc import Callable
from pathlib import Path

GIB = 1024**3
AMD_VENDOR = "0x1002"

#: PCI device IDs whose AMD gfx architecture is established; matches the ROCm
#: device maps used by vLLM and ROCm tooling (0x7550 = Navi 48, gfx1201).
GFX_ARCH_BY_DEVICE = {"0x7550": "gfx1201"}

_GPU_LINE = re.compile(
    r"^(?P<addr>[0-9a-f:.]+)\s+\S.*?:\s+(?P<desc>.+)\s+\[(?P<ids>[0-9a-f]{4}:[0-9a-f]{4})\]"
    r"(?:\s+\(rev\s+(?P<rev>[0-9a-f]+)\))?$"
)


class HostFactsError(OSError):
    """A required host fact could not be read; the message names the path."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError as error:
        raise HostFactsError(f"Cannot read host fact: {path}") from error


def _parse_os_release(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key] = value.strip().strip('"')
    return values


def os_block(etc_root: Path = Path("/etc")) -> dict[str, str]:
    """Distribution name and version from os-release."""
    values = _parse_os_release(_read_text(etc_root / "os-release"))
    try:
        name = values["NAME"]
    except KeyError as error:
        raise HostFactsError("os-release does not define NAME") from error
    return {"name": name, "version": values.get("VERSION_ID") or values.get("VERSION") or ""}


def kernel_release(proc: Path = Path("/proc")) -> str:
    """Kernel version string."""
    return _read_text(proc / "sys/kernel/osrelease")


def cpu_block(proc: Path = Path("/proc")) -> dict[str, object]:
    """CPU model name and logical core count from cpuinfo."""
    model: str | None = None
    cores = 0
    for line in _read_text(proc / "cpuinfo").splitlines():
        if line.startswith("processor"):
            cores += 1
        elif model is None and line.startswith("model name"):
            _, _, value = line.partition(":")
            model = value.strip()
    if model is None:
        raise HostFactsError(f"{proc}/cpuinfo does not define model name")
    return {"model": model, "cores": cores}


def memory_total_gib(proc: Path = Path("/proc")) -> float:
    """Total system memory in GiB from meminfo."""
    for line in _read_text(proc / "meminfo").splitlines():
        if line.startswith("MemTotal:"):
            kib = int(line.split()[1])
            return round(kib * 1024 / GIB, 2)
    raise HostFactsError(f"{proc}/meminfo does not define MemTotal")


def amd_devices(pci_root: Path) -> list[tuple[int, str]]:
    """AMD PCI devices with a readable VRAM size, largest VRAM first, PCI name as tie-break.

    This is the machine's GPU selection rule: the first entry is the discrete GPU to measure
    and to report, and every entry is a candidate for the same role.
    """
    found: list[tuple[int, str]] = []
    if pci_root.is_dir():
        for device in pci_root.iterdir():
            try:
                if (device / "vendor").read_text().strip() != AMD_VENDOR:
                    continue
            except OSError:
                continue
            try:
                vram = int((device / "mem_info_vram_total").read_text().strip())
            except (OSError, ValueError):
                continue
            found.append((vram, device.name))
    found.sort(key=lambda item: (-item[0], item[1]))
    return found


def _lspci() -> str:
    return subprocess.run(
        ["lspci", "-nn"], check=True, capture_output=True, text=True
    ).stdout  # fmt: skip


def parse_gpu_description(lspci_output: str, pci_address: str) -> str | None:
    """Device description for one PCI address from ``lspci -nn``, or None if absent."""
    short = re.sub(r"^[0-9a-f]{4}:", "", pci_address, count=1)
    for line in lspci_output.splitlines():
        match = _GPU_LINE.match(line)
        if match and match["addr"] == short:
            return match["desc"]
    return None


def gpu_block(
    sys_root: Path = Path("/sys"),
    lspci: Callable[[], str] | None = None,
) -> dict[str, object]:
    """Discrete GPU facts: description, gfx architecture, VRAM, and kernel driver.

    The description falls back to ``None`` when ``lspci`` is unavailable; architecture
    is ``None`` for device IDs missing from the reviewed table.
    """
    devices = amd_devices(sys_root / "bus/pci/devices")
    if not devices:
        raise HostFactsError(f"No AMD GPU with readable VRAM found under {sys_root}")
    vram_bytes, pci_name = devices[0]
    device = sys_root / "bus/pci/devices" / pci_name
    try:
        device_id = _read_text(device / "device")
    except HostFactsError:
        device_id = ""
    driver: str | None = None
    with contextlib.suppress(OSError):
        driver = Path(os.readlink(device / "driver")).name
    model: str | None = None
    if lspci is not None:
        try:
            model = parse_gpu_description(lspci(), pci_name)
        except (OSError, subprocess.SubprocessError):
            model = None
    return {
        "model": model,
        "gfx_arch": GFX_ARCH_BY_DEVICE.get(device_id),
        "vram_total_gib": round(vram_bytes / GIB, 2),
        "driver": driver,
        "pci_device": device_id,
    }


def collect(
    *,
    proc: Path = Path("/proc"),
    sys_root: Path = Path("/sys"),
    etc_root: Path = Path("/etc"),
    hostname: Callable[[], str] = socket.gethostname,
    lspci: Callable[[], str] | None = _lspci,
) -> dict[str, object]:
    """Gather the host block: identity, OS, kernel, CPU, memory, and GPU.

    Raises:
        HostFactsError: a required fact could not be read. Optional fields (GPU
        description and gfx architecture) report ``None`` instead of failing.
    """
    return {
        "hostname": hostname(),
        "os": os_block(etc_root),
        "kernel": kernel_release(proc),
        "cpu": cpu_block(proc),
        "memory": {"total_gib": memory_total_gib(proc)},
        "gpu": gpu_block(sys_root, lspci),
    }
