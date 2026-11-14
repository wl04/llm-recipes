"""End-to-end runs of the baseline runner against an in-process server."""

import signal
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from baseline import schema, vision
from baseline.aggregate import build_results
from baseline.rawlog import RawRun, RunWriter, read_run
from baseline.runner import RunConfig, Runner, converged
from baseline.sampler import Sampler, Source
from baseline.schema import ExitCode
from baseline.sources import Reading
from baseline.workloads import Document, SuiteConfig
from fake_server import FakeServer

ROOT = Path(__file__).resolve().parents[1]
SUITE = SuiteConfig(
    probe_tokens=200,
    noise_runs=3,
    probe_output=10,
    contexts=(("context-a", 400), ("context-big", 100_000)),
    context_output=10,
    sustained_output=12,
    min_sustained_output=8,
    warmup_max=3,
    warmup_tolerance=0.5,
    warmup_output=6,
    idle_seconds=0.03,
    sample_interval_s=0.005,
    request_timeout_s=10,
)
CORPUS = [Document(f"module_{n}.py", f"# module {n}\n" + "x = 1\n" * 700) for n in range(12)]


class Telemetry:
    """A fake telemetry source whose CPU counter rises on every read."""

    def __init__(self) -> None:
        self.reads = 0

    def __call__(self) -> Reading:
        self.reads += 1
        return Reading(values={"cpu_usec": self.reads * 1000.0, "mem_bytes": 2.0**30})


def execute(
    tmp_path: Path,
    server: FakeServer,
    *,
    model: str | None = "test-model",
    suite: SuiteConfig = SUITE,
    context_tokens: int = 2048,
    stop: threading.Event | None = None,
) -> tuple[ExitCode, RawRun, Sampler]:
    writer = RunWriter(tmp_path / "run")
    sampler = Sampler(
        [Source("fake", Telemetry(), ("cpu_usec", "mem_bytes"))],
        suite.sample_interval_s,
        writer.append_sample,
    )
    config = RunConfig(
        recipe="test-recipe",
        kind="strata",
        base_url=server.base_url,
        model=model,
        context_tokens=context_tokens,
        suite=suite,
        corpus=CORPUS,
        run_id="t1",
        expectations=vision.load_expectations(ROOT / "assets/checks/amdgpu-top.expected.json"),
        image=ROOT / "assets/checks/amdgpu-top.png",
        image_is_default=True,
        target={"memory_key": "mem_bytes", "memory_label": "fake", "cpu_label": "fake"},
        meta_extra={"boot": {"metrics": {}, "warnings": ["noted"]}},
    )
    code = Runner(config, writer, sampler, stop=stop).run()
    return code, read_run(writer.directory), sampler


def results_of(raw: RawRun) -> dict[str, Any]:
    document = build_results(raw)
    schema.validate_results(document)
    return document


def case_of(document: dict[str, Any], case_id: str) -> dict[str, Any]:
    return next(case for case in document["cases"] if case["id"] == case_id)


def test_run_completes_every_workload_in_the_fixed_order(tmp_path: Path) -> None:
    with FakeServer() as server:
        code, raw, _ = execute(tmp_path, server)

    document = results_of(raw)
    assert code == ExitCode.OK
    assert document["run"]["status"] == "complete"
    assert [case["id"] for case in document["cases"]] == [
        "context-8k",
        "sustained-lru-cache",
        "sustained-tokenizer",
        "sustained-event-store",
        "context-a",
        "context-big",
    ]
    assert [e["status"] for e in document["functional"]] == ["pass", "pass", "pass"]
    assert [e["id"] for e in document["functional"]] == ["text", "tools", "vision"]
    assert case_of(document, "context-big")["status"] == "skipped"
    assert "does not fit" in case_of(document, "context-big")["note"]


def test_run_scores_the_vision_answer_against_the_expectations(tmp_path: Path) -> None:
    with FakeServer() as server:
        _, raw, _ = execute(tmp_path, server)

    vision_entry = results_of(raw)["functional"][2]
    assert vision_entry["scores"]["identity"] == {"match": 2, "mismatch": 0, "missing": 0}
    assert vision_entry["scores"]["detail"]["match"] == 7


def test_run_fails_the_check_when_vision_misreads_identity_fields(tmp_path: Path) -> None:
    with FakeServer() as server:
        server.vision_answer["application"] = "nvidia-smi"
        code, raw, _ = execute(tmp_path, server)

    assert results_of(raw)["functional"][2]["status"] == "fail"
    assert code == ExitCode.CHECKS_FAILED


