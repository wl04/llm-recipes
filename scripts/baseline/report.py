"""Render baseline results as the markdown block of an experiment summary."""

import html
from typing import Any

from baseline import schema

CASE_COLUMNS = (
    ("input_tokens", "Input tokens", True),
    ("output_tokens", "Output tokens", True),
    ("cached_input_tokens", "Cached input", False),
    ("first_output_s", "First output (s)", True),
    ("client_decode_tok_s", "Decode, client (tok/s)", True),
    ("engine_prefill_tok_s", "Prefill, engine (tok/s)", False),
    ("engine_decode_tok_s", "Decode, engine (tok/s)", False),
    ("draft_acceptance", "Draft acceptance", False),
)
RESOURCE_COLUMNS = (
    ("cpu_cores_avg", "CPU (cores)"),
    ("system_cpu_busy_percent", "System CPU busy (%)"),
    ("ram_peak_gib", "Peak RAM (GiB)"),
    ("ram_anon_peak_gib", "Peak anon RAM (GiB)"),
    ("ram_file_peak_gib", "Peak file cache (GiB)"),
    ("system_available_min_gib", "Min available RAM (GiB)"),
    ("vram_peak_gib", "Peak VRAM (GiB)"),
    ("gtt_peak_gib", "Peak GTT (GiB)"),
    ("proc_vram_peak_gib", "Peak process VRAM (GiB)"),
    ("gpu_busy_avg_percent", "GPU busy avg (%)"),
    ("gpu_power_avg_w", "GPU power avg (W)"),
    ("gpu_temp_max_c", "GPU temp max (°C)"),
    ("swap_in_pages", "Swap in (pages)"),
    ("swap_out_pages", "Swap out (pages)"),
    ("sample_count", "Samples"),
    ("sample_max_gap_s", "Max sample gap (s)"),
)
NOISE_LABELS = (
    ("noise_first_output_spread", "first output"),
    ("noise_decode_spread", "decode rate"),
)
PHASE_SYSTEM_DETAILS = (
    "ram_anon_peak_gib", "ram_file_peak_gib", "proc_vram_peak_gib", "gtt_peak_gib",
    "gpu_busy_avg_percent", "gpu_temp_max_c", "swap_in_pages", "swap_out_pages",
)  # fmt: skip
MISSING = "—"


def _cell(value: object) -> str:
    return html.escape(str(value), quote=False).replace("|", "&#124;").replace("\n", "<br>")


def _number(metric: dict[str, Any] | None) -> str:
    if metric is None or metric.get("value") is None:
        return MISSING
    value = metric["value"]
    if metric.get("unit") == "ratio":
        return f"{value:.1%}"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:.3f}" if abs(value) < 1 else f"{value:,.2f}"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _vision_details(entry: dict[str, Any]) -> str:
    scores = entry.get("scores")
    if not isinstance(scores, dict):
        return _cell(entry.get("detail", ""))
    parts = []
    for tier in ("identity", "detail"):
        counts = scores.get(tier, {})
        total = sum(counts.values())
        text = f"{tier} {counts.get('match', 0)}/{total}"
        misses = [
            f"{counts[outcome]} {outcome}"
            for outcome in ("mismatch", "missing")
            if counts.get(outcome)
        ]
        parts.append(text + (f" ({', '.join(misses)})" if misses else ""))
    return ", ".join(parts)


def _functional(entries: list[dict[str, Any]]) -> list[str]:
    rows = [[_cell(e["id"]), _cell(e["status"]), _vision_details(e)] for e in entries]
    return ["", "### Functional checks", "", *_table(["Check", "Status", "Details"], rows)]


def _boot(boot: dict[str, Any]) -> list[str]:
    rows = [
        [_cell(name), MISSING if metric["value"] is None else f"{_number(metric)} {metric['unit']}"]
        for name, metric in boot.get("metrics", {}).items()
    ]
    lines = ["", "### Boot state", ""]
    if rows:
        lines += [*_table(["Measurement", "Value"], rows), ""]
    lines += [f"- {_cell(note)}" for note in boot.get("warnings", [])]
    return lines


PHASE_COLUMNS = (
    ("duration_s", "Duration (s)"),
    ("system_cpu_busy_percent", "System CPU busy (%)"),
    ("cpu_cores_avg", "Server CPU (cores)"),
    ("ram_peak_gib", "Server RAM peak (GiB)"),
    ("system_available_min_gib", "System available min (GiB)"),
    ("vram_peak_gib", "VRAM peak (GiB)"),
    ("gpu_power_avg_w", "GPU power avg (W)"),
)


