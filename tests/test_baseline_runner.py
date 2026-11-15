"""End-to-end runs of the baseline runner against an in-process server."""

import signal
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from baseline import functional, schema, vision
from baseline.aggregate import build_results
from baseline.lifecycle import LifecycleError, StartedServer
from baseline.rawlog import RawRun, RunWriter, read_run
from baseline.runner import RunConfig, Runner, converged
from baseline.sampler import Sampler, Source
from baseline.schema import ExitCode
from baseline.sources import Reading
from baseline.workloads import Document, SuiteConfig
from fake_server import FakeServer
from test_baseline_sources import make_cgroup

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
    load_timeout_s=3.0,
    ready_poll_s=0.01,
    settle_seconds=0.03,
    settle_max_seconds=0.5,
    settle_poll_s=0.01,
    settle_system_cpu_percent=100.0,
    settle_server_cpu_cores=100.0,
    loaded_idle_seconds=0.03,
    unload_seconds=0.03,
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


class FakeControl:
    """A server control that records calls and can fail or delay at each step."""

    def __init__(self, tmp_path: Path, server: FakeServer | None = None) -> None:
        self.calls: list[str] = []
        self.server = server
        self.cgroup = make_cgroup(tmp_path / "server-cgroup")
        self.ready_after_s = 0.0
        self.preflight_error: str | None = None
        self.start_error: str | None = None
        self.stop_error: str | None = None
        self.running = True

    def preflight(self) -> None:
        self.calls.append("preflight")
        if self.preflight_error:
            raise LifecycleError(self.preflight_error)

    def start(self) -> StartedServer:
        self.calls.append("start")
        if self.start_error:
            raise LifecycleError(self.start_error)
        if self.server is not None and self.ready_after_s:
            served = self.server.models
            self.server.models = []
            threading.Timer(
                self.ready_after_s, lambda: setattr(self.server, "models", served)
            ).start()
        return StartedServer(self.cgroup, {"instance": "baseline", "container_id": "abc"})

    def is_running(self) -> bool:
        return self.running

    def stop(self) -> None:
        self.calls.append("stop")
        if self.stop_error:
            raise LifecycleError(self.stop_error)


def execute(
    tmp_path: Path,
    server: FakeServer,
    *,
    model: str | None = "test-model",
    kind: str = "strata",
    suite: SuiteConfig = SUITE,
    context_tokens: int = 2048,
    stop: threading.Event | None = None,
    control: FakeControl | None = None,
    keep_running: bool = False,
) -> tuple[ExitCode, RawRun, Sampler]:
    writer = RunWriter(tmp_path / "run")
    sampler = Sampler(
        [Source("fake", Telemetry(), ("cpu_usec", "mem_bytes"))],
        suite.sample_interval_s,
        writer.append_sample,
    )
    config = RunConfig(
        recipe="test-recipe",
        kind=kind,
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
        keep_running=keep_running,
    )
    code = Runner(config, writer, sampler, stop=stop, control=control).run()
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
        "conversation-fresh",
        "conversation-reuse-1",
        "conversation-reuse-2",
        "conversation-reuse-3",
        "reasoning-medium",
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


def test_run_marks_the_tool_check_as_two_requests_for_log_matching(tmp_path: Path) -> None:
    with FakeServer() as server:
        _, raw, _ = execute(tmp_path, server)

    counts = {r["case"]: r.get("requests", 1) for r in raw.requests if r["phase"] == "functional"}
    assert counts == {"text": 1, "tools": 2, "vision": 1}


def test_run_uses_distinct_content_for_every_request(tmp_path: Path) -> None:
    with FakeServer() as server:
        execute(tmp_path, server)

    single_message = [p for p in server.requests if p.get("stream") and len(p["messages"]) == 1]
    prompts = [str(p["messages"][0]["content"])[:400] for p in single_message]
    assert len(set(prompts)) == len(prompts)


