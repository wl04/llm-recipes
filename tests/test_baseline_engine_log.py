"""Engine timings read from the server's own log and matched to the requests."""

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from baseline import engine_log

FIXTURES = Path(__file__).parent / "fixtures"

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
    text = (FIXTURES / "tabbyapi/completions.log").read_text()
    records = engine_log.parse_tabbyapi(text)
    assert len(records) == 20
    assert records[8].prompt_tokens == 9372
    assert records[8].drafts_accepted == 674
    assert records[8].drafts_proposed == 2450
    assert records[2].reused_tokens == 256
    assert records[-1].prefill_ms == 114900
    assert engine_log.summarize(records[-2:]).draft_acceptance == pytest.approx(1374 / 4718)


def test_parse_tabbyapi_extracts_sequence_and_timestamp_from_timestamped_lines() -> None:
    text = (FIXTURES / "tabbyapi/completions.timestamped.log").read_text()

    records = engine_log.parse_tabbyapi(text)

    completions = [record for record in records if not record.cancelled]
    assert len(completions) == 20
    assert completions[0].sequence == 3
    assert completions[0].timestamp == datetime(2026, 11, 15, 0, 12, 36, 530000)
    assert all(record.timestamp is not None for record in completions)


def test_parse_tabbyapi_marks_cancelled_requests() -> None:
    text = (FIXTURES / "tabbyapi/completions.timestamped.log").read_text()

    cancelled = [r for r in engine_log.parse_tabbyapi(text) if r.cancelled]

    assert [record.sequence for record in cancelled] == [23]
    assert cancelled[0].timestamp == datetime(2026, 11, 15, 0, 42, 36, 530000)


def test_parse_tabbyapi_finds_unclosed_request_ids() -> None:
    text = (FIXTURES / "tabbyapi/completions.timestamped.log").read_text()

    assert engine_log.tabby_unclosed_requests(text) == []


def test_parse_tabbyapi_unclosed_reports_started_requests_without_summary() -> None:
    text = (
        "2026-11-15 10:00:00.100 | INFO | #7 chat/completions (stream): 512 prompt tokens\n"
        "2026-11-15 10:00:09.900 | INFO | #8 chat/completions (stream): 512 prompt tokens\n"
        "2026-11-15 10:00:20.000 | INFO | #8 chat/completions (stream): 40 tokens generated at "
        "90.0 T/s · prompt 512 tokens, none cached, 512 new in 1.0 s · first token 1.0 s, "
        "total 2.0 s\n"
    )

    assert engine_log.tabby_unclosed_requests(text) == [7]


def test_parse_strata_flags_cancelled_generations() -> None:
    text = (
        "[strata] done: 122 tokens in 2 s (98.3 tok/s) (stop, cancel=False), expert cache hit\n"
        "[strata] done: 5 tokens in 1 s (5.0 tok/s) (user_cancel, cancel=True), expert cache\n"
    )

    entries = engine_log.parse_strata(text)

    assert len(entries) == 1
    assert entries[0].cancelled


def test_parse_strata_records_timestamps_when_lines_carry_them() -> None:
    line = (
        "2026-11-15 08:00:00 strata serve: prompt 100 tokens = 20 reused + 80 read in 40 ms "
        "(2000.0 tok/s), 10 generated in 200 ms (50.0 tok/s)"
    )

    entries = engine_log.parse_strata(line)

    assert entries[0].timestamp == datetime(2026, 11, 15, 8, 0)
    assert entries[0].read_tokens == 80