def _phases(phases: list[dict[str, Any]]) -> list[str]:
    shown = {key for key, _ in PHASE_COLUMNS}
    rows = [
        [
            _cell(phase["id"]),
            _cell(phase["status"]),
            *(_number(phase["metrics"].get(key)) for key, _ in PHASE_COLUMNS),
        ]
        for phase in phases
    ]
    header = ["Phase", "Status", *(title for _, title in PHASE_COLUMNS)]
    lines = ["", "### Phases", "", *_table(header, rows)]
    extras = []
    for phase in phases:
        if phase.get("note"):
            extras.append(f"- {_cell(phase['id'])}: {_cell(phase['note'])}")
        for key, metric in phase["metrics"].items():
            if key in shown or key.startswith("sample") or metric["value"] is None:
                continue
            if key in PHASE_SYSTEM_DETAILS:
                continue
            label = key.removesuffix("_s").removesuffix("_gib").replace("_", " ")
            extras.append(f"- {_cell(phase['id'])}: {label} {_number(metric)} {metric['unit']}")
    return lines + (["", *extras] if extras else [])


def _warmup(warmup: dict[str, Any]) -> list[str]:
    state = "converged" if warmup["converged"] else "did not converge"
    duration = warmup.get("metrics", {}).get("duration_s")
    tail = f", {_number(duration)} s" if duration and duration["value"] is not None else ""
    return ["", f"Warmup: {warmup['requests']} requests, {state}{tail}."]


def _cases(cases: list[dict[str, Any]]) -> list[str]:
    columns = [
        (key, title)
        for key, title, always in CASE_COLUMNS
        if always or any(key in case.get("metrics", {}) for case in cases)
    ]
    header = ["Case", "Status", "Runs", *(title for _, title in columns), "Finish", "Note"]
    rows = [
        [
            _cell(case["id"]),
            _cell(case["status"]),
            str(case["runs"]),
            *(_number(case.get("metrics", {}).get(key)) for key, _ in columns),
            _cell(case.get("finish_reason") or MISSING),
            _cell(case.get("note", "")),
        ]
        for case in cases
    ]
    lines = ["", "### Cases", "", *_table(header, rows)]
    noise = []
    for case in cases:
        parts = [
            f"{label} {_number(case['metrics'][key])}"
            for key, label in NOISE_LABELS
            if key in case.get("metrics", {})
        ]
        if parts:
            noise.append(
                f"- Noise floor, {_cell(case['id'])} ({case['runs']} runs): {', '.join(parts)} "
                "(range over median)."
            )
    return lines + (["", *noise] if noise else [])


def _resources(entries: list[dict[str, Any]]) -> list[str]:
    columns = [
        (key, title)
        for key, title in RESOURCE_COLUMNS
        if any(key in entry.get("metrics", {}) for entry in entries)
    ]
    rows = [
        [_cell(entry["case"]), *(_number(entry.get("metrics", {}).get(key)) for key, _ in columns)]
        for entry in entries
    ]
    return ["", "### Resources", "", *_table(["Case", *(t for _, t in columns)], rows)]


def _unavailable(document: dict[str, Any]) -> list[str]:
    grouped: dict[tuple[str, str], list[str]] = {}
    sources = [(f"{c['id']}", c.get("metrics", {})) for c in document["cases"]]
    sources += [(f"{r['case']}", r.get("metrics", {})) for r in document.get("resources", [])]
    for owner, metrics in sources:
        for name, metric in metrics.items():
            if metric["value"] is None:
                owners = grouped.setdefault((name, metric["unavailable"]), [])
                if owner not in owners:
                    owners.append(owner)
    reasons = [
        f"- {_cell(name)}: {_cell(reason)} ({_cell(', '.join(owners))})"
        for (name, reason), owners in grouped.items()
    ]
    return ["", "### Unavailable measurements", "", *reasons] if reasons else []


def render_results_block(document: dict[str, Any]) -> str:
    """Render the results section of an experiment summary.

    Raises:
        ValueError: the document violates the result contract.
    """
    schema.validate_results(document)
    run, server = document["run"], document["server"]
    lines = [
        "## Baseline results",
        "",
        f"suite {_cell(document['suite_version'])} · schema {document['schema_version']} · "
        f"run {_cell(run['status'])} · model `{_cell(server['model'])}` · "
        f"context {server['context_tokens']:,} tokens",
    ]
    if document.get("functional"):
        lines += _functional(document["functional"])
    if "boot" in document:
        lines += _boot(document["boot"])
    if document.get("phases"):
        lines += _phases(document["phases"])
    if "warmup" in document:
        lines += _warmup(document["warmup"])
    lines += _cases(document["cases"])
    if document.get("resources"):
        lines += _resources(document["resources"])
    lines += _unavailable(document)
    return "\n".join(lines) + "\n"
