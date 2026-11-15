"""Engine-reported timings from the server's own log.

Strata and TabbyAPI log per-completion prompt processing, generation, and draft counters.
These are kept separate from client timings. Entries are matched to requests in order;
a mismatch stops matching instead of guessing. TabbyAPI rates and durations are rounded.

File logs may carry a per-line timestamp prefix; entries record it when present and
``None`` otherwise. Cancelled completions are kept as entries so session reports can
account for them without a client-side request list.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

STRATA_LINE = re.compile(
    r"strata serve: prompt (\d+) tokens = (\d+) reused \+ (\d+) read in (\d+) ms "
    r"\([\d.]+ tok/s\), (\d+) generated in (\d+) ms \([\d.]+ tok/s\)"
    r"(?:, drafts accepted (\d+) of (\d+))?"
)
LOOKAHEAD = 3

LINE_TIMESTAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)")


def line_timestamp(text: str) -> datetime | None:
    """Parse the leading timestamp of a log line; file logs may omit it entirely."""
    match = LINE_TIMESTAMP.match(text)
    return datetime.fromisoformat(match[1]) if match else None


@dataclass(frozen=True)
class EngineRequest:
    """One completion as the engine reports it."""

    prompt_tokens: int
    reused_tokens: int
    read_tokens: int
    prefill_ms: float
    generated_tokens: int
    decode_ms: float
    drafts_accepted: int | None
    drafts_proposed: int | None
    sequence: int | None = None
    timestamp: datetime | None = None
    cancelled: bool = False


STRATA_CANCELLED_LINE = re.compile(r"\[strata\] done: .* \(\w+, cancel=True\)")


def parse_strata(text: str) -> list[EngineRequest]:
    """Strata engine and server log lines, in order.

    ``engine.log`` per-completion lines become full entries; ``server.log`` lines that
    report a cancelled generation become cancelled entries. Lines carrying neither
    marker are ignored.
    """
    found = []
    for line in text.splitlines():
        match = STRATA_LINE.search(line)
        timestamp = line_timestamp(line)
        if match is not None:
            values = match.groups()
            accepted, proposed = values[6], values[7]
            found.append(
                EngineRequest(
                    int(values[0]),
                    int(values[1]),
                    int(values[2]),
                    int(values[3]),
                    int(values[4]),
                    int(values[5]),
                    None if accepted is None else int(accepted),
                    None if proposed is None else int(proposed),
                    timestamp=timestamp,
                )
            )
        elif STRATA_CANCELLED_LINE.search(line):
            found.append(
                EngineRequest(0, 0, 0, 0.0, 0, 0.0, None, None, timestamp=timestamp, cancelled=True)
            )
    return found


TABBY_LINE = re.compile(
    r"#(\d+) chat/completions(?: \(stream\))?: ([\d,]+) tokens generated at "
    r"([\d.]+) T/s · prompt ([\d,]+) tokens, .*?, ([\d,]+) new in "
    r"([\d.]+) s.*? · first token .*?, total .*? s"
    r"(?: · draft ([\d,]+)/([\d,]+) accepted \(\d+%\))?"
)
TABBY_CANCELLED_LINE = re.compile(r"#(\d+) chat/completions.*: client disconnected")
TABBY_STARTED_LINE = re.compile(r"#(\d+) chat/completions(?: \(stream\))?: [\d,]+ prompt tokens")


def parse_tabbyapi(text: str) -> list[EngineRequest]:
    """Read TabbyAPI completion summaries; decode time derives from its rounded rate.

    Completion summaries become full entries; ``client disconnected, generation
    cancelled`` lines become cancelled entries with the request id attached.
    """
    found = []
    for line in text.splitlines():
        cancelled = TABBY_CANCELLED_LINE.search(line)
        if cancelled is not None:
            found.append(
                EngineRequest(
                    0,
                    0,
                    0,
                    0.0,
                    0,
                    0.0,
                    None,
                    None,
                    sequence=int(cancelled[1]),
                    timestamp=line_timestamp(line),
                    cancelled=True,
                )
            )
            continue
        match = TABBY_LINE.search(line)
        if match is None:
            continue
        sequence, generated, rate, prompt, read, seconds, accepted, proposed = match.groups()

        def count(value: str) -> int:
            return int(value.replace(",", ""))

        if float(rate) <= 0:
            continue
        found.append(
            EngineRequest(
                count(prompt),
                count(prompt) - count(read),
                count(read),
                float(seconds) * 1000,
                count(generated),
                count(generated) / float(rate) * 1000,
                count(accepted) if accepted is not None else None,
                count(proposed) if proposed is not None else None,
                sequence=int(sequence),
                timestamp=line_timestamp(line),
            )
        )
    return found


def tabby_unclosed_requests(text: str) -> list[int]:
    """Request ids that TabbyAPI started but never finished or explicitly cancelled."""
    completed = {
        int(match[1])
        for line in text.splitlines()
        for pattern in (TABBY_LINE, TABBY_CANCELLED_LINE)
        for match in [pattern.search(line)]
        if match is not None
    }
    started = [
        int(match[1]) for line in text.splitlines() if (match := TABBY_STARTED_LINE.search(line))
    ]
    return [sequence for sequence in started if sequence not in completed]


SAMPLING_PARAMETERS = (
    "temperature",
    "top_k",
    "top_p",
    "min_p",
    "repetition_penalty",
    "presence_penalty",
)
TABBY_SAMPLING_LINE = re.compile(
    r"Sampler overrides \(inline\): temperature ([\d.]+), top_k ([\d,]+), top_p ([\d.]+), "
    r"min_p ([\d.]+), repetition_penalty ([\d.]+), presence_penalty ([\d.]+)"
)
STRATA_SAMPLING_LINE = re.compile(
    r"\[strata\] sampling defaults from the config: temperature=([\d.]+), top_k=([\d,]+), "
    r"top_p=([\d.]+), min_p=([\d.]+), repetition_penalty=([\d.]+), presence_penalty=([\d.]+)"
)


def _count_or_float(value: str) -> int | float:
    number = float(value.replace(",", ""))
    return int(number) if number.is_integer() else number


def _sampling_from(match: re.Match[str] | None) -> dict[str, object] | None:
    if match is None:
        return None
    values = [_count_or_float(value) for value in match.groups()]
    return dict(zip(SAMPLING_PARAMETERS, values, strict=True))


def tabby_sampling_from_log(text: str) -> dict[str, object] | None:
    """Inline sampler overrides as TabbyAPI reported them; None if never logged."""
    for line in reversed(text.splitlines()):
        found = _sampling_from(TABBY_SAMPLING_LINE.search(line))
        if found is not None:
            return found
    return None


def strata_sampling_from_log(text: str) -> dict[str, object] | None:
    """Config sampling defaults as Strata echoed them; None if never logged."""
    for line in reversed(text.splitlines()):
        found = _sampling_from(STRATA_SAMPLING_LINE.search(line))
        if found is not None:
            return found
    return None


@dataclass
class Alignment:
    """Engine entries per request record (keyed by ``id``), and why matching stopped, if it did."""

    by_record: dict[int, list[EngineRequest]] = field(default_factory=dict)
    reason: str | None = None


def align(records: list[dict[str, Any]], engine: list[EngineRequest]) -> Alignment:
    """Match successful requests to engine entries in order.

    A request with a known prompt size must match the next entries within a short lookahead;
    skipped lines belong to failed requests, which leave no usable record. A request without a
    known size (a functional check) takes as many entries as it made requests.
    """
    result = Alignment()
    cursor = 0
    for record in records:
        if record.get("status") != "ok":
            continue
        count = record.get("requests", 1)
        expected = (record.get("usage") or {}).get("prompt_tokens") if count == 1 else None
        name = record.get("case", "?")
        if expected is not None:
            window = range(cursor, min(cursor + LOOKAHEAD, len(engine)))
            found = next((k for k in window if engine[k].prompt_tokens == expected), None)
            if found is None:
                result.reason = (
                    f"the engine log ended before {name}"
                    if cursor >= len(engine)
                    else f"the engine log does not show {expected} prompt tokens for {name}"
                )
                return result
            result.by_record[id(record)] = [engine[found]]
            cursor = found + 1
        else:
            end = cursor + count
            if end > len(engine):
                result.reason = f"the engine log ended before {name}"
                return result
            result.by_record[id(record)] = engine[cursor:end]
            cursor = end
    return result


@dataclass(frozen=True)
class Summary:
    """Totals over several completions: tokens divided by time, accepted over proposed."""

    prefill_tok_s: float | None
    decode_tok_s: float | None
    draft_acceptance: float | None


def summarize(requests: list[EngineRequest]) -> Summary:
    read = sum(r.read_tokens for r in requests)
    prefill_s = sum(r.prefill_ms for r in requests) / 1000
    generated = sum(r.generated_tokens for r in requests)
    decode_s = sum(r.decode_ms for r in requests) / 1000
    counted = [r for r in requests if r.drafts_accepted is not None and r.drafts_proposed]
    proposed = sum(r.drafts_proposed or 0 for r in counted)
    return Summary(
        read / prefill_s if read and prefill_s > 0 else None,
        generated / decode_s if generated and decode_s > 0 else None,
        sum(r.drafts_accepted or 0 for r in counted) / proposed if proposed else None,
    )