def test_run_repeats_only_the_probe_and_reports_its_noise_floor(tmp_path: Path) -> None:
    with FakeServer() as server:
        _, raw, _ = execute(tmp_path, server)

    document = results_of(raw)
    assert case_of(document, "context-8k")["runs"] == 3
    assert "noise_decode_spread" in case_of(document, "context-8k")["metrics"]
    assert case_of(document, "context-a")["runs"] == 1
    assert "noise_decode_spread" not in case_of(document, "context-a")["metrics"]


def test_run_calibrates_prompt_length_from_the_servers_reported_tokens(tmp_path: Path) -> None:
    with FakeServer(chars_per_token=4.0) as server:
        _, raw, _ = execute(tmp_path, server)

    tokens = case_of(results_of(raw), "context-8k")["metrics"]["input_tokens"]["value"]
    assert 170 <= tokens <= 215


def test_run_fits_every_probe_prompt_to_the_target_with_the_servers_tokenizer(
    tmp_path: Path,
) -> None:
    with FakeServer(chars_per_token=3.3) as server:
        _, raw, _ = execute(tmp_path, server)

    probes = [r for r in raw.requests if r.get("case") == "context-8k"]
    assert len(probes) == 3
    assert all(190 <= r["counted_input_tokens"] <= 200 for r in probes)
    assert all(190 <= r["usage"]["prompt_tokens"] <= 200 for r in probes)
    assert server.count_requests
    assert raw.meta["workload"]["token_counting"].startswith("server route")


def test_run_falls_back_to_calibration_when_the_tokenizer_route_fails(tmp_path: Path) -> None:
    with FakeServer(chars_per_token=4.0) as server:
        server.counts_tokens = False
        code, raw, _ = execute(tmp_path, server)

    document = results_of(raw)
    later = case_of(document, "context-a")["metrics"]["input_tokens"]["value"]
    assert code == ExitCode.OK
    assert raw.meta["workload"]["token_counting"] == "calibration from reported usage"
    assert 340 <= later <= 420


def test_run_skips_a_case_when_counted_input_plus_output_exceeds_the_context(
    tmp_path: Path,
) -> None:
    suite = SuiteConfig(
        **{**SUITE.__dict__, "contexts": (("context-tight", 400),), "context_output": 1700}
    )
    with FakeServer() as server:
        _, raw, _ = execute(tmp_path, server, suite=suite)

    case = case_of(results_of(raw), "context-tight")
    assert case["status"] == "skipped"
    assert "does not fit" in case["note"]


def test_run_uses_distinct_content_for_every_request(tmp_path: Path) -> None:
    with FakeServer() as server:
        execute(tmp_path, server)

    prompts = [str(p["messages"][0]["content"])[:400] for p in server.requests if p.get("stream")]
    assert len(set(prompts)) == len(prompts)


def test_run_starts_monitoring_before_requests_and_keeps_it_until_after_them(
    tmp_path: Path,
) -> None:
    with FakeServer() as server:
        _, raw, _ = execute(tmp_path, server)

    starts = [r["started_s"] for r in raw.requests if "started_s" in r]
    ends = [r["ended_s"] for r in raw.requests if "ended_s" in r]
    times = [s["t"] for s in raw.samples]
    assert min(times) < min(starts)
    assert max(times) > max(ends)


def test_run_attributes_samples_to_each_case_while_requests_block(tmp_path: Path) -> None:
    with FakeServer(token_delay_s=0.004) as server:
        _, raw, _ = execute(tmp_path, server)

    document = results_of(raw)
    for entry in document["resources"]:
        assert entry["metrics"]["sample_count"]["value"] >= 2
        assert entry["metrics"]["cpu_cores_avg"]["value"] is not None
    assert document["boot"]["metrics"]["idle_cpu_cores_avg"]["value"] is not None


def test_run_records_a_failed_request_and_continues_with_the_rest(tmp_path: Path) -> None:
    with FakeServer() as server:
        server.behave = lambda p: "fail" if "t1-8k-1." in str(p["messages"][0]["content"]) else None
        code, raw, _ = execute(tmp_path, server)

    probe = case_of(results_of(raw), "context-8k")
    assert code == ExitCode.CHECKS_FAILED
    assert (probe["status"], probe["runs"]) == ("ok", 3)
    assert "injected failure" in probe["note"]
    assert case_of(results_of(raw), "context-a")["status"] == "ok"


