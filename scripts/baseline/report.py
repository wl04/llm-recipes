"""Render baseline results as the markdown block of an experiment summary.

The block is a pure function of the result document, so a summary can be regenerated at any time.
Sizes are shown in GB, as elsewhere in the repository; the result document stores them in GiB.
"""

import html
from pathlib import Path
from typing import Any

from baseline import schema

MISSING = "—"
VISIBLE_OUTPUT = "first_visible_output_s"
PAIR_TITLE = "First output / visible (s)"
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
    if metric.get("unit") == "tokens":
        return f"{round(value):,}"
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
    columns = [
        (key, title)
        for key, title, always in CASE_COLUMNS
        if always or any(key in case.get("metrics", {}) for case in cases)
    ]
    if any(VISIBLE_OUTPUT in case.get("metrics", {}) for case in cases):
        columns = [
            (key, PAIR_TITLE if key == "first_output_s" else title) for key, title in columns
        ]
    return columns


def _case_value(case: dict[str, Any], key: str) -> str:
    metrics = case.get("metrics", {})
    if key == "first_output_s" and VISIBLE_OUTPUT in metrics:
        return f"{_number(metrics.get('first_output_s'))} / {_number(metrics.get(VISIBLE_OUTPUT))}"
    return _number(metrics.get(key))


def _cases(cases: list[dict[str, Any]]) -> list[str]:
    columns = _case_columns(cases)
    header = ["Case", "Status", "Runs", *(title for _, title in columns), "Finish"]
    rows = [
        [
            _cell(case["id"]),
            _cell(case["status"]),
            str(case["runs"]),
            *(_case_value(case, key) for key, _ in columns),
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


def _conversation(cases: list[dict[str, Any]]) -> list[str]:
    fresh = next((case for case in cases if case["id"] == "conversation-fresh"), None)
    reuse = [case for case in cases if case["id"].startswith("conversation-reuse-")]
    if fresh is None or not reuse:
        return []

    def line(case: dict[str, Any], tail: str) -> str:
        m = case.get("metrics", {})
        parts = [_cell(case["id"]), _number(m.get("first_output_s")) + " s first output"]
        if _has(m.get("cached_input_tokens")):
            parts.append(
                f"{int(m['cached_input_tokens']['value']):,} of "
                f"{int(m['input_tokens']['value']):,} tokens reported cached"
            )
        return "- " + ", ".join(parts) + tail

    lines = ["", "### Conversation reuse", "", line(fresh, " (full history, cold)")]
    lines += [line(case, "") for case in reuse]
    ratios = [
        case["metrics"]["cached_input_tokens"]["value"] / case["metrics"]["input_tokens"]["value"]
        for case in reuse
        if _has(case.get("metrics", {}).get("cached_input_tokens"))
        and _has(case.get("metrics", {}).get("input_tokens"))
        and case["metrics"]["input_tokens"]["value"]
    ]
    if ratios:
        lines += [
            "",
            f"Cache reuse: observed — up to {max(ratios) * 100:.0f}% of prompt tokens reported "
            "cached on the replay ladder.",
        ]
    else:
        note = "Cache reuse: unknown — the server reports no cached-token counts."
        fresh_first = fresh.get("metrics", {}).get("first_output_s")
        twin = next(
            (
                case
                for case in reuse
                if _has(case.get("metrics", {}).get("first_output_s"))
                and _has(case.get("metrics", {}).get("input_tokens"))
                and _has(fresh_first)
                and _has(fresh.get("metrics", {}).get("input_tokens"))
                and case["metrics"]["input_tokens"]["value"]
                == fresh["metrics"]["input_tokens"]["value"]
            ),
            None,
        )
        if twin is not None and fresh_first is not None and fresh_first["value"] > 0:
            cold = fresh_first["value"]
            warm = twin["metrics"]["first_output_s"]["value"]
            if warm <= 0.9 * cold:
                note += (
                    f" Replaying the identical prompt reached first output in {warm:.2f} s "
                    f"versus {cold:.2f} s cold — consistent with KV-cache reuse across requests."
                )
            elif warm >= 1.1 * cold:
                note += (
                    f" Replaying the identical prompt was slower, not faster ({warm:.2f} s "
                    f"versus {cold:.2f} s cold) — no reuse observed."
                )
            else:
                note += (
                    " Replaying the identical prompt changed time to first output by less "
                    "than 10% — no reuse observed."
                )
        lines += ["", note]
    return lines


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
    cases = document["cases"]
    shown_case_keys = {key for key, _ in _case_columns(cases)}
    if any(VISIBLE_OUTPUT in case.get("metrics", {}) for case in cases):
        shown_case_keys.add(VISIBLE_OUTPUT)
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
        f"Suite v{_cell(document['suite_version'])} · "
        f"run {_cell(run['status'])} · model `{_cell(server['model'])}` · "
        f"configured context {server['context_tokens']:,} tokens",
    ]
    if document.get("functional"):
        lines += _functional(document["functional"])
    if "boot" in document:
        lines += _boot(document["boot"])
    if "warmup" in document:
        lines += _warmup(document["warmup"])
    lines += _cases(document["cases"])
    lines += _conversation(document["cases"])
    if document.get("resources"):
        boot_metrics = document.get("boot", {}).get("metrics", {})
        lines += _resources(document["resources"], boot_metrics)
    lines += _unavailable(document)
    lines += ["", DEFINITIONS]
    return "\n".join(lines) + "\n"


SESSION_START = "<!-- BEGIN GENERATED SESSION -->"
SESSION_END = "<!-- END GENERATED SESSION -->"
UNAVAILABLE = "unavailable"


def _value(document: dict[str, Any], key: str, nested: str | None = None) -> Any:
    section: Any = document if nested is None else document.get(nested)
    return section.get(key) if isinstance(section, dict) else None


def _metric(value: object, digits: int = 1) -> str:
    if value is None:
        return MISSING
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.{digits}f}"


