"""Assemble the telemetry sources for one run."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from baseline import sources
from baseline.sampler import Source


@dataclass
class Monitoring:
    """Sources to poll, and how the server's memory and CPU are measured."""

    sources: list[Source]
    target: dict[str, Any]


def target_sources(
    cgroup: Path,
    gpu_address: str | None,
    proc: Path = Path("/proc"),
) -> tuple[list[Source], dict[str, Any]]:
    """Sources for a server's cgroup, and how its memory and CPU are labeled.

    A run adds these to a running sampler once the server exists. Server VRAM comes from the DRM
    fdinfo of the cgroup's current processes, so processes that start later are followed.
    """
    added = [Source("cgroup", lambda: sources.read_cgroup(cgroup), sources.CGROUP_KEYS)]
    if gpu_address is not None:
        address = gpu_address
        added.append(
            Source(
                "process-vram",
                lambda: sources.read_drm_vram(sources.cgroup_pids(cgroup), address, proc),
                ("proc_vram_bytes",),
            )
        )
    target = {
        "memory_key": "mem_bytes",
        "memory_label": "cgroup memory.current",
        "cpu_label": "cgroup cpu.stat",
    }
    return added, target


def build_monitoring(
    *,
    cgroup: Path | None,
    gpu_address: str | None,
    proc: Path = Path("/proc"),
    pci_root: Path = Path("/sys/bus/pci/devices"),
) -> Monitoring:
    """Choose sources for a server running in ``cgroup`` (a container or a desktop app's scope).

    System and GPU readings are always available. With a cgroup, the server's CPU, memory, and
    swap come from its cgroup files and its VRAM from the DRM fdinfo of the cgroup's current
    processes, so processes that start later are followed.
    """
    chosen: list[Source] = [
        Source("system", lambda: sources.read_system(proc), ("sys_available_bytes", "pswpin"))
    ]
    target: dict[str, Any] = {
        "memory_key": "mem_bytes",
        "memory_label": "no server selected",
        "cpu_label": "no server selected",
    }
    if cgroup is not None:
        chosen.append(Source("cgroup", lambda: sources.read_cgroup(cgroup), sources.CGROUP_KEYS))
        target.update(memory_label="cgroup memory.current", cpu_label="cgroup cpu.stat")
    if gpu_address is not None:
        device = pci_root / gpu_address
        chosen.append(Source("gpu", lambda: sources.read_gpu(device), sources.GPU_KEYS))
        if cgroup is not None:
            members, address = cgroup, gpu_address
            chosen.append(
                Source(
                    "process-vram",
                    lambda: sources.read_drm_vram(sources.cgroup_pids(members), address, proc),
                    ("proc_vram_bytes",),
                )
            )
    return Monitoring(chosen, target)
