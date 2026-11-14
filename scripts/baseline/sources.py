"""Readers for host, server-process, and GPU telemetry.

Each reader returns a ``Reading``: the values it could take, and for every sample key it could not
take, the reason. A missing sensor or permission therefore becomes an unavailable metric with a
cause, never a zero. Paths are parameters so tests can read fake trees.
"""

import json
import os
import signal
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CLOCK_TICKS = os.sysconf("SC_CLK_TCK")
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")
CGROUP_KEYS = ("cpu_usec", "mem_bytes", "mem_anon_bytes", "mem_file_bytes", "swap_bytes")
GPU_KEYS = ("gpu_busy_percent", "vram_bytes", "gtt_bytes", "gpu_power_uw", "gpu_temp_mc")
MIB = 1024 * 1024
AMD_VENDOR = "0x1002"


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


def _stat_fields(proc: Path, pid: int) -> list[str]:
    text = (proc / str(pid) / "stat").read_text()
    return text.rsplit(")", 1)[1].split()


class ProcessTree:
    """A server process and its descendants, guarded against PID reuse."""

    def __init__(self, pid: int, proc: Path = Path("/proc")) -> None:
        self._pid = pid
        self._proc = proc
        self._start = _stat_fields(proc, pid)[19]

    def pids(self) -> set[int]:
        """The root process and its current descendants; empty if the root restarted or exited."""
        children: dict[int, list[int]] = {}
        try:
            if _stat_fields(self._proc, self._pid)[19] != self._start:
                return set()
        except (OSError, IndexError):
            return set()
        for entry in self._proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                parent = int(_stat_fields(self._proc, int(entry.name))[1])
            except (OSError, IndexError, ValueError):
                continue
            children.setdefault(parent, []).append(int(entry.name))
        found, pending = set(), [self._pid]
        while pending:
            pid = pending.pop()
            if pid not in found:
                found.add(pid)
                pending.extend(children.get(pid, []))
        return found

    def _members(self, keys: tuple[str, ...], reading: Reading) -> set[int] | None:
        members = self.pids()
        if not members:
            for key in keys:
                reading.errors[key] = "server process exited or restarted"
            return None
        return members

    def read_basic(self) -> Reading:
        """Summed CPU time and resident memory over the tree."""
        reading = Reading()
        members = self._members(("cpu_usec", "mem_rss_bytes"), reading)
        if members is None:
            return reading

        def cpu() -> float:
            ticks = 0
            for pid in members:
                fields = _stat_fields(self._proc, pid)
                ticks += int(fields[11]) + int(fields[12])
            return ticks * 1_000_000 // CLOCK_TICKS

        def rss() -> float:
            return sum(
                int((self._proc / str(p) / "statm").read_text().split()[1]) * PAGE_SIZE
                for p in members
            )

        reading.take("cpu_usec", cpu)
        reading.take("mem_rss_bytes", rss)
        return reading

    def read_pss(self) -> Reading:
        """Proportional set size over the tree; walks page tables, so sample it sparingly."""
        reading = Reading()
        members = self._members(("mem_pss_bytes",), reading)
        if members is None:
            return reading

        def pss() -> float:
            return sum(_keyed(self._proc / str(p) / "smaps_rollup")["Pss"] * 1024 for p in members)

        reading.take("mem_pss_bytes", pss)
        return reading


def read_system(proc: Path = Path("/proc")) -> Reading:
    """System memory (available, used by formula total-available), swap occupancy and activity."""
    reading = Reading()
    info: dict[str, int] = {}
    try:
        info = _keyed(proc / "meminfo")
    except OSError as error:
        for key in ("sys_available_bytes", "sys_used_bytes", "sys_swap_used_bytes"):
            reading.errors[key] = f"OSError: {error}"
    if info:
        reading.take("sys_available_bytes", lambda: info["MemAvailable"] * 1024)
        reading.take("sys_used_bytes", lambda: (info["MemTotal"] - info["MemAvailable"]) * 1024)
        reading.take("sys_swap_used_bytes", lambda: (info["SwapTotal"] - info["SwapFree"]) * 1024)
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
    reading.take("gtt_bytes", lambda: _integer(device / "mem_info_gtt_used"))
    reading.take("gpu_power_uw", lambda: _integer(_hwmon(device, "power1_average")))
    reading.take("gpu_temp_mc", lambda: _integer(_hwmon(device, "temp1_input")))
    return reading


