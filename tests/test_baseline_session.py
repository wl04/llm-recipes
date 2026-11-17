"""Session statistics and schema for coding-session reports from engine logs."""

from datetime import datetime
from typing import Any

import pytest
from baseline import engine_log, schema, session

REQUEST: dict[str, Any] = {
    "prompt_tokens": 1000,
    "reused_tokens": 400,
    "read_tokens": 600,
    "prefill_ms": 500,
    "generated_tokens": 100,
    "decode_ms": 1000,
    "drafts_accepted": 40,
    "drafts_proposed": 80,
}


def entry(**overrides: object) -> engine_log.EngineRequest:
    values = {**REQUEST, **overrides}
    return engine_log.EngineRequest(**values)


def entries() -> list[engine_log.EngineRequest]:
    return [
        entry(),
        entry(
            prompt_tokens=200,
            reused_tokens=0,
            read_tokens=200,
            prefill_ms=100,
            generated_tokens=50,
            decode_ms=500,
        ),
        entry(
            prompt_tokens=5000,
            reused_tokens=1000,
            read_tokens=4000,
            prefill_ms=3000,
            generated_tokens=2000,
            decode_ms=20000,
        ),
    ]


def test_session_stats_totals_tokens_and_cancelled_requests() -> None:
    document = session.session_stats(
        [*entries(), entry(cancelled=True, sequence=9)],
        engine="tabbyapi",
    )

    totals = document["totals"]
    assert totals["requests"] == 3
    assert totals["cancelled"] == 1
    assert totals["prompt_tokens"] == 6200
    assert totals["reused_prompt_tokens"] == 1400
    assert totals["read_prompt_tokens"] == 4800
    assert totals["generated_tokens"] == 2150
    assert totals["decode_tok_s"] == pytest.approx(2150 / 21.5)
    assert totals["decode_tok_s_median"] == pytest.approx(100.0)
    assert totals["drafts_accepted"] == 120
    assert totals["drafts_proposed"] == 240
    assert document["engine"] == "tabbyapi"
    assert document["schema_version"] == 1


def test_session_stats_buckets_requests_by_context_range() -> None:
    document = session.session_stats(entries(), engine="tabbyapi")

    buckets = {bucket["label"]: bucket for bucket in document["totals"]["context_buckets"]}

    assert buckets["under 2,048 tokens"]["requests"] == 2
    assert buckets["2,048-8,191 tokens"]["requests"] == 1
    assert buckets["2,048-8,191 tokens"]["prompt_tokens"] == 5000


def test_session_stats_marks_unavailable_metrics_as_unavailable() -> None:
    no_drafts = [entry(drafts_accepted=None, drafts_proposed=None)]

    document = session.session_stats(no_drafts, engine="strata")

    assert document["availability"]["draft_acceptance"] is False
    assert document["availability"]["timestamps"] is False
    assert document["availability"]["unclosed_requests"] is False
    assert document["totals"]["draft_acceptance"] is None
    assert document["first_request"] is None


def test_session_stats_reports_timestamp_span_when_available() -> None:
    first = datetime(2026, 11, 15, 9, 0, 0)
    last = datetime(2026, 11, 15, 11, 30, 0)
    made = [entry(timestamp=first), entry(timestamp=last)]

    document = session.session_stats(made, engine="tabbyapi", unclosed=2)

    assert document["first_request"] == first.isoformat()
    assert document["last_request"] == last.isoformat()
    assert document["availability"]["timestamps"] is True
    assert document["totals"]["unclosed_requests"] == 2


def test_filter_window_keeps_entries_inside_the_window() -> None:
    base = datetime(2026, 11, 15, 9, 0)
    made = [entry(timestamp=base), entry(timestamp=datetime(2026, 11, 15, 12, 0))]

    kept = session.filter_window(made, datetime(2026, 11, 15, 10), None)

    assert len(kept) == 1
    assert kept[0].timestamp == datetime(2026, 11, 15, 12, 0)


def test_filter_window_rejects_timestampless_logs() -> None:
    with pytest.raises(ValueError, match="no timestamps"):
        session.filter_window([entry()], datetime(2026, 11, 15, 10), None)


def test_validate_session_accepts_generated_document() -> None:
    document = session.session_stats(entries(), engine="tabbyapi", unclosed=0)

    schema.validate_session(document)


