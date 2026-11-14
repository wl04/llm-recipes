"""Turning raw request and sample records into the result document."""

from typing import Any

import pytest
from baseline import schema
from baseline.aggregate import build_results
from baseline.rawlog import RawRun

GIB = 1024**3


def meta(**extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": 1,
        "suite_version": "1",
        "recipe": "test-recipe",
        "run": {"id": "r1", "status": "complete"},
        "server": {"kind": "strata", "model": "m", "context_tokens": 131072},
        "target": {
            "memory_key": "mem_bytes",
            "memory_label": "cgroup memory.current",
            "cpu_label": "cgroup cpu.stat",
        },
    }
    base.update(extra)
    return base


def request(case: str, run: int = 1, **fields: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "phase": "case",
        "case": case,
        "run": run,
        "started_s": 10.0 + run,
        "ended_s": 11.0 + run,
        "status": "ok",
        "error": None,
        "usage": {"prompt_tokens": 100, "completion_tokens": 51, "cached_tokens": None},
        "first_output_s": 1.0,
        "last_output_s": 6.0,
        "finish_reason": "stop",
    }
    record.update(fields)
    return record


def results(
    requests: list[dict[str, Any]],
    samples: list[dict[str, Any]] | None = None,
    **meta_extra: Any,
) -> dict[str, Any]:
    document = build_results(RawRun(meta(**meta_extra), requests, samples or []))
    schema.validate_results(document)
    return document


def case_of(document: dict[str, Any], case_id: str) -> dict[str, Any]:
    return next(case for case in document["cases"] if case["id"] == case_id)


def value(entry: dict[str, Any], name: str) -> Any:
    return entry["metrics"][name]["value"]


def sample(t: float, **values: float) -> dict[str, Any]:
    return {"t": t, "values": values, "errors": {}}


def test_build_results_takes_median_of_repeated_runs() -> None:
    requests = [
        request("c", 1, usage={"prompt_tokens": 100, "completion_tokens": 51, "cached_tokens": 0}),
        request("c", 2, usage={"prompt_tokens": 102, "completion_tokens": 51, "cached_tokens": 0}),
        request("c", 3, usage={"prompt_tokens": 110, "completion_tokens": 51, "cached_tokens": 0}),
    ]

    case = case_of(results(requests), "c")

    assert case["runs"] == 3
    assert case["status"] == "ok"
    assert value(case, "input_tokens") == 102
    assert value(case, "cached_input_tokens") == 0
    assert case["finish_reason"] == "stop"


def test_build_results_computes_client_decode_rate_from_usage_and_timings() -> None:
    case = case_of(results([request("c")]), "c")

    assert value(case, "client_decode_tok_s") == pytest.approx(10.0)
    assert value(case, "first_output_s") == 1.0
    assert case["metrics"]["client_decode_tok_s"]["source"].startswith("client")


def test_build_results_marks_unreported_values_unavailable_with_reason() -> None:
    case = case_of(results([request("c", usage=None)]), "c")

    assert value(case, "input_tokens") is None
    assert "usage" in case["metrics"]["input_tokens"]["unavailable"]
    assert value(case, "cached_input_tokens") is None
    assert value(case, "engine_decode_tok_s") is None


def test_build_results_reports_noise_floor_only_for_repeated_probe() -> None:
    probe = [
        request("p", n, noise_probe=True, first_output_s=1.0 + 0.1 * n, last_output_s=7.0)
        for n in (1, 2, 3)
    ]

    case = case_of(results(probe), "p")

    assert value(case, "noise_first_output_spread") == pytest.approx(0.2 / 1.2, abs=1e-5)
    assert "noise_decode_spread" in case["metrics"]


def test_build_results_gives_no_noise_floor_for_single_run() -> None:
    case = case_of(results([request("p", noise_probe=True)]), "p")

    assert "noise_first_output_spread" not in case["metrics"]


def test_build_results_marks_case_failed_when_every_request_failed() -> None:
    failed = request("c", status="failed", error="HTTP 500", usage=None, first_output_s=None)

    case = case_of(results([failed]), "c")

    assert case["status"] == "failed"
    assert case["runs"] == 1
    assert "HTTP 500" in case["note"]


def test_build_results_keeps_successful_runs_when_one_request_failed() -> None:
    requests = [request("c", 1), request("c", 2, status="failed", error="reset", usage=None)]

    case = case_of(results(requests), "c")

    assert case["status"] == "ok"
    assert case["runs"] == 2
    assert "reset" in case["note"]


def test_build_results_marks_interrupted_request_as_failed_case() -> None:
    case = case_of(results([request("c", status="interrupted", error="interrupted")]), "c")

    assert case["status"] == "failed"
    assert "interrupted" in case["note"]