def find_gpu(pci_root: Path = Path("/sys/bus/pci/devices")) -> tuple[str, list[str]]:
    """Choose the AMD device with the most VRAM, and list all AMD candidates by VRAM.

    Raises:
        SourceError: no AMD GPU with a readable VRAM size was found.
    """
    found: list[tuple[int, str]] = []
    if pci_root.is_dir():
        for device in pci_root.iterdir():
            try:
                if (device / "vendor").read_text().strip() != AMD_VENDOR:
                    continue
                found.append((_integer(device / "mem_info_vram_total"), device.name))
            except (OSError, ValueError, IndexError):
                continue
    if not found:
        raise SourceError("No AMD GPU with readable VRAM was found")
    found.sort(key=lambda item: (-item[0], item[1]))
    return found[0][1], [name for _, name in found]


def parse_top_line(line: str) -> dict[int, int]:
    """Per-process VRAM in bytes from one ``amdgpu_top --json`` document."""
    try:
        data: Any = json.loads(line)
        fdinfo = data["devices"][0]["fdinfo"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        raise SourceError(f"Unexpected amdgpu_top output: {type(error).__name__}") from error
    usage: dict[int, int] = {}
    for pid, entry in fdinfo.items():
        try:
            vram = entry["usage"]["usage"]["VRAM"]
        except (KeyError, TypeError):
            continue
        if isinstance(vram, dict) and isinstance(vram.get("value"), int | float):
            usage[int(pid)] = int(vram["value"] * MIB)
    return usage


class TopReader:
    """A long-lived ``amdgpu_top`` JSON stream; keeps the latest per-process VRAM.

    The child runs in its own session so it can be stopped with its process group, and ``stop``
    must be called even when the runner is interrupted.
    """

    def __init__(self, address: str, interval_ms: int, executable: str = "amdgpu_top") -> None:
        self._command = [
            executable, "-J", "-s", str(interval_ms), "-n", "0",
            "--pci", address, "--no-pc", "-u", "1",
        ]  # fmt: skip
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._latest: dict[int, int] | None = None
        self._failure: str | None = None
        self._exited = False

    def start(self) -> None:
        """Start the child; a failure to start is reported later by ``latest``."""
        try:
            process = subprocess.Popen(
                self._command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                start_new_session=True,
            )
        except OSError as error:
            self._failure, self._exited = f"amdgpu_top could not start: {error}", True
            return
        self._process = process
        threading.Thread(target=self._pump, args=(process,), daemon=True).start()

    def _pump(self, process: "subprocess.Popen[str]") -> None:
        for line in process.stdout or []:
            try:
                parsed = parse_top_line(line)
            except SourceError as error:
                with self._lock:
                    self._failure = str(error)
                continue
            with self._lock:
                self._latest, self._failure = parsed, None
        with self._lock:
            self._exited = True

    def latest(self) -> dict[int, int]:
        """Latest per-process VRAM in bytes.

        Raises:
            SourceError: no usable data has arrived, or the child exited.
        """
        with self._lock:
            if self._latest is None:
                raise SourceError(self._failure or "amdgpu_top has produced no data yet")
            if self._exited:
                raise SourceError("amdgpu_top exited")
            return dict(self._latest)

    def stop(self, grace_s: float = 2.0) -> None:
        """Stop the child and its process group; safe to call repeatedly."""
        process = self._process
        if process is None or process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        except ProcessLookupError:
            pass


def read_process_vram(top: TopReader, pids: Callable[[], set[int]]) -> Reading:
    """Per-process VRAM summed over the server's processes; refreshes lag by the fdinfo interval."""
    reading = Reading()
    try:
        usage = top.latest()
    except SourceError as error:
        reading.errors["proc_vram_bytes"] = str(error)
        return reading
    members = pids()
    if not members:
        reading.errors["proc_vram_bytes"] = "no server processes to attribute"
        return reading
    listed = members & usage.keys()
    if not listed:
        reading.errors["proc_vram_bytes"] = "server processes not yet listed by amdgpu_top fdinfo"
        return reading
    reading.values["proc_vram_bytes"] = sum(usage[pid] for pid in listed)
    return reading
