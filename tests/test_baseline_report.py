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


def header_of(text: str, first_cell: str) -> list[str]:
    return row_of(text, first_cell)


def section(text: str, heading: str) -> str:
    return text.split(heading)[1].split("\n### ")[0]


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
    assert "Warmup: 2 requests, converged, 14.20 s." in render()


def test_boot_state_uses_readable_labels_and_used_over_total_pairs() -> None:
    boot = section(render(), "### Boot state")

    assert row_of(boot, "Uptime (s)")[1] == "540"
    assert row_of(boot, "RAM used / total (GB)")[1] == "6.5 / 62.6"
    assert row_of(boot, "Swap used / total (GB)")[1] == "0.0 / 8.0"
    assert row_of(boot, "VRAM used / total (GB)")[1] == "0.2 / 15.9"
    assert row_of(boot, "GPU busy (%)")[1] == "2"
    assert row_of(boot, "GPU power (W)")[1] == "9.30"
    assert row_of(boot, "GPU temperature (°C)")[1] == "29"
    assert row_of(boot, "Load average (1 min)")[1] == "0.25"


def test_boot_state_shows_variable_names_nowhere() -> None:
    boot = section(render(), "### Boot state")

    for name in ("uptime_s", "mem_used_gib", "gpu_vram_used_gib", "swap_used_gib", "load_1m"):
        assert name not in boot


def test_boot_state_shows_a_dash_for_a_missing_total() -> None:
    document = sample_results()
    del document["boot"]["metrics"]["gpu_vram_total_gib"]

    boot = section(render(document), "### Boot state")

    assert row_of(boot, "VRAM used / total (GB)")[1] == "0.2 / —"


def test_render_results_block_lists_boot_warnings() -> None:
    assert "Another process was using the GPU at start" in render()


def test_cases_table_has_the_agreed_columns_and_no_note_column() -> None:
    cases = section(render(), "### Cases")
    header = [c.strip() for c in cases.strip().splitlines()[0].strip("|").split("|")]

    assert header == [
        "Case",
        "Status",
        "Runs",
        "Input tokens",
        "Output tokens",
        "First output (s)",
        "Prefill (tok/s)",
        "Decode (tok/s)",
        "Draft acceptance",
        "Finish",
    ]


def test_cases_table_formats_values_and_marks_unavailable() -> None:
    row = row_of(section(render(), "### Cases"), "context-8k")

    assert row[2] == "5"
    assert "8,012" in row
    assert "2.50" in row
    assert "3,100.40" in row or "3,100.4" in row
    assert "81.50" in row


def test_cases_table_shows_a_dash_when_the_server_reports_no_prefill() -> None:
    document = sample_results()
    document["cases"][0]["metrics"]["engine_prefill_tok_s"] = schema.unavailable("no log")

    row = row_of(section(render(document), "### Cases"), "context-8k")

    assert "—" in row


def test_skipped_case_keeps_its_status_and_reason_outside_the_table() -> None:
    cases = section(render(), "### Cases")

    assert row_of(cases, "context-120k")[1] == "skipped"
    assert "- context-120k: Input plus output exceeds the 65,536-token context" in cases


def test_render_results_block_states_noise_floor_of_repeated_case() -> None:
    text = render()

    assert "Noise floor, context-8k (5 runs)" in text
    assert "first output 4.0%" in text
    assert "decode rate 3.0%" in text


def test_resources_use_used_over_total_columns() -> None:
    resources = section(render(), "### Resources")
    header = [c.strip() for c in resources.strip().splitlines()[0].strip("|").split("|")]

    assert header == [
        "Case",
        "Server CPU (cores)",
        "System CPU busy (%)",
        "RAM peak / total (GB)",
        "VRAM peak / total (GB)",
        "GPU busy (%)",
        "GPU power (W)",
        "GPU temp (°C)",
        "Swap in / out (pages)",
        "Samples",
        "Max sample gap (s)",
    ]


def test_resources_row_pairs_peaks_with_totals_from_the_boot_state() -> None:
    row = row_of(section(render(), "### Resources"), "context-8k")

    assert "53.2 / 62.6" in row
    assert "15.1 / 15.9" in row
    assert "0 / —" in row  # swap out was not measured


def test_resources_omit_gtt_anonymous_file_cache_and_process_vram() -> None:
    resources = section(render(), "### Resources")

    for word in ("GTT", "anon", "file cache", "process VRAM", "Min available"):
        assert word not in resources


def test_no_phases_section_is_rendered() -> None:
    text = render()

    assert "### Phases" not in text
    assert "time to ready" not in text


def test_units_are_gb_not_gib_or_mib() -> None:
    text = render()

    assert "GiB" not in text
    assert "MiB" not in text
    assert "GB" in text


def test_a_definitions_line_explains_decode_prefill_and_gb() -> None:
    text = render()

    assert "Decode is a client estimate" in text
    assert "Prefill is reported by the engine" in text
    assert "2^30" not in text


def test_unavailable_list_covers_only_metrics_that_are_shown() -> None:
    text = render()
    unavailable = text.split("### Unavailable measurements")[1]

    assert "engine_decode_tok_s" not in unavailable
    assert "swap_out_pages" in unavailable


def test_unavailable_reasons_are_grouped_across_cases() -> None:
    document = sample_results()
    document["cases"].append(
        {
            "id": "context-32k",
            "status": "ok",
            "runs": 1,
            "metrics": {"engine_prefill_tok_s": schema.unavailable("no log")},
        }
    )
    document["cases"][0]["metrics"]["engine_prefill_tok_s"] = schema.unavailable("no log")

    unavailable = render(document).split("### Unavailable measurements")[1]

    assert unavailable.count("no log") == 1
    assert "(context-8k, context-32k)" in unavailable


def test_render_results_block_omits_absent_optional_sections() -> None:
    document = sample_results()
    for key in ("boot", "warmup", "resources", "phases"):
        del document[key]
    del document["cases"][0]["metrics"]["noise_first_output_spread"]
    del document["cases"][0]["metrics"]["noise_decode_spread"]

    text = render(document)

    assert "### Resources" not in text
    assert "### Boot state" not in text
    assert "Warmup:" not in text
    assert "Noise floor" not in text


def test_render_results_block_escapes_table_delimiters_in_reasons() -> None:
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


def test_render_results_block_keeps_precision_for_sub_second_latency() -> None:
    document = sample_results()
    document["cases"][0]["metrics"]["first_output_s"] = schema.measured(0.0123, "s", "client")

    assert "0.012" in row_of(section(render(document), "### Cases"), "context-8k")


def test_cached_input_column_appears_only_when_the_server_reports_it() -> None:
    document = sample_results()
    assert "Cached input" not in render(document)

    document["cases"][0]["metrics"]["cached_input_tokens"] = schema.measured(0, "tokens", "usage")

    assert "Cached input" in render(document)


def test_blocks_never_contain_two_blank_lines_in_a_row() -> None:
    document = sample_results()
    document["boot"]["warnings"] = []

    assert "\n\n\n" not in render(document)
    assert "\n\n\n" not in render()