def test_build_results_flags_reply_shorter_than_required_minimum() -> None:
    short = request("c", min_output_tokens=512, usage={"prompt_tokens": 9, "completion_tokens": 40})

    case = case_of(results([short]), "c")

    assert case["status"] == "insufficient_sample"
    assert "512" in case["note"]


def test_build_results_records_skipped_case_with_reason() -> None:
    skipped = {"phase": "case", "case": "big", "status": "skipped", "note": "Does not fit"}

    case = case_of(results([skipped]), "big")

    assert (case["status"], case["runs"], case["note"]) == ("skipped", 0, "Does not fit")


def test_build_results_keeps_cases_in_order_of_first_request() -> None:
    document = results([request("b"), request("a"), request("b", 2)])

    assert [case["id"] for case in document["cases"]] == ["b", "a"]


def test_build_results_passes_functional_entries_through() -> None:
    entry = {"id": "text", "status": "pass"}
    record = {"phase": "functional", "case": "text", "functional": entry}

    document = results([record, request("c")])

    assert document["functional"] == [entry]


def test_build_results_summarizes_warmup() -> None:
    warmups = [
        request("warmup", 1, phase="warmup", started_s=0.0, ended_s=2.0),
        request("warmup", 2, phase="warmup", started_s=2.5, ended_s=5.0),
    ]

    document = results([*warmups, request("c")], warmup={"converged": True})

    assert document["warmup"]["requests"] == 2
    assert document["warmup"]["converged"] is True
    assert document["warmup"]["metrics"]["duration_s"]["value"] == 5.0
    assert [case["id"] for case in document["cases"]] == ["c"]


def test_build_results_omits_warmup_when_none_ran() -> None:
    assert "warmup" not in results([request("c")])


def test_build_results_carries_run_status_and_boot_warnings() -> None:
    boot = {"metrics": {}, "warnings": ["busy"]}

    document = results([request("c")], run={"id": "r1", "status": "interrupted"}, boot=boot)

    assert document["run"]["status"] == "interrupted"
    assert document["boot"]["warnings"] == ["busy"]


def requests_between(start: float, end: float) -> list[dict[str, Any]]:
    return [request("c", started_s=start, ended_s=end)]