LMSTUDIO_LOG = """\
[2026-11-15 00:44:28][INFO][LM STUDIO SERVER] Success! HTTP server listening on port 1234
[2026-11-15 00:44:39][DEBUG] Received request: POST to /v1/chat/completions with body {
  "model": "qwen3.8-27b-gsq-rco",
  "messages": [
    {
      "role": "user",
      "content": "Say hi. }"
    }
  ],
  "max_tokens": 8,
  "temperature": 0,
  "top_k": 20,
  "top_p": 0.95,
  "min_p": 0,
  "repetition_penalty": 1,
  "presence_penalty": 0,
  "stream": true
}
[2026-11-15 00:44:39][DEBUG] 2.22.343.603 I slot get_availabl: id  0 | task -1 | selected slot by LRU
[2026-11-15 00:44:39][DEBUG] 2.22.374.417 I slot launch_slot_: id  0 | task 27 | processing task
[2026-11-15 00:44:39][INFO][qwen3.8-27b-gsq-rco] Prompt processing progress: 100.0%
[2026-11-15 00:44:42][DEBUG] 2.24.841.586 I slot print_timing: id  0 | task 27 | prompt eval time =     275.45 ms /    55 tokens (    5.01 ms per token,   199.67 tokens per second)
2.24.841.588 I slot print_timing: id  0 | task 27 |        eval time =    2191.61 ms /     8 tokens (  313.09 ms per token,     3.19 tokens per second)
2.24.841.589 I slot print_timing: id  0 | task 27 |       total time =    2467.06 ms /    63 tokens
2.24.841.592 I slot print_timing: id  0 | task 27 | draft acceptance = 1.00000 (    5 accepted /     5 generated), mean len =  3.50
2.24.841.615 I slot      release: id  0 | task 27 | stop processing: n_tokens = 62, truncated = 0
[2026-11-15 00:44:42][INFO][qwen3.8-27b-gsq-rco] Finished streaming response
[2026-11-15 00:44:44][ERROR] Unexpected endpoint or method. (POST /v1/token/encode). Returning 200 anyway
[2026-11-15 00:50:01][DEBUG] 5.10.000.100 I slot print_timing: id  0 | task 31 | prompt eval time =     100.00 ms /    10 tokens (   10.00 ms per token,   100.00 tokens per second)
5.10.000.101 I slot print_timing: id  0 | task 31 |        eval time =     200.00 ms /    20 tokens (   10.00 ms per token,   100.00 tokens per second)
5.10.000.102 I slot print_timing: id  0 | task 31 |       total time =     300.00 ms /    30 tokens
5.10.000.103 I slot      release: id  0 | task 31 | stop processing: n_tokens = 30, truncated = 0
"""


def test_parse_lmstudio_reads_timing_blocks_closed_by_slot_release() -> None:
    entries = engine_log.parse_lmstudio(LMSTUDIO_LOG)

    assert len(entries) == 2
    first = entries[0]
    assert (first.read_tokens, first.prefill_ms) == (55, 275.45)
    assert (first.generated_tokens, first.decode_ms) == (8, 2191.61)
    assert (first.drafts_accepted, first.drafts_proposed) == (5, 5)
    assert first.timestamp == datetime(2026, 11, 15, 0, 44, 42)
    assert not first.cancelled


def test_parse_lmstudio_leaves_draft_counts_empty_when_the_line_has_none() -> None:
    second = engine_log.parse_lmstudio(LMSTUDIO_LOG)[-1]

    assert second.drafts_accepted is None and second.drafts_proposed is None
    assert second.prompt_tokens == 10 and second.reused_tokens == 0


def test_parse_lmstudio_ignores_noise_without_slot_release() -> None:
    noise = LMSTUDIO_LOG.split("5.10.000.103")[0]

    assert [e for e in engine_log.parse_lmstudio(noise) if e.prompt_tokens == 10] == []


def test_lmstudio_sampling_reads_the_last_request_body_with_parameters() -> None:
    text = LMSTUDIO_LOG + (
        'Received request: POST to /v1/chat/completions with body {\n  "max_tokens": 8\n}\n'
    )

    found = engine_log.lmstudio_sampling_from_log(text)

    assert found == {
        "temperature": 0,
        "top_k": 20,
        "top_p": 0.95,
        "min_p": 0,
        "repetition_penalty": 1,
        "presence_penalty": 0,
    }


def test_lmstudio_sampling_absent_when_no_request_body_echoed() -> None:
    assert (
        engine_log.lmstudio_sampling_from_log("[2026-11-15 00:44:28][INFO] Server stopped.") is None
    )