def test_run_replays_conversation_prefixes_after_the_cold_full_prompt(
    tmp_path: Path,
) -> None:
    with FakeServer() as server:
        _, raw, _ = execute(tmp_path, server)

    conversation = [p for p in server.requests if p.get("stream") and len(p["messages"]) > 1]
    full = conversation[0]["messages"]
    assert [p["messages"] for p in conversation[1:]] == [full[:3], full[:5], full]
    assert [c["id"] for c in results_of(raw)["cases"]][-5:] == [
        "conversation-fresh",
        "conversation-reuse-1",
        "conversation-reuse-2",
        "conversation-reuse-3",
        "reasoning-medium",
    ]


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
    phases = {phase["id"]: phase for phase in document["phases"]}
    assert list(phases) == ["settle", "loaded_idle"]
    assert phases["loaded_idle"]["metrics"]["cpu_cores_avg"]["value"] is not None


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
    assert policy["thinking_request"] == {"reasoning_effort": "none"}
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


def phase_ids(document: dict[str, Any]) -> list[str]:
    return [phase["id"] for phase in document["phases"]]


def test_managed_run_goes_through_every_phase_and_stops_the_server_last(tmp_path: Path) -> None:
    with FakeServer() as server:
        control = FakeControl(tmp_path, server)
        code, raw, _ = execute(tmp_path, server, control=control)

    document = results_of(raw)
    assert code == ExitCode.OK
    assert control.calls == ["preflight", "start", "stop"]
    assert phase_ids(document) == [
        "idle", "load", "settle", "loaded_idle", "unload", "after_unload"
    ]  # fmt: skip
    assert all(phase["status"] == "ok" for phase in document["phases"])
    unload = next(p for p in document["phases"] if p["id"] == "unload")["metrics"]
    assert unload["time_to_stop_s"]["value"] >= 0
    assert raw.meta["container"]["container_id"] == "abc"
    last_request = max(r["ended_s"] for r in raw.requests if "ended_s" in r)
    assert raw.meta["phases"]["unload"]["start_s"] >= last_request


def test_managed_run_waits_for_the_server_to_become_ready_and_times_the_load(
    tmp_path: Path,
) -> None:
    with FakeServer() as server:
        control = FakeControl(tmp_path, server)
        control.ready_after_s = 0.15
        code, raw, _ = execute(tmp_path, server, control=control)

    load = next(p for p in results_of(raw)["phases"] if p["id"] == "load")
    assert code == ExitCode.OK
    assert load["metrics"]["time_to_ready_s"]["value"] >= 0.14


def test_managed_run_samples_only_system_sources_until_the_server_exists(tmp_path: Path) -> None:
    with FakeServer() as server:
        control = FakeControl(tmp_path, server)
        _, raw, _ = execute(tmp_path, server, control=control)

    load_start = raw.meta["phases"]["load"]["start_s"]
    before = [s for s in raw.samples if s["t"] < load_start]
    after = [s for s in raw.samples if s["t"] > load_start]
    assert before and all("mem_anon_bytes" not in s["values"] for s in before)
    assert any("mem_anon_bytes" in s["values"] for s in after)
    assert raw.meta["target"]["memory_label"] == "cgroup memory.current"


def test_managed_run_stops_before_starting_when_preflight_fails(tmp_path: Path) -> None:
    with FakeServer() as server:
        control = FakeControl(tmp_path, server)
        control.preflight_error = "Launcher instance(s) already running: coding"
        code, raw, _ = execute(tmp_path, server, control=control)

    assert code == ExitCode.PREFLIGHT_FAILED
    assert control.calls == ["preflight"]
    assert raw.samples == []
    assert "already running" in raw.meta["run"]["error"]


def test_managed_run_reports_a_failed_start_and_still_stops(tmp_path: Path) -> None:
    with FakeServer() as server:
        control = FakeControl(tmp_path, server)
        control.start_error = "Docker could not start the server: port is already allocated"
        code, raw, _ = execute(tmp_path, server, control=control)

    document = results_of(raw)
    assert code == ExitCode.PREFLIGHT_FAILED
    assert control.calls == ["preflight", "start", "stop"]
    assert next(p for p in document["phases"] if p["id"] == "load")["status"] == "failed"
    assert "port is already allocated" in raw.meta["run"]["error"]
    assert server.requests == []