def resources_of(document: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = document["resources"][0]["metrics"]
    return metrics


def test_resources_compute_cpu_cores_by_interpolating_counter_at_request_bounds() -> None:
    samples = [sample(float(t), cpu_usec=2_000_000 * t) for t in range(0, 6)]

    metrics = resources_of(results(requests_between(1.5, 3.5), samples))

    assert metrics["cpu_cores_avg"]["value"] == pytest.approx(2.0)
    assert metrics["cpu_cores_avg"]["unit"] == "cores"
    assert metrics["cpu_cores_avg"]["source"] == "cgroup cpu.stat"


def test_resources_ignore_peaks_outside_request_intervals() -> None:
    samples = [
        sample(0.5, mem_bytes=9 * GIB),
        sample(2.0, mem_bytes=3 * GIB),
        sample(3.0, mem_bytes=4 * GIB),
        sample(5.0, mem_bytes=8 * GIB),
    ]

    metrics = resources_of(results(requests_between(1.5, 3.5), samples))

    assert metrics["ram_peak_gib"]["value"] == 4.0


def test_resources_use_configured_memory_key_and_label() -> None:
    samples = [
        sample(2.0, mem_pss_bytes=2 * GIB, mem_bytes=7 * GIB),
        sample(3.0, mem_pss_bytes=GIB),
    ]
    target = {"memory_key": "mem_pss_bytes", "memory_label": "process tree PSS"}

    metrics = resources_of(results(requests_between(1.5, 3.5), samples, target=target))

    assert metrics["ram_peak_gib"]["value"] == 2.0
    assert metrics["ram_peak_gib"]["source"] == "process tree PSS"


def test_resources_report_minimum_available_memory_and_device_peaks() -> None:
    samples = [
        sample(2.0, sys_available_bytes=40 * GIB, vram_bytes=14 * GIB, gtt_bytes=GIB),
        sample(3.0, sys_available_bytes=30 * GIB, vram_bytes=15 * GIB, gtt_bytes=2 * GIB),
    ]

    metrics = resources_of(results(requests_between(1.5, 3.5), samples))

    assert metrics["system_available_min_gib"]["value"] == 30.0
    assert metrics["vram_peak_gib"]["value"] == 15.0
    assert metrics["gtt_peak_gib"]["value"] == 2.0


def test_resources_average_gpu_busy_with_sample_and_hold_weighting() -> None:
    samples = [
        sample(1.0, gpu_busy_percent=10, gpu_power_uw=10_000_000, gpu_temp_mc=40_000),
        sample(2.0, gpu_busy_percent=30, gpu_power_uw=30_000_000, gpu_temp_mc=45_000),
        sample(3.0, gpu_busy_percent=50, gpu_power_uw=50_000_000, gpu_temp_mc=44_000),
    ]

    metrics = resources_of(results(requests_between(1.0, 3.0), samples))

    assert metrics["gpu_busy_avg_percent"]["value"] == pytest.approx(20.0)
    assert metrics["gpu_power_avg_w"]["value"] == pytest.approx(20.0)
    assert metrics["gpu_temp_max_c"]["value"] == 45.0


def test_resources_report_swap_activity_as_counter_delta() -> None:
    samples = [sample(1.0, pswpin=100, pswpout=10), sample(4.0, pswpin=130, pswpout=10)]

    metrics = resources_of(results(requests_between(1.0, 4.0), samples))

    assert metrics["swap_in_pages"]["value"] == 30
    assert metrics["swap_out_pages"]["value"] == 0


def test_resources_mark_metric_unavailable_with_collection_error() -> None:
    samples = [
        {"t": 2.0, "values": {}, "errors": {"gpu_power_uw": "power1_average not found"}},
        {"t": 3.0, "values": {}, "errors": {"gpu_power_uw": "power1_average not found"}},
    ]

    metrics = resources_of(results(requests_between(1.5, 3.5), samples))

    assert metrics["gpu_power_avg_w"]["value"] is None
    assert "power1_average" in metrics["gpu_power_avg_w"]["unavailable"]


def test_resources_mark_everything_unavailable_without_samples_in_requests() -> None:
    samples = [sample(0.0, mem_bytes=GIB), sample(20.0, mem_bytes=GIB)]

    metrics = resources_of(results(requests_between(5.0, 6.0), samples))

    assert metrics["ram_peak_gib"]["value"] is None
    assert "no samples" in metrics["ram_peak_gib"]["unavailable"]


def test_resources_report_sample_count_and_largest_gap() -> None:
    samples = [sample(0.5, mem_bytes=1), sample(1.0, mem_bytes=1), sample(3.0, mem_bytes=1)]

    metrics = resources_of(results(requests_between(1.0, 3.0), samples))

    assert metrics["sample_count"]["value"] == 2
    assert metrics["sample_max_gap_s"]["value"] == 2.0


def test_resources_join_samples_only_to_active_request_time() -> None:
    samples = [sample(float(t), cpu_usec=1_000_000 * t) for t in range(0, 12)]
    requests = [
        request("c", 1, started_s=1.0, ended_s=2.0),
        request("c", 2, started_s=6.0, ended_s=7.0),
    ]

    metrics = resources_of(results(requests, samples))

    assert metrics["cpu_cores_avg"]["value"] == pytest.approx(1.0)


def test_resources_cover_only_cases_that_ran_requests() -> None:
    skipped = {"phase": "case", "case": "big", "status": "skipped", "note": "x"}

    document = results([request("c"), skipped], [sample(12.0, mem_bytes=GIB)])

    assert [entry["case"] for entry in document["resources"]] == ["c"]


def test_boot_state_includes_idle_reference_measured_before_requests() -> None:
    samples = [
        sample(0.0, mem_bytes=GIB, vram_bytes=GIB),
        sample(2.0, mem_bytes=GIB, vram_bytes=GIB),
    ]
    boot: dict[str, Any] = {"metrics": {}, "warnings": []}

    document = results([request("c")], samples, boot=boot, idle={"start_s": 0.0, "end_s": 2.0})

    assert document["boot"]["metrics"]["idle_vram_peak_gib"]["value"] == 1.0


def test_resources_report_anonymous_and_file_memory_peaks_inside_requests() -> None:
    samples = [
        sample(2.0, mem_bytes=5 * GIB, mem_anon_bytes=GIB, mem_file_bytes=4 * GIB),
        sample(3.0, mem_bytes=6 * GIB, mem_anon_bytes=2 * GIB, mem_file_bytes=4 * GIB),
    ]

    metrics = resources_of(results(requests_between(1.5, 3.5), samples))

    assert metrics["ram_anon_peak_gib"]["value"] == 2.0
    assert metrics["ram_file_peak_gib"]["value"] == 4.0


def test_resources_omit_cases_where_no_request_succeeded() -> None:
    failed = request("bad", status="failed", error="HTTP 400", usage=None, first_output_s=None)

    document = results([request("c"), failed], [sample(12.0, mem_bytes=GIB)])

    assert [entry["case"] for entry in document["resources"]] == ["c"]
