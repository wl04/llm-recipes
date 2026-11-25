"""Deterministic coding-session statistics from instance logs.

Session reports need no client request list: the engine log alone states prompt
processing, generation, draft counters, and cancellations. Metrics a server's log
cannot provide are reported as unavailable instead of guessed.
"""

import re
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

from baseline import engine_log
from baseline.engine_log import EngineRequest

ENGINE_KINDS = ("tabbyapi", "strata", "lm-studio")

# Reviewed prompt-size bands; a request is counted in the first band it fits into.
CONTEXT_BUCKETS: tuple[tuple[int, str], ...] = (
    (2_048, "under 2,048 tokens"),
    (8_192, "2,048-8,191 tokens"),
    (32_768, "8,192-32,767 tokens"),
    (131_072, "32,768-131,071 tokens"),
)
LARGEST_BUCKET = "131,072 tokens and above"


def filter_window(
    entries: list[EngineRequest],
    since: datetime | None,
    until: datetime | None,
) -> list[EngineRequest]:
    """Keep entries inside a wall-clock window.

    Raises:
        ValueError: a window was requested but the engine log carries no timestamps.
    """
    if since is None and until is None:
        return entries
    timestamped = [entry for entry in entries if entry.timestamp is not None]
    if timestamped and len(timestamped) != len(entries):
        raise ValueError("the log mixes timestamped and timestampless lines; cannot filter")
    if not timestamped:
        raise ValueError("the engine log has no timestamps; run without --since/--until")
    kept: list[EngineRequest] = []
    for entry in entries:
        moment = entry.timestamp
        if moment is None:
            continue
        if (since is None or moment >= since) and (until is None or moment <= until):
            kept.append(entry)
    return kept


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _decode_rate(entry: EngineRequest) -> float | None:
    if entry.decode_ms > 0 and entry.generated_tokens > 0:
        return entry.generated_tokens / (entry.decode_ms / 1000)
    return None


def context_buckets(entries: list[EngineRequest]) -> list[dict[str, object]]:
    """Per-request prompt-size distribution across reviewed bands."""
    labels = [*[label for _limit, label in CONTEXT_BUCKETS], LARGEST_BUCKET]
    counts = {label: {"requests": 0, "prompt": 0, "generated": 0} for label in labels}
    for entry in entries:
        label = next(
            (label for limit, label in CONTEXT_BUCKETS if entry.prompt_tokens < limit),
            LARGEST_BUCKET,
        )
        counts[label]["requests"] += 1
        counts[label]["prompt"] += entry.prompt_tokens
        counts[label]["generated"] += entry.generated_tokens
    return [
        {
            "label": label,
            "requests": counts[label]["requests"],
            "prompt_tokens": counts[label]["prompt"],
            "generated_tokens": counts[label]["generated"],
        }
        for label in labels
        if counts[label]["requests"]
    ]


