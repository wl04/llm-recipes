"""Engine-reported timings from the server's own log.

Strata logs one line per completion with the prompt tokens read and generated, the time each
took, and the draft tokens accepted. These are engine measurements, kept separate from the client
timings. Lines are matched to the requests in order, and a mismatch stops the matching instead of
guessing.
"""

import re
from dataclasses import dataclass, field
from typing import Any

STRATA_LINE = re.compile(
    r"strata serve: prompt (\d+) tokens = (\d+) reused \+ (\d+) read in (\d+) ms "
    r"\([\d.]+ tok/s\), (\d+) generated in (\d+) ms \([\d.]+ tok/s\)"
    r"(?:, drafts accepted (\d+) of (\d+))?"
)
LOOKAHEAD = 3


@dataclass(frozen=True)
class EngineRequest:
    """One completion as the engine reports it."""

    prompt_tokens: int
    reused_tokens: int
    read_tokens: int
    prefill_ms: int
    generated_tokens: int
    decode_ms: int
    drafts_accepted: int | None
    drafts_proposed: int | None


def parse_strata(text: str) -> list[EngineRequest]:
    """Every per-completion line of a Strata engine log, in order."""
    found = []
    for match in STRATA_LINE.finditer(text):
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
            )
        )
    return found


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