def test_validate_session_rejects_negative_totals() -> None:
    document = session.session_stats(entries(), engine="tabbyapi")
    document["totals"]["cancelled"] = -1

    with pytest.raises(ValueError, match="cancelled"):
        schema.validate_session(document)


def test_validate_session_rejects_unknown_engine() -> None:
    document = session.session_stats(entries(), engine="tabbyapi")
    document["engine"] = "vllm"

    with pytest.raises(ValueError, match="engine"):
        schema.validate_session(document)


def rendered_document(**overrides: object) -> dict[str, Any]:
    entries_for_stats = [
        entry(timestamp=datetime(2026, 11, 15, 9, 0)),
        entry(
            timestamp=datetime(2026, 11, 15, 11, 0),
            prompt_tokens=50_000,
            read_tokens=49_000,
            prefill_ms=40_000,
            generated_tokens=512,
            decode_ms=8_000,
        ),
        entry(cancelled=True, sequence=42),
    ]
    document = session.session_stats(
        entries_for_stats, engine="tabbyapi", unclosed=1, log_files=("engine.log",)
    )
    document.update(overrides)
    return document


def test_session_report_renders_totals_and_buckets() -> None:
    from baseline import report

    block = report.render_session(rendered_document())

    assert "### Session activity" in block
    assert "| Requests completed | 2 |" in block
    assert "| Cancelled | 1 |" in block
    assert "| Started without result | 1 |" in block
    assert "| Generated tokens | 612 |" in block
    assert "### Request size distribution" in block
    assert "32,768-131,071 tokens" in block


def test_session_report_marks_unavailable_metrics_as_unavailable() -> None:
    from baseline import report

    document = rendered_document()
    document = session.session_stats([entry()], engine="strata", log_files=("engine.log",))
    block = report.render_session(document)

    assert "Timestamps: unavailable" in block
    assert "| Wall-clock span | unavailable |" in block
    assert "| Started without result | unavailable |" in block


def test_write_session_block_appends_when_absent(tmp_path: Any) -> None:
    from baseline import report

    summary = tmp_path / "summary.md"
    summary.write_text("# Experiment\n\nHuman prose.\n")

    report.write_session_block(summary, "### Session activity\n\n| a | b |\n")

    text = summary.read_text()
    assert text.count(report.SESSION_START) == 1
    assert "Human prose." in text
    assert "### Session activity" in text


def test_write_session_block_replaces_only_the_generated_block(tmp_path: Any) -> None:
    from baseline import report

    summary = tmp_path / "summary.md"
    summary.write_text(
        "# Experiment\n\n"
        + report.SESSION_START
        + "\n\nold\n"
        + report.SESSION_END
        + "\n\nHuman prose.\n"
    )

    report.write_session_block(summary, "new\n")

    text = summary.read_text()
    assert "new" in text
    assert "old" not in text
    assert "Human prose." in text


def test_write_session_block_rejects_unbalanced_markers(tmp_path: Any) -> None:
    from baseline import report

    summary = tmp_path / "summary.md"
    summary.write_text(report.SESSION_START + "\n\norphan\n")

    with pytest.raises(ValueError, match="exactly one"):
        report.write_session_block(summary, "block")


def test_tabby_sampling_parsed_from_inline_override_line() -> None:
    text = (
        "2026-11-07 20:45:33.212 | INFO     | Sampler overrides (inline): temperature 1.0, "
        "top_k 20, top_p 0.95, min_p 0, repetition_penalty 1, presence_penalty 0\n"
    )

    assert engine_log.tabby_sampling_from_log(text) == {
        "temperature": 1.0,
        "top_k": 20,
        "top_p": 0.95,
        "min_p": 0,
        "repetition_penalty": 1,
        "presence_penalty": 0,
    }


def test_strata_sampling_parsed_from_config_defaults_line() -> None:
    text = (
        "[strata] sampling defaults from the config: temperature=1.0, top_k=20, top_p=0.95, "
        "min_p=0.0, repetition_penalty=1.0, presence_penalty=0.0\n"
    )

    assert engine_log.strata_sampling_from_log(text) == {
        "temperature": 1.0,
        "top_k": 20,
        "top_p": 0.95,
        "min_p": 0,
        "repetition_penalty": 1,
        "presence_penalty": 0,
    }


def test_sampling_from_log_absent_when_never_logged() -> None:
    assert engine_log.tabby_sampling_from_log("nothing here") is None
    assert engine_log.strata_sampling_from_log("nothing here") is None
