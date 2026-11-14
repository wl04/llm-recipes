"""Render baseline results as the markdown block of an experiment summary.

The block is a pure function of the result document, so a summary can be regenerated at any time.
Sizes are shown in GB, as elsewhere in the repository; the result document stores them in GiB.
"""

import html
from typing import Any

from baseline import schema

MISSING = "—"
CASE_COLUMNS = (
    ("input_tokens", "Input tokens", True),
    ("output_tokens", "Output tokens", True),
    ("cached_input_tokens", "Cached input", False),
    ("first_output_s", "First output (s)", True),
    ("engine_prefill_tok_s", "Prefill (tok/s)", True),
    ("client_decode_tok_s", "Decode (tok/s)", True),
    ("draft_acceptance", "Draft acceptance", False),
)
NOISE_LABELS = (
    ("noise_first_output_spread", "first output"),
    ("noise_decode_spread", "decode rate"),
)
# (label, used metric, total metric, decimals); the total is empty for a single value.
BOOT_ROWS = (
    ("Uptime", "uptime_s", None, 0),
    ("RAM used / total (GB)", "mem_used_gib", "mem_total_gib", 1),
    ("Swap used / total (GB)", "swap_used_gib", "swap_total_gib", 1),
    ("GPU busy (%)", "gpu_busy_percent", None, 0),
    ("VRAM used / total (GB)", "gpu_vram_used_gib", "gpu_vram_total_gib", 1),
    ("GPU power (W)", "gpu_power_w", None, 2),
    ("GPU temperature (°C)", "gpu_temp_c", None, 0),
)
RESOURCE_SINGLES = (
    ("cpu_cores_avg", "Server CPU (cores)"),
    ("system_cpu_busy_percent", "System CPU busy (%)"),
)
RESOURCE_TAIL = (
    ("gpu_busy_avg_percent", "GPU busy (%)"),
    ("gpu_power_avg_w", "GPU power (W)"),
    ("gpu_temp_max_c", "GPU temp (°C)"),
)
RESOURCE_COUNTS = (("sample_count", "Samples"), ("sample_max_gap_s", "Max sample gap (s)"))
RESOURCE_DISPLAYED = (
    "cpu_cores_avg",
    "system_cpu_busy_percent",
    "ram_used_peak_gib",
    "vram_peak_gib",
    "gpu_busy_avg_percent",
    "gpu_power_avg_w",
    "gpu_temp_max_c",
    "swap_in_pages",
    "swap_out_pages",
    "sample_count",
    "sample_max_gap_s",
)
DEFINITIONS = (
    "Decode is a client estimate: (output tokens - 1) / (last - first output). Prefill is "
    "reported by the engine and is empty when the server reports none."
)


def _cell(value: object) -> str:
    return html.escape(str(value), quote=False).replace("|", "&#124;").replace("\n", "<br>")


def _has(metric: dict[str, Any] | None) -> bool:
    return metric is not None and metric.get("value") is not None


def _number(metric: dict[str, Any] | None) -> str:
    if not _has(metric):
        return MISSING
    assert metric is not None
    value = metric["value"]
    if metric.get("unit") == "ratio":
        return f"{value:.1%}"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:.3f}" if abs(value) < 1 else f"{value:,.2f}"


def _fixed(metric: dict[str, Any] | None, digits: int) -> str:
    return f"{metric['value']:,.{digits}f}" if metric is not None and _has(metric) else MISSING


def _uptime(metric: dict[str, Any] | None) -> str:
    if not _has(metric):
        return MISSING
    assert metric is not None
    minutes = int(metric["value"]) // 60
    if minutes == 0:
        return f"{int(metric['value'])} s"
    hours, minutes = divmod(minutes, 60)
    if hours == 0:
        return f"{minutes} min"
    return f"{hours} h" if minutes == 0 else f"{hours} h {minutes} min"


def _pair(used: dict[str, Any] | None, total: dict[str, Any] | None, digits: int) -> str:
    return f"{_fixed(used, digits)} / {_fixed(total, digits)}"


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
    metrics = boot.get("metrics", {})
    rows = []
    for label, used, total, digits in BOOT_ROWS:
        if used not in metrics and total not in metrics:
            continue
        if used == "uptime_s":
            value = _uptime(metrics.get(used))
        elif total is None:
            value = _fixed(metrics.get(used), digits)
        else:
            value = _pair(metrics.get(used), metrics.get(total), digits)
        rows.append([label, value])
    lines = ["", "### Boot state", ""]
    if rows:
        lines += _table(["Measurement", "Value"], rows)
    warnings = [f"- {_cell(note)}" for note in boot.get("warnings", [])]
    return lines + (["", *warnings] if warnings else [])


