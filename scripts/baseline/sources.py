"""Readers for host, server-process, and GPU telemetry.

Each reader returns a ``Reading``: the values it could take, and for every sample key it could not
take, the reason. A missing sensor or permission therefore becomes an unavailable metric with a
cause, never a zero. Paths are parameters so tests can read fake trees.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import host_facts

CGROUP_KEYS = ("cpu_usec", "mem_bytes", "mem_anon_bytes", "mem_file_bytes", "swap_bytes")
GPU_KEYS = (
    "gpu_busy_percent",
    "vram_bytes",
    "vram_total_bytes",
    "gtt_bytes",
    "gpu_power_uw",
    "gpu_temp_mc",
)


class SourceError(Exception):
    """A telemetry source could not be used at all; the message is the reason."""


@dataclass
class Reading:
    """Values taken by one read, and the reason for each sample key that could not be taken."""

    values: dict[str, float] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    def take(self, key: str, read: Callable[[], float]) -> None:
        try:
            self.values[key] = read()
        except (OSError, ValueError, IndexError, KeyError) as error:
            self.errors[key] = f"{type(error).__name__}: {error}"


def _integer(path: Path) -> int:
    return int(path.read_text().split()[0])


def _keyed(path: Path) -> dict[str, int]:
    result = {}
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].lstrip("-").isdigit():
            result[parts[0].rstrip(":")] = int(parts[1])
    return result


def read_cgroup(path: Path) -> Reading:
    """Read a container's cgroup v2 CPU time, charged memory, memory breakdown, and swap."""
    reading = Reading()
    reading.take("cpu_usec", lambda: _keyed(path / "cpu.stat")["usage_usec"])
    reading.take("mem_bytes", lambda: _integer(path / "memory.current"))
    reading.take("mem_anon_bytes", lambda: _keyed(path / "memory.stat")["anon"])
    reading.take("mem_file_bytes", lambda: _keyed(path / "memory.stat")["file"])
    reading.take("swap_bytes", lambda: _integer(path / "memory.swap.current"))
    return reading


def cgroup_pids(path: Path) -> set[int]:
    """Process IDs currently in a cgroup."""
    try:
        return {int(item) for item in (path / "cgroup.procs").read_text().split()}
    except (OSError, ValueError):
        return set()


def _cpu_ticks(path: Path) -> tuple[int, int]:
    """Busy and total system CPU ticks; guest time is already part of user time."""
    user, nice, system, idle, iowait, irq, softirq, steal = (
        int(field) for field in path.read_text().splitlines()[0].split()[1:9]
    )
    total = user + nice + system + idle + iowait + irq + softirq + steal
    return total - idle - iowait, total


def read_system(proc: Path = Path("/proc")) -> Reading:
    """System memory (used = total - available), swap occupancy and activity, and CPU ticks."""
    reading = Reading()
    info: dict[str, int] = {}
    try:
        info = _keyed(proc / "meminfo")
    except OSError as error:
        for key in ("sys_available_bytes", "sys_used_bytes", "sys_swap_used_bytes"):
            reading.errors[key] = f"OSError: {error}"
    if info:
        reading.take("sys_total_bytes", lambda: info["MemTotal"] * 1024)
        reading.take("sys_available_bytes", lambda: info["MemAvailable"] * 1024)
        reading.take("sys_used_bytes", lambda: (info["MemTotal"] - info["MemAvailable"]) * 1024)
        reading.take("sys_swap_total_bytes", lambda: info["SwapTotal"] * 1024)
        reading.take("sys_swap_used_bytes", lambda: (info["SwapTotal"] - info["SwapFree"]) * 1024)
    reading.take("cpu_busy_ticks", lambda: _cpu_ticks(proc / "stat")[0])
    reading.take("cpu_total_ticks", lambda: _cpu_ticks(proc / "stat")[1])
    reading.take("pswpin", lambda: _keyed(proc / "vmstat")["pswpin"])
    reading.take("pswpout", lambda: _keyed(proc / "vmstat")["pswpout"])
    return reading


def _hwmon(device: Path, name: str) -> Path:
    for directory in sorted((device / "hwmon").glob("hwmon*")):
        if (directory / name).is_file():
            return directory / name
    raise FileNotFoundError(f"{name} not found under {device}/hwmon")


def read_gpu(device: Path) -> Reading:
    """Device-wide load, VRAM, GTT, power, and temperature from the amdgpu sysfs interface."""
    reading = Reading()
    reading.take("gpu_busy_percent", lambda: _integer(device / "gpu_busy_percent"))
    reading.take("vram_bytes", lambda: _integer(device / "mem_info_vram_used"))
    reading.take("vram_total_bytes", lambda: _integer(device / "mem_info_vram_total"))
    reading.take("gtt_bytes", lambda: _integer(device / "mem_info_gtt_used"))
    reading.take("gpu_power_uw", lambda: _integer(_hwmon(device, "power1_average")))
    reading.take("gpu_temp_mc", lambda: _integer(_hwmon(device, "temp1_input")))
    return reading


def find_gpu(pci_root: Path = Path("/sys/bus/pci/devices")) -> tuple[str, list[str]]:
    """Choose the AMD device with the most VRAM, and list all AMD candidates by VRAM.

    Raises:
        SourceError: no AMD GPU with a readable VRAM size was found.
    """
    devices = host_facts.amd_devices(pci_root)
    if not devices:
        raise SourceError("No AMD GPU with readable VRAM was found")
    candidates = [name for _, name in devices]
    return candidates[0], candidates


def _kib(value: str) -> int:
    """Bytes from a fdinfo size such as ``15756212 KiB``."""
    amount, _, unit = value.partition(" ")
    scale = {"": 1, "B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}[unit.strip()]
    return int(amount) * scale


def read_drm_vram(pids: set[int], address: str, proc: Path = Path("/proc")) -> Reading:
    """VRAM held on one GPU by the given processes, read from DRM fdinfo.

    Each DRM client is counted once even when several descriptors share it. A process that
    exits while being read is skipped. A process whose fdinfo is readable but holds no client
    on this device uses no VRAM there (zero); if no fdinfo could be read at all, the result is
    an error rather than a zero.
    """
    reading = Reading()
    if not pids:
        reading.errors["proc_vram_bytes"] = "no server processes to attribute"
        return reading
    clients: dict[str, int] = {}
    readable = False
    for pid in pids:
        try:
            descriptors = list((proc / str(pid) / "fdinfo").iterdir())
        except OSError:
            continue
        readable = True
        for descriptor in descriptors:
            try:
                fields = dict(
                    line.split(":\t", 1)
                    for line in descriptor.read_text().splitlines()
                    if ":\t" in line
                )
                if fields.get("drm-driver") != "amdgpu" or fields.get("drm-pdev") != address:
                    continue
                clients[fields["drm-client-id"]] = _kib(fields.get("drm-memory-vram", "0 KiB"))
            except (OSError, KeyError, ValueError):
                continue
    if not readable:
        reading.errors["proc_vram_bytes"] = "fdinfo of the server processes is not readable"
        return reading
    reading.values["proc_vram_bytes"] = sum(clients.values())
    return reading