def test_run_keeps_the_partial_result_of_a_truncated_stream(tmp_path: Path) -> None:
    with FakeServer() as server:
        server.behave = lambda p: (
            "truncate" if "sustained-tokenizer" in str(p["messages"][0]["content"]) else None
        )
        code, raw, _ = execute(tmp_path, server)

    failed = next(r for r in raw.requests if r.get("case") == "sustained-tokenizer")
    assert code == ExitCode.CHECKS_FAILED
    assert failed["status"] == "failed"
    assert failed["first_output_s"] is not None
    assert "before [DONE]" in failed["error"]


def test_run_stops_at_preflight_when_the_model_is_not_served(tmp_path: Path) -> None:
    with FakeServer() as server:
        server.models = ["another-model"]
        code, raw, sampler = execute(tmp_path, server)

    assert code == ExitCode.PREFLIGHT_FAILED
    assert raw.meta["run"]["status"] == "failed"
    assert "test-model" in raw.meta["run"]["error"]
    assert server.requests == []
    assert raw.samples == []
    assert sampler.failures == 0


def test_run_uses_the_only_served_model_when_none_is_given(tmp_path: Path) -> None:
    with FakeServer(model="only-model") as server:
        code, raw, _ = execute(tmp_path, server, model=None)

    assert code == ExitCode.OK
    assert raw.meta["server"]["model"] == "only-model"
    assert {p["model"] for p in server.requests} == {"only-model"}


def test_run_refuses_to_guess_when_several_models_are_served(tmp_path: Path) -> None:
    with FakeServer() as server:
        server.models = ["a", "b"]
        code, raw, _ = execute(tmp_path, server, model=None)

    assert code == ExitCode.PREFLIGHT_FAILED
    assert "--model" in raw.meta["run"]["error"]


def test_run_records_interruption_and_stops_monitoring(tmp_path: Path) -> None:
    with FakeServer() as server:
        server.behave = lambda p: "hang" if "t1-8k-1." in str(p["messages"][0]["content"]) else None
        timer = threading.Timer(
            0.5, lambda: signal.pthread_kill(threading.main_thread().ident or 0, signal.SIGINT)
        )
        timer.start()
        try:
            code, raw, _ = execute(tmp_path, server)
        finally:
            timer.cancel()

    document = results_of(raw)
    interrupted = [r for r in raw.requests if r.get("status") == "interrupted"]
    count = len(raw.samples)
    assert code == ExitCode.INTERRUPTED
    assert document["run"]["status"] == "interrupted"
    assert len(interrupted) == 1
    assert max(s["t"] for s in raw.samples) > interrupted[0]["ended_s"] - 0.001
    assert [c["id"] for c in document["cases"]] == ["context-8k"]
    time.sleep(0.05)
    assert len(read_run(tmp_path / "run").samples) == count


def test_run_stops_between_requests_when_asked(tmp_path: Path) -> None:
    stop = threading.Event()
    with FakeServer() as server:
        original = server.behave

        def behave(payload: dict[str, Any]) -> str | None:
            if "sustained" in str(payload["messages"][0]["content"]):
                stop.set()
            return original(payload)

        server.behave = behave
        code, raw, _ = execute(tmp_path, server, stop=stop)

    assert code == ExitCode.INTERRUPTED
    assert "context-a" not in [c["id"] for c in results_of(raw)["cases"]]


def test_run_marks_short_sustained_reply_as_insufficient(tmp_path: Path) -> None:
    with FakeServer(output_tokens=5) as server:
        _, raw, _ = execute(tmp_path, server)

    case = case_of(results_of(raw), "sustained-lru-cache")
    assert case["status"] == "insufficient_sample"


def test_run_records_the_request_policy_and_unconfigured_thinking(tmp_path: Path) -> None:
    with FakeServer() as server:
        _, raw, _ = execute(tmp_path, server)

    policy = raw.meta["policy"]
    assert policy["performance"]["temperature"] == 1.0
    assert policy["functional"]["temperature"] == 0.0
    assert policy["thinking_disabled_by_default"] is True
    assert {p.get("temperature") for p in server.requests} == {0.0, 1.0}


@pytest.mark.parametrize(
    ("rates", "expected"),
    [
        ([10.0, 10.5], True),
        ([10.0, 13.0], False),
        ([10.0], False),
        ([None, 10.0], False),
        ([5.0, 20.0, 20.5], True),
        ([], False),
    ],
)
def test_converged_compares_the_last_two_rates(rates: list[float | None], expected: bool) -> None:
    assert converged(rates, tolerance=0.10) is expected
