"""Assemble the telemetry sources for one run."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from baseline import sources
from baseline.sampler import Source
from baseline.sources import Reading, SourceError, TopReader

PSS_EVERY = 4


@dataclass
class Monitoring:
    """Sources to poll, how the target's memory is measured, and how to stop helper processes."""

    sources: list[Source]
    target: dict[str, Any]
    cleanup: Callable[[], None] = field(default=lambda: None)


def build_monitoring(
    *,
    cgroup: Path | None,
    pid: int | None,
    gpu_address: str | None,
    interval_ms: int,
    proc: Path = Path("/proc"),
    pci_root: Path = Path("/sys/bus/pci/devices"),
    top_executable: str | None = None,
) -> Monitoring:
    """Choose sources for a container (``cgroup``), a process tree (``pid``), or neither.

    Per-process GPU memory needs both a server target and ``top_executable``. The returned
    ``cleanup`` stops any helper process and may be called repeatedly.

    Raises:
        SourceError: the server process cannot be found.
    """
    chosen: list[Source] = [
        Source("system", lambda: sources.read_system(proc), ("sys_available_bytes", "pswpin"))
    ]
    target: dict[str, Any] = {
        "memory_key": "mem_bytes",
        "memory_label": "no server process selected",
        "cpu_label": "no server process selected",
    }
    pids: Callable[[], set[int]] | None = None
    if cgroup is not None:
        chosen.append(Source("cgroup", lambda: sources.read_cgroup(cgroup), sources.CGROUP_KEYS))
        pids = lambda: sources.cgroup_pids(cgroup)  # noqa: E731
        target.update(memory_label="cgroup memory.current", cpu_label="cgroup cpu.stat")
    elif pid is not None:
        try:
            tree = sources.ProcessTree(pid, proc)
        except (OSError, IndexError) as error:
            raise SourceError(f"Cannot read process {pid}: {error}") from error
        chosen.append(Source("process", tree.read_basic, ("cpu_usec", "mem_rss_bytes")))
        pids = tree.pids
        target.update(cpu_label="/proc process tree CPU time")
        if tree.read_pss().values:
            chosen.append(Source("process-pss", tree.read_pss, ("mem_pss_bytes",), PSS_EVERY))
            target.update(
                memory_key="mem_pss_bytes", memory_label="process tree PSS (smaps_rollup)"
            )
        else:
            target.update(
                memory_key="mem_rss_bytes",
                memory_label="process tree RSS (statm; shared pages counted per process)",
            )
    top: TopReader | None = None
    if gpu_address is not None:
        device = pci_root / gpu_address
        chosen.append(Source("gpu", lambda: sources.read_gpu(device), sources.GPU_KEYS))
        if top_executable is not None and pids is not None:
            top = TopReader(gpu_address, interval_ms, top_executable)
            top.start()
            reader, members = top, pids

            def process_vram() -> Reading:
                return sources.read_process_vram(reader, members)

            chosen.append(Source("process-vram", process_vram, ("proc_vram_bytes",)))

    def cleanup() -> None:
        if top is not None:
            top.stop()

    return Monitoring(chosen, target, cleanup)