def test_managed_run_fails_when_the_server_never_becomes_ready(tmp_path: Path) -> None:
    suite = SuiteConfig(**{**SUITE.__dict__, "load_timeout_s": 0.2})
    with FakeServer() as server:
        server.models = []
        control = FakeControl(tmp_path, server)
        code, raw, _ = execute(tmp_path, server, control=control, suite=suite)

    assert code == ExitCode.PREFLIGHT_FAILED
    assert "ready" in raw.meta["run"]["error"]
    assert control.calls[-1] == "stop"


def test_managed_run_fails_fast_when_the_container_dies_while_loading(tmp_path: Path) -> None:
    with FakeServer() as server:
        server.models = []
        control = FakeControl(tmp_path, server)
        control.running = False
        code, raw, _ = execute(tmp_path, server, control=control)

    assert code == ExitCode.PREFLIGHT_FAILED
    assert "stopped while loading" in raw.meta["run"]["error"]


def test_managed_run_stops_the_server_it_started_when_interrupted(tmp_path: Path) -> None:
    with FakeServer() as server:
        server.behave = lambda p: "hang" if "t1-8k-1." in str(p["messages"][0]["content"]) else None
        control = FakeControl(tmp_path, server)
        timer = threading.Timer(
            1.0, lambda: signal.pthread_kill(threading.main_thread().ident or 0, signal.SIGINT)
        )
        timer.start()
        try:
            code, raw, _ = execute(tmp_path, server, control=control)
        finally:
            timer.cancel()

    assert code == ExitCode.INTERRUPTED
    assert control.calls == ["preflight", "start", "stop"]
    assert raw.meta["phases"]["unload"]["status"] == "ok"
    assert "after_unload" not in raw.meta["phases"]


def test_managed_run_reports_a_failed_stop_as_a_problem(tmp_path: Path) -> None:
    with FakeServer() as server:
        control = FakeControl(tmp_path, server)
        control.stop_error = "Stop it yourself with: sudo docker stop llm-recipes-baseline"
        code, raw, _ = execute(tmp_path, server, control=control)

    assert code == ExitCode.CHECKS_FAILED
    assert raw.meta["phases"]["unload"]["status"] == "failed"
    assert "after_unload" not in raw.meta["phases"]
    assert any("sudo docker stop" in problem for problem in raw.meta["problems"])


def test_managed_run_leaves_the_server_running_when_asked(tmp_path: Path) -> None:
    with FakeServer() as server:
        control = FakeControl(tmp_path, server)
        code, raw, _ = execute(tmp_path, server, control=control, keep_running=True)

    assert code == ExitCode.OK
    assert "stop" not in control.calls
    assert "unload" not in raw.meta["phases"]
    assert "after_unload" not in raw.meta["phases"]


def test_managed_run_notes_when_the_server_does_not_settle(tmp_path: Path) -> None:
    suite = SuiteConfig(**{**SUITE.__dict__, "settle_server_cpu_cores": -1.0})
    with FakeServer() as server:
        control = FakeControl(tmp_path, server)
        code, raw, _ = execute(tmp_path, server, control=control, suite=suite)

    settle = next(p for p in results_of(raw)["phases"] if p["id"] == "settle")
    assert code == ExitCode.OK
    assert "did not settle" in settle["note"]


def test_managed_run_notes_when_the_server_was_already_settled(tmp_path: Path) -> None:
    suite = SuiteConfig(**{**SUITE.__dict__, "settle_seconds": 0.0})
    with FakeServer() as server:
        control = FakeControl(tmp_path, server)
        _, raw, _ = execute(tmp_path, server, control=control, suite=suite)

    settle = next(p for p in results_of(raw)["phases"] if p["id"] == "settle")
    assert "already settled" in settle["note"].lower()
    assert list(settle["metrics"]) == ["duration_s"]


