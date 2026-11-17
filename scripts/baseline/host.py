"""Host and server-process facts gathered before a run: boot state, container, and revision."""

import hashlib
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import paths

from baseline import schema, sources

Run = Callable[[list[str]], "subprocess.CompletedProcess[str]"]
GIB = 1024**3
GPU_BUSY_WARNING = 5.0
INSTANCE_LABEL = "io.llm-recipes.instance"
MANAGED_LABEL = "io.llm-recipes.managed"


class HostError(Exception):
    """A host fact could not be established; the message says what to fix."""


def run_command(command: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    """Run a bounded, noninteractive command; a missing executable is reported as a failure."""
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))


def _metric(read: Callable[[], float], unit: str, source: str) -> dict[str, Any]:
    try:
        return schema.measured(round(read(), 6), unit, source)
    except (OSError, ValueError, IndexError, KeyError) as error:
        return schema.unavailable(f"{source}: {type(error).__name__}: {error}")


def boot_state(proc: Path, gpu_device: Path | None) -> dict[str, Any]:
    """Uptime, load, memory, and idle GPU readings, with warnings when the machine is busy."""
    system = sources.read_system(proc)
    metrics: dict[str, Any] = {
        "uptime_s": _metric(
            lambda: float((proc / "uptime").read_text().split()[0]), "s", "/proc/uptime"
        ),
    }
    for key, name, source in (
        ("sys_used_bytes", "mem_used_gib", "/proc/meminfo MemTotal-MemAvailable"),
        ("sys_total_bytes", "mem_total_gib", "/proc/meminfo MemTotal"),
        ("sys_swap_used_bytes", "swap_used_gib", "/proc/meminfo SwapTotal-SwapFree"),
        ("sys_swap_total_bytes", "swap_total_gib", "/proc/meminfo SwapTotal"),
    ):
        metrics[name] = (
            schema.measured(round(system.values[key] / GIB, 6), "GiB", source)
            if key in system.values
            else schema.unavailable(system.errors.get(key, f"{key} was not reported"))
        )
    warnings: list[str] = []
    if gpu_device is not None:
        gpu = sources.read_gpu(gpu_device)
        for key, name, scale, unit in (
            ("gpu_busy_percent", "gpu_busy_percent", 1, "%"),
            ("vram_bytes", "gpu_vram_used_gib", GIB, "GiB"),
            ("vram_total_bytes", "gpu_vram_total_gib", GIB, "GiB"),
            ("gpu_power_uw", "gpu_power_w", 1_000_000, "W"),
            ("gpu_temp_mc", "gpu_temp_c", 1000, "C"),
        ):
            metrics[name] = (
                schema.measured(round(gpu.values[key] / scale, 6), unit, "amdgpu sysfs")
                if key in gpu.values
                else schema.unavailable(gpu.errors.get(key, f"{key} was not reported"))
            )
    busy = metrics.get("gpu_busy_percent", {}).get("value")
    if busy is not None and busy > GPU_BUSY_WARNING:
        warnings.append(f"GPU is {busy:.0f}% busy at start")
    return {"metrics": metrics, "warnings": warnings}


def cgroup_path_of(
    pid: int, proc: Path = Path("/proc"), root: Path = Path("/sys/fs/cgroup")
) -> Path:
    """The cgroup v2 directory of a process.

    Raises:
        HostError: the process is gone or the host does not use the unified hierarchy.
    """
    try:
        lines = (proc / str(pid) / "cgroup").read_text().splitlines()
    except OSError as error:
        raise HostError(f"Cannot read the cgroup of process {pid}: {error}") from error
    for line in lines:
        if line.startswith("0::"):
            return root / line[3:].lstrip("/")
    raise HostError("The host does not use cgroup v2; container metrics are unavailable")


@dataclass(frozen=True)
class ContainerInfo:
    container_id: str
    pid: int
    cgroup: Path
    image_id: str
    image: str


def resolve_container(
    instance: str,
    run: Run = run_command,
    proc: Path = Path("/proc"),
    cgroup_root: Path = Path("/sys/fs/cgroup"),
) -> ContainerInfo:
    """Find a launcher-managed container by instance label, with its host PID and cgroup.

    Raises:
        HostError: Docker cannot be inspected non-interactively, or no such instance runs.
    """
    fix = (
        "sudo credentials may have timed out; re-run to refresh them, or check the Docker service."
    )
    listing = run(
        [
            "sudo", "-n", "docker", "ps",
            "--filter", f"label={MANAGED_LABEL}=true",
            "--filter", f"label={INSTANCE_LABEL}={instance}",
            "--format", "{{.ID}}",
        ]
    )  # fmt: skip
    if listing.returncode:
        raise HostError(f"Docker inspection failed: {listing.stderr.strip()}. {fix}")
    ids = listing.stdout.split()
    if not ids:
        raise HostError(f"No running instance '{instance}' was found among launcher containers")
    inspected = run(
        [
            "sudo", "-n", "docker", "inspect",
            "--format", "{{.State.Pid}} {{.Image}} {{.Config.Image}}", ids[0],
        ]
    )  # fmt: skip
    parts = inspected.stdout.split()
    if inspected.returncode or len(parts) != 3 or not parts[0].isdigit():
        raise HostError(
            f"Docker inspection failed: {inspected.stderr.strip() or inspected.stdout}. {fix}"
        )
    pid = int(parts[0])
    return ContainerInfo(ids[0], pid, cgroup_path_of(pid, proc, cgroup_root), parts[1], parts[2])


def repository_revision(root: Path, run: Run = run_command) -> dict[str, Any] | None:
    """The repository commit and whether the working tree has changes; ``None`` if unavailable.

    Outside a git checkout (an installed snapshot), falls back to the installer's
    ``VERSION`` stamp so runs still record the exact serving code.
    """
    commit = run(["git", "-C", str(root), "rev-parse", "HEAD"])
    if commit.returncode:
        return paths.version_stamp(root)
    status = run(["git", "-C", str(root), "status", "--porcelain"])
    return {"commit": commit.stdout.strip(), "dirty": bool(status.stdout.strip())}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