def session_stats(
    entries: list[EngineRequest],
    *,
    engine: str,
    since: datetime | None = None,
    until: datetime | None = None,
    unclosed: int | None = None,
    log_files: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Assemble the ``session-results.json`` document from parsed engine entries."""
    completed = [entry for entry in entries if not entry.cancelled]
    cancelled = sum(1 for entry in entries if entry.cancelled)
    timestamps = [entry.timestamp for entry in completed if entry.timestamp is not None]
    rates = [rate for rate in (_decode_rate(entry) for entry in completed) if rate is not None]
    drafts = [
        entry for entry in completed if entry.drafts_accepted is not None and entry.drafts_proposed
    ]
    accepted = sum(entry.drafts_accepted or 0 for entry in drafts)
    proposed = sum(entry.drafts_proposed or 0 for entry in drafts)
    prompt = sum(entry.prompt_tokens for entry in completed)
    reused = sum(entry.reused_tokens for entry in completed)
    read = sum(entry.read_tokens for entry in completed)
    generated = sum(entry.generated_tokens for entry in completed)
    prefill_seconds = sum(entry.prefill_ms for entry in completed) / 1000
    decode_seconds = sum(entry.decode_ms for entry in completed) / 1000
    timestamped = bool(timestamps)
    return {
        "schema_version": 1,
        "kind": "session",
        "engine": engine,
        "log_files": list(log_files),
        "window": {
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
        },
        "first_request": min(timestamps).isoformat() if timestamps else None,
        "last_request": max(timestamps).isoformat() if timestamps else None,
        "availability": {
            "timestamps": timestamped,
            "draft_acceptance": bool(drafts),
            "unclosed_requests": unclosed is not None,
        },
        "totals": {
            "requests": len(completed),
            "cancelled": cancelled,
            "unclosed_requests": unclosed,
            "prompt_tokens": prompt,
            "reused_prompt_tokens": reused,
            "read_prompt_tokens": read,
            "generated_tokens": generated,
            "prefill_seconds": _rounded(prefill_seconds),
            "decode_seconds": _rounded(decode_seconds),
            "prefill_tok_s": _rounded(read / prefill_seconds if read and prefill_seconds else None),
            "decode_tok_s": _rounded(
                generated / decode_seconds if generated and decode_seconds else None
            ),
            "decode_tok_s_median": _rounded(median(rates)) if rates else None,
            "drafts_accepted": accepted if drafts else None,
            "drafts_proposed": proposed if drafts else None,
            "draft_acceptance": accepted / proposed if proposed else None,
            "context_buckets": context_buckets(completed),
        },
    }


STRATA_MARKERS = ("engine.log", "server.log")
LMSTUDIO_FILE = re.compile(r"\d{4}-\d{2}-\d{2}\.\d+\.log")


def read_engine_logs(
    log_dir: Path, engine: str | None = None
) -> tuple[str, list[EngineRequest], int | None, tuple[str, ...], dict[str, object] | None]:
    """Parse every ``*.log`` file of an instance log directory.

    The engine defaults to the file layout: Strata names its logs ``engine.log`` and
    ``server.log``, LM Studio rotates dated files into month directories. Returns the
    engine, entries in file order, Tabby-only unclosed request ids (None otherwise),
    the file paths read relative to the directory, and sampler parameters the engine
    echoed to its log.

    Raises:
        ValueError: the directory has no ``.log`` files or the engine is unknown.
    """
    files = sorted(p for p in log_dir.iterdir() if p.is_file() and p.suffix == ".log")
    if not files:
        files = sorted(p for p in log_dir.rglob("*.log") if p.is_file())
    if not files:
        raise ValueError(f"{log_dir} contains no .log files")
    names = tuple(p.relative_to(log_dir).as_posix() for p in files)
    if engine is None:
        if any(name in STRATA_MARKERS for name in names):
            chosen = "strata"
        elif any(LMSTUDIO_FILE.fullmatch(name.rsplit("/", 1)[-1]) for name in names):
            chosen = "lm-studio"
        else:
            chosen = "tabbyapi"
    else:
        chosen = engine
    if chosen not in ENGINE_KINDS:
        raise ValueError(f"engine must be one of {', '.join(ENGINE_KINDS)}")
    parse = {
        "strata": engine_log.parse_strata,
        "lm-studio": engine_log.parse_lmstudio,
        "tabbyapi": engine_log.parse_tabbyapi,
    }[chosen]
    entries: list[EngineRequest] = []
    unclosed = 0
    texts: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        texts.append(text)
        entries.extend(parse(text))
        if chosen == "tabbyapi":
            unclosed += len(engine_log.tabby_unclosed_requests(text))
    joined = "\n".join(texts)
    if chosen == "tabbyapi":
        sampling = engine_log.tabby_sampling_from_log(joined)
    elif chosen == "lm-studio":
        sampling = engine_log.lmstudio_sampling_from_log(joined)
    else:
        sampling = engine_log.strata_sampling_from_log(joined)
    return chosen, entries, (unclosed if chosen == "tabbyapi" else None), names, sampling