def test_run_repeats_only_the_largest_context_and_reports_its_spread(tmp_path: Path) -> None:
    suite = SuiteConfig(
        **{
            **SUITE.__dict__,
            "contexts": (("context-small", 300), ("context-large", 600)),
            "largest_context_runs": 2,
        }
    )
    with FakeServer() as server:
        _, raw, _ = execute(tmp_path, server, suite=suite)

    document = results_of(raw)
    large, small = case_of(document, "context-large"), case_of(document, "context-small")
    assert (large["runs"], small["runs"]) == (2, 1)
    assert "noise_decode_spread" in large["metrics"]
    assert "noise_decode_spread" not in small["metrics"]
    large_prompts = [
        str(p["messages"][0]["content"])
        for p in server.requests
        if p.get("stream") and "context-large" in str(p["messages"][0]["content"])[:60]
    ]
    assert len(large_prompts) == 2 and large_prompts[0] != large_prompts[1]


def test_run_does_not_repeat_a_largest_context_that_was_skipped(tmp_path: Path) -> None:
    with FakeServer() as server:
        _, raw, _ = execute(tmp_path, server)

    skipped = [r for r in raw.requests if r.get("case") == "context-big"]
    assert len(skipped) == 1
    assert skipped[0]["status"] == "skipped"


def test_run_sizes_prompts_using_tabbyapi_chat_tokenizer(tmp_path: Path) -> None:
    with FakeServer() as server:
        _, raw, _ = execute(tmp_path, server, kind="tabbyapi")
    assert server.count_requests
    assert all("text" in body and "template_vars" in body for body in server.count_requests)
    probes = [r for r in raw.requests if r.get("case") == "context-8k"]
    assert all(abs(r["counted_input_tokens"] - 200) <= 2 for r in probes)


def test_run_enables_thinking_only_for_the_reasoning_request(tmp_path: Path) -> None:
    with FakeServer() as server:
        _, raw, _ = execute(tmp_path, server)

    def carries_snail(payload: dict[str, Any]) -> bool:
        return "snail" in str(payload["messages"][0]["content"])

    on = [p for p in server.requests if carries_snail(p)]
    off = [p for p in server.requests if not carries_snail(p)]
    assert len(on) == 1
    assert on[0]["reasoning_effort"] == "high"
    assert on[0]["max_completion_tokens"] == 1536
    assert all(p.get("reasoning_effort") == "none" for p in off)
    assert raw.meta["policy"]["reasoning_request"] == {"reasoning_effort": "high"}


def test_run_reports_the_reasoning_case_with_visible_and_reasoning_text(tmp_path: Path) -> None:
    with FakeServer() as server:
        server.reasoning_tokens = 3
        _, raw, _ = execute(tmp_path, server)

    metrics = case_of(results_of(raw), "reasoning-medium")["metrics"]
    other = case_of(results_of(raw), "context-8k")["metrics"]
    assert metrics["reasoning_chars"]["value"] == 15
    assert metrics["first_visible_output_s"]["value"] > metrics["first_output_s"]["value"]
    assert "reasoning_chars" not in other


def test_run_flags_reasoning_that_never_reaches_visible_output(tmp_path: Path) -> None:
    with FakeServer(output_tokens=0) as server:
        server.reasoning_tokens = 4
        code, raw, _ = execute(tmp_path, server)

    assert code != ExitCode.OK
    assert any("reasoning without visible output" in p for p in raw.meta["problems"])


def test_run_forces_tools_with_the_string_choice_form_when_server_rejects_objects(
    tmp_path: Path,
) -> None:
    def behave(payload: dict[str, Any]) -> str | None:
        if isinstance(payload.get("tool_choice"), dict):
            return "reject_tool_choice"
        return None

    with FakeServer() as server:
        server.behave = behave
        _, raw, _ = execute(tmp_path, server, kind="lmstudio")

    forced = [p for p in server.requests if p.get("tool_choice") == "required"]
    assert forced
    tools = next(c for c in results_of(raw)["functional"] if c["id"] == "tools")
    assert tools["status"] == "pass"


def test_run_forces_tools_with_the_named_object_choice_form_for_strata(
    tmp_path: Path,
) -> None:
    with FakeServer() as server:
        _, raw, _ = execute(tmp_path, server, kind="strata")

    forced = [p for p in server.requests if p.get("tool_choice") == functional.TOOL_CHOICE]
    assert forced
    tools = next(c for c in results_of(raw)["functional"] if c["id"] == "tools")
    assert tools["status"] == "pass"