def _warmup(warmup: dict[str, Any]) -> list[str]:
    state = "converged" if warmup["converged"] else "did not converge"
    duration = warmup.get("metrics", {}).get("duration_s")
    tail = f", {_number(duration)} s" if _has(duration) else ""
    return ["", f"Warmup: {warmup['requests']} requests, {state}{tail}."]


def _case_columns(cases: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [
        (key, title)
        for key, title, always in CASE_COLUMNS
        if always or any(key in case.get("metrics", {}) for case in cases)
    ]


def _cases(cases: list[dict[str, Any]]) -> list[str]:
    columns = _case_columns(cases)
    header = ["Case", "Status", "Runs", *(title for _, title in columns), "Finish"]
    rows = [
        [
            _cell(case["id"]),
            _cell(case["status"]),
            str(case["runs"]),
            *(_number(case.get("metrics", {}).get(key)) for key, _ in columns),
            _cell(case.get("finish_reason") or MISSING),
        ]
        for case in cases
    ]
    lines = ["", "### Cases", "", *_table(header, rows)]
    extras = []
    for case in cases:
        parts = [
            f"{label} {_number(case['metrics'][key])}"
            for key, label in NOISE_LABELS
            if key in case.get("metrics", {})
        ]
        if parts:
            extras.append(
                f"- Noise floor, {_cell(case['id'])} ({case['runs']} runs): {', '.join(parts)} "
                "(range over median)."
            )
    extras += [f"- {_cell(c['id'])}: {_cell(c['note'])}" for c in cases if c.get("note")]
    return lines + (["", *extras] if extras else [])


def _resources(entries: list[dict[str, Any]], boot_metrics: dict[str, Any]) -> list[str]:
    ram_total = boot_metrics.get("mem_total_gib")
    vram_total = boot_metrics.get("gpu_vram_total_gib")
    header = [
        "Case",
        *(title for _, title in RESOURCE_SINGLES),
        "RAM peak / total (GB)",
        "VRAM peak / total (GB)",
        *(title for _, title in RESOURCE_TAIL),
        "Swap in / out (pages)",
        *(title for _, title in RESOURCE_COUNTS),
    ]
    rows = []
    for entry in entries:
        m = entry.get("metrics", {})
        rows.append(
            [
                _cell(entry["case"]),
                *(_number(m.get(key)) for key, _ in RESOURCE_SINGLES),
                _pair(m.get("ram_used_peak_gib"), ram_total, 1),
                _pair(m.get("vram_peak_gib"), vram_total, 1),
                *(_number(m.get(key)) for key, _ in RESOURCE_TAIL),
                f"{_number(m.get('swap_in_pages'))} / {_number(m.get('swap_out_pages'))}",
                *(_number(m.get(key)) for key, _ in RESOURCE_COUNTS),
            ]
        )
    return ["", "### Resources", "", *_table(header, rows)]


def _unavailable(document: dict[str, Any]) -> list[str]:
    shown_case_keys = {key for key, _ in _case_columns(document["cases"])}
    shown_case_keys |= {key for key, _ in NOISE_LABELS}
    grouped: dict[tuple[str, str], list[str]] = {}
    sources = [(case["id"], case.get("metrics", {}), shown_case_keys) for case in document["cases"]]
    sources += [
        (entry["case"], entry.get("metrics", {}), set(RESOURCE_DISPLAYED))
        for entry in document.get("resources", [])
    ]
    for owner, metrics, shown in sources:
        for name, metric in metrics.items():
            if name in shown and metric["value"] is None:
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
    if "warmup" in document:
        lines += _warmup(document["warmup"])
    lines += _cases(document["cases"])
    if document.get("resources"):
        boot_metrics = document.get("boot", {}).get("metrics", {})
        lines += _resources(document["resources"], boot_metrics)
    lines += _unavailable(document)
    lines += ["", DEFINITIONS]
    return "\n".join(lines) + "\n"
