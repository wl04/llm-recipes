"""Rendering of baseline results into the markdown block of an experiment summary."""

import copy
from typing import Any

import pytest
from baseline import report, schema
from baseline_data import sample_results


def render(document: dict[str, Any] | None = None) -> str:
    return report.render_results_block(document or sample_results())


def row_of(text: str, first_cell: str) -> list[str]:
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if line.startswith("|") and cells[0] == first_cell:
            return cells
    raise AssertionError(f"No table row starting with {first_cell!r}")


def test_render_results_block_shows_run_identity_and_status() -> None:
    text = render()

    assert text.startswith("## Baseline results")
    assert "test-model" in text
    assert "131,072" in text
    assert "suite 1" in text


def test_render_results_block_marks_interrupted_run() -> None:
    document = sample_results()
    document["run"]["status"] = "interrupted"

    assert "interrupted" in render(document).splitlines()[2]


def test_render_results_block_lists_functional_outcomes_with_vision_scores() -> None:
    text = render()

    assert row_of(text, "text")[1] == "pass"
    vision = row_of(text, "vision")
    assert vision[1] == "pass"
    assert "identity 2/2" in vision[2]
    assert "detail 5/9" in vision[2]
    assert "1 mismatch" in vision[2]


def test_render_results_block_reports_warmup() -> None:
    text = render()

    assert "Warmup: 2 requests, converged, 14.20 s." in text


def test_render_results_block_formats_case_values_and_marks_unavailable() -> None:
    row = row_of(render(), "context-8k")

    assert "5" in row
    assert "8,012" in row
    assert "2.50" in row
    assert "81.50" in row
    assert "—" in row


def test_render_results_block_shows_skip_note_for_skipped_case() -> None:
    row = row_of(render(), "context-120k")

    assert row[1] == "skipped"
    assert "exceeds the 65,536-token context" in row[-1]


def test_render_results_block_states_noise_floor_of_repeated_case() -> None:
    text = render()

    assert "Noise floor, context-8k (5 runs)" in text
    assert "first output 4.0%" in text
    assert "decode rate 3.0%" in text


def test_render_results_block_lists_resources_per_case() -> None:
    section = render().split("### Resources")[1]

    row = row_of(section, "context-8k")
    assert row[1] == "1.50"
    assert "15.10" in row
    assert "CPU (cores)" in section
    assert "Peak VRAM (GiB)" in section


def test_render_results_block_collects_reasons_for_unavailable_measurements() -> None:
    text = render()

    assert "context-8k engine_decode_tok_s: server reports no timings" in text
    assert "context-8k swap_out_pages: /proc/vmstat not readable" in text


def test_render_results_block_lists_boot_warnings() -> None:
    text = render()

    assert "Another process was using the GPU at start" in text
    assert "uptime" in text


def test_render_results_block_omits_absent_optional_sections() -> None:
    document = sample_results()
    for key in ("boot", "warmup", "resources"):
        del document[key]
    del document["cases"][0]["metrics"]["noise_first_output_spread"]
    del document["cases"][0]["metrics"]["noise_decode_spread"]

    text = render(document)

    assert "### Resources" not in text
    assert "### Boot state" not in text
    assert "Warmup:" not in text
    assert "Noise floor" not in text


def test_render_results_block_escapes_table_delimiters_in_notes() -> None:
    document = sample_results()
    document["cases"][1]["note"] = "a | b"

    assert "a &#124; b" in render(document)


def test_render_results_block_is_deterministic() -> None:
    assert render() == render(copy.deepcopy(sample_results()))


def test_render_results_block_rejects_invalid_document() -> None:
    document = sample_results()
    document["cases"][0]["metrics"]["bad"] = {"value": 1}

    with pytest.raises(ValueError, match="bad"):
        render(document)


def test_render_results_block_renders_every_metric_the_runner_may_emit() -> None:
    document = sample_results()
    document["cases"][0]["metrics"]["cached_input_tokens"] = schema.measured(0, "tokens", "usage")

    text = render(document)

    assert "Cached input" in text


def test_render_results_block_keeps_precision_for_sub_second_latency() -> None:
    document = sample_results()
    document["cases"][0]["metrics"]["first_output_s"] = schema.measured(0.0123, "s", "client")

    assert "0.012" in row_of(render(document), "context-8k")


def test_render_results_block_shows_phase_table_and_extra_measures() -> None:
    document = sample_results()
    document["phases"][1]["metrics"]["vram_vs_idle_gib"] = schema.measured(0.25, "GiB", "x")

    text = render(document)

    assert "### Phases" in text
    idle = row_of(text, "idle")
    assert idle[1] == "ok"
    assert "30" in idle
    assert "2.50" in idle
    assert "- load: time to ready 94.20 s" in text
    assert "- load: vram vs idle 0.250 GiB" in text


def test_render_results_block_omits_phase_section_without_phases() -> None:
    document = sample_results()
    del document["phases"]

    assert "### Phases" not in render(document)
