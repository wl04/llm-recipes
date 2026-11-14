"""Decisions about the phases of a managed run."""

from typing import Any


def settled(
    samples: list[dict[str, Any]],
    *,
    window_s: float,
    system_cpu_max: float,
    server_cpu_max: float,
) -> bool | None:
    """Whether the system and the server stayed quiet for the last ``window_s`` seconds.

    System CPU is the busy share of ``/proc/stat`` ticks (percent) and server CPU is the cgroup's
    average cores. A criterion whose counters are missing is not judged. Returns ``None`` until
    the window has been observed.
    """
    if not samples:
        return None
    latest = samples[-1]["t"]
    start = latest - window_s
    before = [s for s in samples if s["t"] <= start]
    if not before:
        return None
    window = [before[-1], *(s for s in samples if s["t"] > start)]
    first, final = window[0], window[-1]
    elapsed = final["t"] - first["t"]

    def rise(key: str) -> float | None:
        earlier, later = first["values"].get(key), final["values"].get(key)
        return None if earlier is None or later is None or later < earlier else later - earlier

    verdicts: list[bool] = []
    cpu = rise("cpu_usec")
    if cpu is not None and elapsed > 0:
        verdicts.append(cpu / 1_000_000 / elapsed <= server_cpu_max)
    busy, total = rise("cpu_busy_ticks"), rise("cpu_total_ticks")
    if busy is not None and total:
        verdicts.append(100 * busy / total <= system_cpu_max)
    return all(verdicts)