def _span(document: dict[str, Any]) -> str:
    first, last = _value(document, "first_request"), _value(document, "last_request")
    if not first or not last:
        return UNAVAILABLE
    return f"{first} → {last}"


def render_session(document: dict[str, Any]) -> str:
    """Render a validated session-results document as the summary's activity section."""
    availability = document["availability"]
    totals = document["totals"]
    window = document["window"]
    rows = [
        ["Requests completed", _metric(totals["requests"])],
        ["Cancelled", _metric(totals["cancelled"])],
        [
            "Started without result",
            _metric(totals["unclosed_requests"])
            if availability["unclosed_requests"]
            else UNAVAILABLE,
        ],
        ["Wall-clock span", _span(document)],
        ["Prompt tokens", _metric(totals["prompt_tokens"])],
        ["Reused prompt tokens", _metric(totals["reused_prompt_tokens"])],
        ["Fresh prefill tokens", _metric(totals["read_prompt_tokens"])],
        ["Generated tokens", _metric(totals["generated_tokens"])],
        ["Aggregate prefill (tok/s)", _metric(totals["prefill_tok_s"])],
        ["Aggregate decode (tok/s)", _metric(totals["decode_tok_s"])],
        ["Median decode (tok/s)", _metric(totals["decode_tok_s_median"])],
    ]
    if availability["draft_acceptance"]:
        acceptance = totals["draft_acceptance"]
        shown = MISSING if acceptance is None else f"{acceptance:.1%}"
        rows.append(
            [
                "Draft acceptance",
                f"{shown} ({totals['drafts_accepted']:,} / {totals['drafts_proposed']:,})",
            ]
        )
    else:
        rows.append(["Draft acceptance", UNAVAILABLE])
    lines = [
        "### Session activity",
        "",
        "Engine: `{}` · logs: {}".format(
            document["engine"], ", ".join(_cell(str(name)) for name in document["log_files"])
        ),
    ]
    if window["since"] or window["until"]:
        lines.append(f"Window: {window['since'] or 'start'} → {window['until'] or 'end'}")
    if not availability["timestamps"]:
        lines.append(
            "Timestamps: " + UNAVAILABLE + " — this engine logs no per-line times; "
            "wall-clock span and window filtering are not applicable."
        )
    lines += ["", *_table(["Metric", "Value"], rows), ""]
    buckets = totals["context_buckets"]
    if buckets:
        lines += [
            "### Request size distribution",
            "",
            *_table(
                ["Prompt context", "Requests", "Prompt tokens", "Generated tokens"],
                [
                    [
                        _cell(str(bucket["label"])),
                        _metric(bucket["requests"]),
                        _metric(bucket["prompt_tokens"]),
                        _metric(bucket["generated_tokens"]),
                    ]
                    for bucket in buckets
                ],
            ),
        ]
    return "\n".join(lines) + "\n"


def write_session_block(summary_path: Path, block: str) -> None:
    """Replace the generated session block in a summary, appending it when absent.

    Raises:
        ValueError: any marker present requires exactly one balanced pair.
    """
    text = summary_path.read_text()
    starts, ends = text.count(SESSION_START), text.count(SESSION_END)
    if starts == 0 and ends == 0:
        summary_path.write_text(
            text.rstrip()
            + "\n\n"
            + SESSION_START
            + "\n\n"
            + block.rstrip()
            + "\n"
            + SESSION_END
            + "\n"
        )
        return
    if starts != 1 or ends != 1:
        raise ValueError(f"{summary_path} must contain exactly one generated session block")
    if text.index(SESSION_START) > text.index(SESSION_END):
        raise ValueError(f"{summary_path} has session markers in the wrong order")
    before, middle = text.split(SESSION_START)
    _old, after = middle.split(SESSION_END)
    summary_path.write_text(
        before + SESSION_START + "\n\n" + block.rstrip() + "\n" + SESSION_END + after
    )
