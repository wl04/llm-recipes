"""Build the result document from raw request and sample records.

Only the raw files are needed, so an interrupted run can be rendered later and presentation
changes never require repeating inference.
"""

import statistics
from collections.abc import Callable
from itertools import pairwise
from typing import Any

from baseline import schema, stats
from baseline.rawlog import RawRun

GIB = 1024**3
CLIENT_SOURCE = "client monotonic clock"
Interval = tuple[float, float]
Points = list[tuple[float, float]]


def _tidy(value: float) -> float | int:
    rounded = round(value, 6)
    return int(rounded) if float(rounded).is_integer() else rounded


def _measured(value: float, unit: str, source: str) -> dict[str, Any]:
    return schema.measured(_tidy(value), unit, source)


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _median_metric(values: list[float], unit: str, source: str, missing: str) -> dict[str, Any]:
    median = _median(values)
    return schema.unavailable(missing) if median is None else _measured(median, unit, source)


def _case_metrics(ok: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    usages = [r["usage"] for r in ok if r.get("usage")]
    prompt = [u["prompt_tokens"] for u in usages if u.get("prompt_tokens") is not None]
    completion = [u["completion_tokens"] for u in usages if u.get("completion_tokens") is not None]
    cached = [u["cached_tokens"] for u in usages if u.get("cached_tokens") is not None]
    first = [r["first_output_s"] for r in ok if r.get("first_output_s") is not None]
    rates = [
        rate
        for r in ok
        if (
            rate := stats.client_decode_rate(
                (r.get("usage") or {}).get("completion_tokens"),
                r.get("first_output_s"),
                r.get("last_output_s"),
            )
        )
        is not None
    ]
    no_usage = "server reported no usage"
    engine = f"engine timings are not parsed for {kind}"
    metrics = {
        "input_tokens": _median_metric(prompt, "tokens", "server usage", no_usage),
        "output_tokens": _median_metric(completion, "tokens", "server usage", no_usage),
        "cached_input_tokens": _median_metric(
            cached, "tokens", "server usage", "server reports no cached-token counts"
        ),
        "first_output_s": _median_metric(first, "s", CLIENT_SOURCE, "no output was received"),
        "client_decode_tok_s": _median_metric(
            rates,
            "tokens/s",
            "client estimate: (tokens - 1) / (last - first output)",
            "fewer than two output tokens, no usage, or no streaming timings",
        ),
        "engine_prefill_tok_s": schema.unavailable(engine),
        "engine_decode_tok_s": schema.unavailable(engine),
    }
    if any(r.get("noise_probe") for r in ok) and len(ok) >= 2:
        for name, values in (("noise_first_output_spread", first), ("noise_decode_spread", rates)):
            spread = stats.relative_spread(values)
            if spread is not None:
                metrics[name] = _measured(spread, "ratio", f"{len(ok)} runs, range over median")
    return metrics


def _case_entry(case_id: str, records: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    attempts = [r for r in records if r.get("status") != "skipped"]
    if not attempts:
        note = "; ".join(str(r.get("note", "")) for r in records if r.get("note"))
        return {"id": case_id, "status": "skipped", "runs": 0, "note": note, "metrics": {}}
    ok = [r for r in attempts if r["status"] == "ok"]
    notes = [
        f"run {r.get('run', '?')}: {r.get('error') or r['status']}"
        for r in attempts
        if r["status"] != "ok"
    ]
    status = "ok" if ok else "failed"
    metrics: dict[str, Any] = {}
    if ok:
        metrics = _case_metrics(ok, kind)
        minimum = max((r.get("min_output_tokens") or 0 for r in ok), default=0)
        output = metrics["output_tokens"]["value"]
        if minimum and output is not None and output < minimum:
            status = "insufficient_sample"
            notes.append(f"Median output {output} tokens is below the {minimum}-token minimum")
    entry: dict[str, Any] = {"id": case_id, "status": status, "runs": len(attempts)}
    if ok and ok[-1].get("finish_reason"):
        entry["finish_reason"] = ok[-1]["finish_reason"]
    if notes:
        entry["note"] = "; ".join(notes)
    entry["metrics"] = metrics
    return entry


def _points(samples: list[dict[str, Any]], key: str) -> Points:
    return [(s["t"], s["values"][key]) for s in samples if key in s["values"]]


def _within(samples: list[dict[str, Any]], intervals: list[Interval]) -> list[dict[str, Any]]:
    return [s for s in samples if any(a <= s["t"] <= b for a, b in intervals)]


def _interpolate(points: Points, when: float) -> float | None:
    if not points or when < points[0][0] or when > points[-1][0]:
        return None
    for (t0, v0), (t1, v1) in pairwise(points):
        if t0 <= when <= t1:
            return v0 if t1 == t0 else v0 + (v1 - v0) * (when - t0) / (t1 - t0)
    return points[-1][1]


def _counter_change(points: Points, intervals: list[Interval]) -> tuple[float, float] | None:
    """Total counter increase and covered seconds, skipping intervals that cannot be bracketed."""
    change = covered = 0.0
    for start, end in intervals:
        begin, finish = _interpolate(points, start), _interpolate(points, end)
        if begin is None or finish is None or finish < begin or end <= start:
            continue
        change += finish - begin
        covered += end - start
    return (change, covered) if covered else None


def _hold_mean(points: Points, intervals: list[Interval]) -> float | None:
    """Time-weighted mean where each sample holds until the next one."""
    total = weight = 0.0
    for start, end in intervals:
        for index, (t, v) in enumerate(points):
            until = points[index + 1][0] if index + 1 < len(points) else end
            lo, hi = max(t, start), min(until, end)
            if hi > lo:
                total += v * (hi - lo)
                weight += hi - lo
    return total / weight if weight else None


def _max_gap(samples: list[dict[str, Any]], intervals: list[Interval]) -> float | None:
    gap = None
    times = [s["t"] for s in samples]
    for start, end in intervals:
        before = [t for t in times if t <= start][-1:]
        after = [t for t in times if t >= end][:1]
        chain = before + [t for t in times if start < t < end] + after
        for earlier, later in pairwise(chain):
            gap = max(gap or 0.0, later - earlier)
    return gap


def _resource_metrics(
    samples: list[dict[str, Any]],
    intervals: list[Interval],
    target: dict[str, Any],
    window: str,
) -> dict[str, Any]:
    inside = _within(samples, intervals)
    reasons: dict[str, str] = {}
    for item in samples:
        for key, reason in item["errors"].items():
            reasons.setdefault(key, reason)

    def missing(key: str) -> dict[str, Any]:
        if key in reasons:
            return schema.unavailable(reasons[key])
        if not inside:
            return schema.unavailable(f"no samples during {window}")
        return schema.unavailable(f"{key} was not reported")

    def peak(key: str, scale: float, unit: str, source: str, pick: Callable[..., float]) -> Any:
        values = [v for _, v in _points(inside, key)]
        return _measured(pick(values) / scale, unit, source) if values else missing(key)

    def mean(key: str, scale: float, unit: str, source: str) -> Any:
        value = _hold_mean(_points(samples, key), intervals)
        covered = bool(_points(inside, key))
        return (
            _measured(value / scale, unit, source)
            if value is not None and covered
            else missing(key)
        )

    def delta(key: str, unit: str, source: str, per_second: bool, scale: float = 1.0) -> Any:
        change = _counter_change(_points(samples, key), intervals)
        if change is None or not inside:
            return missing(key)
        total, seconds = change
        return _measured((total / seconds if per_second else total) / scale, unit, source)

    def cpu_busy() -> Any:
        busy = _counter_change(_points(samples, "cpu_busy_ticks"), intervals)
        total = _counter_change(_points(samples, "cpu_total_ticks"), intervals)
        if busy is None or total is None or total[0] <= 0 or not inside:
            return missing("cpu_total_ticks")
        return _measured(100 * busy[0] / total[0], "%", "/proc/stat")

    memory_key = target.get("memory_key", "mem_bytes")
    memory = target.get("memory_label", "cgroup memory.current")
    cpu = target.get("cpu_label", "cgroup cpu.stat")
    sysfs = "amdgpu sysfs"
    gap = _max_gap(samples, intervals)
    return {
        "cpu_cores_avg": delta("cpu_usec", "cores", cpu, True, 1_000_000),
        "system_cpu_busy_percent": cpu_busy(),
        "ram_peak_gib": peak(memory_key, GIB, "GiB", memory, max),
        "ram_anon_peak_gib": peak("mem_anon_bytes", GIB, "GiB", f"{memory} anon", max),
        "ram_file_peak_gib": peak("mem_file_bytes", GIB, "GiB", f"{memory} file cache", max),
        "system_available_min_gib": peak(
            "sys_available_bytes", GIB, "GiB", "/proc/meminfo MemAvailable", min
        ),
        "vram_peak_gib": peak("vram_bytes", GIB, "GiB", f"{sysfs} mem_info_vram_used", max),
        "gtt_peak_gib": peak("gtt_bytes", GIB, "GiB", f"{sysfs} mem_info_gtt_used", max),
        "proc_vram_peak_gib": peak(
            "proc_vram_bytes", GIB, "GiB", "DRM fdinfo (drm-memory-vram)", max
        ),
        "gpu_busy_avg_percent": mean("gpu_busy_percent", 1, "%", f"{sysfs} gpu_busy_percent"),
        "gpu_power_avg_w": mean("gpu_power_uw", 1_000_000, "W", f"{sysfs} hwmon power1_average"),
        "gpu_temp_max_c": peak("gpu_temp_mc", 1000, "C", f"{sysfs} hwmon temp1_input", max),
        "swap_in_pages": delta("pswpin", "pages", "/proc/vmstat pswpin", False),
        "swap_out_pages": delta("pswpout", "pages", "/proc/vmstat pswpout", False),
        "sample_count": schema.measured(len(inside), "samples", "sampler"),
        "sample_max_gap_s": (
            _measured(gap, "s", "sampler")
            if gap is not None
            else schema.unavailable(f"fewer than two samples around {window}")
        ),
    }


IDLE_CPU_WARNING_PERCENT = 10.0
PHASE_ORDER = ("idle", "load", "settle", "loaded_idle", "unload")
SYSTEM_PHASE_METRICS = (
    "system_cpu_busy_percent",
    "system_available_min_gib",
    "vram_peak_gib",
    "gtt_peak_gib",
    "gpu_busy_avg_percent",
    "gpu_power_avg_w",
    "gpu_temp_max_c",
    "swap_in_pages",
    "swap_out_pages",
    "sample_count",
)
SERVER_PHASE_METRICS = (
    "cpu_cores_avg",
    "ram_peak_gib",
    "ram_anon_peak_gib",
    "ram_file_peak_gib",
    "proc_vram_peak_gib",
)
SYSTEM_ONLY_PHASES = ("idle", "unload")


def _phases(
    meta: dict[str, Any], samples: list[dict[str, Any]], target: dict[str, Any]
) -> list[dict[str, Any]]:
    recorded = dict(meta.get("phases", {}))
    if "idle" in meta and "idle" not in recorded:
        recorded["idle"] = {
            "start_s": meta["idle"]["start_s"],
            "end_s": meta["idle"]["end_s"],
            "status": "ok",
        }
    entries: dict[str, dict[str, Any]] = {}
    for name in [n for n in PHASE_ORDER if n in recorded]:
        item = recorded[name]
        window = [(item["start_s"], item["end_s"])]
        everything = _resource_metrics(samples, window, target, f"the {name} phase")
        names = SYSTEM_PHASE_METRICS + (() if name in SYSTEM_ONLY_PHASES else SERVER_PHASE_METRICS)
        metrics: dict[str, Any] = {
            "duration_s": _measured(item["end_s"] - item["start_s"], "s", CLIENT_SOURCE)
        }
        metrics.update({key: everything[key] for key in names})
        for key, value in item.get("measures", {}).items():
            metrics[key] = _measured(value, "s", CLIENT_SOURCE)
        entry: dict[str, Any] = {"id": name, "status": item.get("status", "ok")}
        if item.get("note"):
            entry["note"] = item["note"]
        entry["metrics"] = metrics
        entries[name] = entry
    idle, unload = entries.get("idle"), entries.get("unload")
    if idle and unload:
        for key, label, sign in (
            ("vram_peak_gib", "vram_vs_idle_gib", 1),
            ("system_available_min_gib", "available_ram_vs_idle_gib", -1),
        ):
            before, after = idle["metrics"][key]["value"], unload["metrics"][key]["value"]
            unload["metrics"][label] = (
                schema.unavailable(f"{key} was not measured in both phases")
                if before is None or after is None
                else _measured(sign * (after - before), "GiB", "unload minus idle phase")
            )
    return list(entries.values())


def build_results(raw: RawRun) -> dict[str, Any]:
    """Aggregate a run into a ``results.json`` document.

    Raises:
        ValueError: the aggregated document violates the result contract.
    """
    meta, samples = raw.meta, sorted(raw.samples, key=lambda s: s["t"])
    kind = meta["server"]["kind"]
    target = meta.get("target", {})
    document: dict[str, Any] = {
        "schema_version": meta["schema_version"],
        "suite_version": meta["suite_version"],
        "recipe": meta["recipe"],
        "run": meta["run"],
        "server": meta["server"],
    }
    if "policy" in meta:
        document["policy"] = meta["policy"]
    phases = _phases(meta, samples, target)
    boot = meta.get("boot")
    if boot is not None or phases:
        warnings = list((boot or {}).get("warnings", []))
        idle = next((p for p in phases if p["id"] == "idle"), None)
        busy = idle["metrics"]["system_cpu_busy_percent"]["value"] if idle else None
        if busy is not None and busy > IDLE_CPU_WARNING_PERCENT:
            warnings.append(
                f"System CPU was {busy:.1f}% busy during the idle phase; "
                "the machine may not have been quiet"
            )
        document["boot"] = {"metrics": dict((boot or {}).get("metrics", {})), "warnings": warnings}
    if phases:
        document["phases"] = phases
    document["functional"] = [
        r["functional"] for r in raw.requests if r.get("phase") == "functional"
    ]
    warmups = [r for r in raw.requests if r.get("phase") == "warmup"]
    if warmups or "warmup" in meta:
        warmup: dict[str, Any] = {
            "requests": len(warmups),
            "converged": bool(meta.get("warmup", {}).get("converged", False)),
        }
        if warmups:
            span = max(r["ended_s"] for r in warmups) - min(r["started_s"] for r in warmups)
            warmup["metrics"] = {"duration_s": _measured(span, "s", CLIENT_SOURCE)}
        document["warmup"] = warmup
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in raw.requests:
        if record.get("phase") == "case":
            grouped.setdefault(record["case"], []).append(record)
    document["cases"] = [_case_entry(case, records, kind) for case, records in grouped.items()]
    document["resources"] = []
    for case, records in grouped.items():
        intervals = [
            (r["started_s"], r["ended_s"])
            for r in records
            if r.get("status") == "ok" and "started_s" in r and "ended_s" in r
        ]
        if intervals:
            metrics = _resource_metrics(samples, intervals, target, "requests")
            document["resources"].append({"case": case, "metrics": metrics})
    schema.validate_results(document)
    return document
