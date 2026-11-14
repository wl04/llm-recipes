"""Engine timings read from the server's own log and matched to the requests."""

from typing import Any

import pytest
from baseline import engine_log

LOG = """\
strata serve: prompt chunk auto: 8192 tokens, a 192-slot ring
strata serve: prompt 24 tokens = 0 reused + 24 read in 315 ms (76.3 tok/s), 120 generated in 1233 ms (97.3 tok/s), drafts accepted 86 of 94, 1 checkpoints
strata serve: decode expert cache hit rate: 54.6% (27511 hits / 50432 lookups)
strata serve: prompt 8013 tokens = 0 reused + 8013 read in 2500 ms (3205.2 tok/s), 1024 generated in 11000 ms (93.1 tok/s), drafts accepted 600 of 900, 1 checkpoints
strata serve: prompt 40 tokens = 10 reused + 30 read in 100 ms (300.0 tok/s), 5 generated in 50 ms (100.0 tok/s), 1 checkpoints
"""


def request(tokens: int | None, status: str = "ok", **extra: Any) -> dict[str, Any]:
    usage = None if tokens is None else {"prompt_tokens": tokens, "completion_tokens": 5}
    return {"phase": "case", "case": "c", "status": status, "usage": usage, **extra}


def test_parse_strata_reads_every_prompt_line_and_skips_other_lines() -> None:
    records = engine_log.parse_strata(LOG)

    assert [r.prompt_tokens for r in records] == [24, 8013, 40]
    first = records[0]
    assert (first.reused_tokens, first.read_tokens, first.prefill_ms) == (0, 24, 315)
    assert (first.generated_tokens, first.decode_ms) == (120, 1233)
    assert (first.drafts_accepted, first.drafts_proposed) == (86, 94)


def test_parse_strata_leaves_draft_counts_empty_when_the_line_has_none() -> None:
    last = engine_log.parse_strata(LOG)[-1]

    assert (last.reused_tokens, last.read_tokens) == (10, 30)
    assert last.drafts_accepted is None and last.drafts_proposed is None


def test_parse_strata_returns_nothing_for_an_unrelated_log() -> None:
    assert engine_log.parse_strata("starting\nloading the model\n") == []


def test_align_matches_requests_to_log_lines_by_prompt_tokens() -> None:
    records = [request(24), request(8013), request(40)]

    aligned = engine_log.align(records, engine_log.parse_strata(LOG))

    assert aligned.reason is None
    assert [aligned.by_record[id(r)][0].prompt_tokens for r in records] == [24, 8013, 40]


def test_align_consumes_several_lines_for_a_check_made_of_several_requests() -> None:
    check = {"phase": "functional", "case": "tools", "requests": 2, "status": "ok"}
    records = [check, request(40)]
    engine = engine_log.parse_strata(LOG)[:2] + engine_log.parse_strata(LOG)[2:]

    aligned = engine_log.align(records, engine[:3])

    assert len(aligned.by_record[id(check)]) == 2
    assert aligned.by_record[id(records[1])][0].prompt_tokens == 40


def test_align_skips_a_log_line_that_belongs_to_a_failed_request() -> None:
    failed = request(None, status="failed", error="stream broke")
    records = [failed, request(8013)]
    engine = engine_log.parse_strata(LOG)[:2]

    aligned = engine_log.align(records, engine)

    assert aligned.reason is None
    assert aligned.by_record[id(records[1])][0].prompt_tokens == 8013


def test_align_reports_a_mismatch_and_stops_matching() -> None:
    records = [request(24), request(9999), request(40)]

    aligned = engine_log.align(records, engine_log.parse_strata(LOG))

    assert id(records[0]) in aligned.by_record
    assert id(records[1]) not in aligned.by_record
    assert id(records[2]) not in aligned.by_record
    assert "9999" in (aligned.reason or "")


def test_align_reports_a_log_that_ends_early() -> None:
    records = [request(24), request(8013), request(40), request(7)]

    aligned = engine_log.align(records, engine_log.parse_strata(LOG))

    assert "ended" in (aligned.reason or "")
    assert id(records[3]) not in aligned.by_record


def test_align_ignores_skipped_records() -> None:
    skipped = {"phase": "case", "case": "big", "status": "skipped"}

    aligned = engine_log.align([skipped, request(24)], engine_log.parse_strata(LOG))

    assert aligned.reason is None


def test_summarize_aggregates_total_tokens_over_total_time() -> None:
    records = engine_log.parse_strata(LOG)[:2]

    summary = engine_log.summarize(records)

    assert summary.prefill_tok_s == pytest.approx((24 + 8013) / (0.315 + 2.5))
    assert summary.decode_tok_s == pytest.approx((120 + 1024) / (1.233 + 11.0))
    assert summary.draft_acceptance == pytest.approx((86 + 600) / (94 + 900))


def test_summarize_reports_no_draft_acceptance_without_draft_counts() -> None:
    summary = engine_log.summarize(engine_log.parse_strata(LOG)[2:])

    assert summary.draft_acceptance is None
    assert summary.prefill_tok_s == pytest.approx(30 / 0.1)


def test_parse_tabbyapi_reads_captured_completions() -> None:
    from pathlib import Path

    text = (Path(__file__).parent / "fixtures/tabbyapi/completions.log").read_text()
    records = engine_log.parse_tabbyapi(text)
    assert len(records) == 20
    assert records[8].prompt_tokens == 9372
    assert records[8].drafts_accepted == 674
    assert records[8].drafts_proposed == 2450
    assert records[2].reused_tokens == 256
    assert records[-1].prefill_ms == 114900
    assert engine_log.summarize(records[-2:]).draft_acceptance == pytest.approx(1374 / 4718)
