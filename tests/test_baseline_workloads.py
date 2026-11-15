"""Request policy, deterministic prompt construction, and case planning."""

import itertools
from pathlib import Path

import pytest
from baseline import workloads
from baseline.workloads import Document, SuiteConfig


def corpus(count: int = 12, size: int = 4000) -> list[Document]:
    return [
        Document(f"module_{n}.py", f"# module {n}\n" + ("x = 1\n" * (size // 6)))
        for n in range(count)
    ]


def test_policy_payload_carries_every_sampling_field_and_streaming_usage() -> None:
    payload = workloads.request_payload(
        "strata",
        "m",
        [{"role": "user", "content": "hi"}],
        workloads.PERFORMANCE,
        max_tokens=64,
        extra={},
        stream=True,
    )

    assert payload["temperature"] == 1.0
    assert payload["top_k"] == 20
    assert payload["top_p"] == 0.95
    assert payload["min_p"] == 0.0
    assert payload["repetition_penalty"] == 1.0
    assert payload["presence_penalty"] == 0.0
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}


def test_functional_policy_uses_temperature_zero() -> None:
    assert workloads.FUNCTIONAL.temperature == 0.0


@pytest.mark.parametrize(
    ("kind", "field", "other"),
    [
        ("strata", "max_completion_tokens", "max_tokens"),
        ("tabbyapi", "max_tokens", "max_completion_tokens"),
        ("lmstudio", "max_tokens", "max_completion_tokens"),
    ],
)
def test_request_payload_uses_the_token_limit_field_the_server_kind_accepts(
    kind: str, field: str, other: str
) -> None:
    payload = workloads.request_payload(
        kind, "m", [], workloads.PERFORMANCE, max_tokens=7, extra={}, stream=False
    )

    assert payload[field] == 7
    assert other not in payload
    assert "stream" not in payload


def test_request_payload_disables_thinking_for_strata_and_merges_user_extra() -> None:
    payload = workloads.request_payload(
        "strata", "m", [], workloads.PERFORMANCE, max_tokens=7, extra={"seed": 3}, stream=False
    )

    assert payload["reasoning_effort"] == "none"
    assert payload["seed"] == 3


def test_request_payload_lets_user_extra_override_defaults() -> None:
    payload = workloads.request_payload(
        "strata",
        "m",
        [],
        workloads.PERFORMANCE,
        max_tokens=7,
        extra={"reasoning_effort": "low"},
        stream=False,
    )

    assert payload["reasoning_effort"] == "low"


def test_thinking_control_is_unconfigured_for_servers_without_a_verified_field() -> None:
    assert workloads.thinking_request("strata", {}) == {"reasoning_effort": "none"}
    assert workloads.thinking_request("tabbyapi", {}) == {}


def test_load_corpus_reads_sorted_python_files_and_skips_tiny_ones(tmp_path: Path) -> None:
    (tmp_path / "b.py").write_text("b" * 3000)
    (tmp_path / "a.py").write_text("a" * 3000)
    (tmp_path / "tiny.py").write_text("x")
    (tmp_path / "notes.txt").write_text("n" * 3000)

    documents = workloads.load_corpus(tmp_path)

    assert [d.name for d in documents] == ["a.py", "b.py"]


def test_load_corpus_rejects_directory_without_usable_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no usable"):
        workloads.load_corpus(tmp_path)


def test_build_prompt_reaches_target_length_and_ends_with_the_task() -> None:
    prompt = workloads.build_prompt(
        corpus(), nonce="n1", variant=0, target_chars=10_000, task="DO IT"
    )

    assert prompt.chars == 10_000
    assert prompt.text.endswith("DO IT")
    assert prompt.text.startswith("Request n1.")


def test_build_prompt_differs_across_variants_and_nonces() -> None:
    first = workloads.build_prompt(corpus(), nonce="n1", variant=0, target_chars=9000, task="T")
    other_variant = workloads.build_prompt(
        corpus(), nonce="n1", variant=1, target_chars=9000, task="T"
    )
    other_nonce = workloads.build_prompt(
        corpus(), nonce="n2", variant=0, target_chars=9000, task="T"
    )

    assert first.content_sha256 != other_variant.content_sha256
    assert first.prompt_sha256 != other_nonce.prompt_sha256
    assert first.content_sha256 == other_nonce.content_sha256


def test_build_prompt_rejects_target_shorter_than_header_and_task() -> None:
    with pytest.raises(ValueError, match="shorter"):
        workloads.build_prompt(corpus(), nonce="n", variant=0, target_chars=10, task="T" * 50)


def test_build_prompt_is_deterministic() -> None:
    first = workloads.build_prompt(corpus(), nonce="n", variant=3, target_chars=9000, task="T")
    second = workloads.build_prompt(corpus(), nonce="n", variant=3, target_chars=9000, task="T")

    assert first == second


def test_build_prompt_rejects_target_larger_than_corpus() -> None:
    with pytest.raises(ValueError, match="corpus"):
        workloads.build_prompt(
            corpus(2, 600), nonce="n", variant=0, target_chars=1_000_000, task="T"
        )


@pytest.mark.parametrize(
    ("chars", "tokens", "expected"),
    [(30_000, 10_000, 3.0), (100, 10_000, 1.5), (1_000_000, 10, 8.0)],
)
def test_calibrate_computes_chars_per_token_within_sane_bounds(
    chars: int, tokens: int, expected: float
) -> None:
    assert workloads.calibrate(chars, tokens) == expected


def test_target_chars_applies_calibration_and_safety_margin() -> None:
    assert workloads.target_chars(10_000, 3.0) == int(10_000 * 3.0 * 0.97)


def test_plan_contexts_skips_cases_that_cannot_fit_input_plus_output() -> None:
    config = SuiteConfig(contexts=(("c-small", 1000), ("c-big", 4000)), context_output=500)

    plan = workloads.plan_contexts(config, context_tokens=2048)

    assert [(c.label, c.skip is None) for c in plan] == [("c-small", True), ("c-big", False)]
    assert "does not fit" in (plan[1].skip or "")
    assert "2,048" in (plan[1].skip or "")


def test_default_suite_matches_the_documented_matrix() -> None:
    config = SuiteConfig()

    assert [label for label, _ in config.contexts] == ["context-32k", "context-64k", "context-120k"]
    assert config.probe_tokens == 8192
    assert config.noise_runs == 5
    assert config.largest_context_runs == 2
    assert config.sustained_output == 2048
    assert config.sample_interval_s == 1.0


def irregular_count(prompt: workloads.Prompt) -> int:
    """A tokenizer stand-in whose chars-per-token ratio drifts with the prompt length."""
    return int(prompt.chars / (3.0 + (prompt.chars % 17) / 80))


def fit(target: int, count: object, initial: int = 3000) -> tuple[workloads.Prompt, int | None]:
    docs = corpus(60, 6000)
    return workloads.fit_prompt(
        lambda chars: workloads.build_prompt(
            docs, nonce="n", variant=1, target_chars=chars, task="T"
        ),
        count,  # type: ignore[arg-type]
        target,
        initial_chars=initial,
    )


@pytest.mark.parametrize("target", [500, 2000, 9000])
def test_fit_prompt_lands_just_under_the_target_token_count(target: int) -> None:
    _, tokens = fit(target, irregular_count)

    assert tokens is not None
    assert 0.9 * target <= tokens <= target


def test_fit_prompt_returns_unfitted_prompt_when_server_cannot_count() -> None:
    prompt, tokens = fit(1000, lambda prompt: None, initial=4000)

    assert tokens is None
    assert prompt.chars == 4000


def test_fit_prompt_never_returns_a_prompt_over_the_target_when_it_can_count() -> None:
    _, tokens = fit(700, lambda prompt: prompt.chars // 3 + 120)

    assert tokens is not None and tokens <= 700


def test_fit_prompt_aims_within_one_percent_below_the_target() -> None:
    _, tokens = fit(9000, lambda prompt: prompt.chars // 4)

    assert tokens is not None
    assert 0.99 * 9000 <= tokens <= 9000


def test_thinking_request_records_fields_after_overrides() -> None:
    assert workloads.thinking_request("strata", {}) == {"reasoning_effort": "none"}
    assert workloads.thinking_request("strata", {"reasoning_effort": "medium"}) == {
        "reasoning_effort": "medium"
    }
    assert workloads.thinking_request("tabbyapi", {}) == {}
    assert workloads.thinking_request(
        "tabbyapi", {"chat_template_kwargs": {"enable_thinking": True}, "temperature": 1}
    ) == {"chat_template_kwargs": {"enable_thinking": True}}


def test_conversation_turns_replay_cumulative_prefixes_ending_at_tool_results() -> None:
    turns = workloads.conversation_turns()

    assert [[m["role"] for m in turn] for turn in turns] == [
        ["user", "assistant", "tool"],
        ["user", "assistant", "tool", "assistant", "tool"],
        ["user", "assistant", "tool", "assistant", "tool", "assistant", "tool"],
    ]
    assert turns[0] == turns[1][:3] == turns[2][:3]
    assert turns[1] == turns[2][:5]


def test_conversation_turns_are_identical_across_calls() -> None:
    assert workloads.conversation_turns() == workloads.conversation_turns()


def test_conversation_turns_carry_tool_call_ids_matching_the_requests() -> None:
    turns = workloads.conversation_turns()

    for turn in turns:
        for message, following in itertools.pairwise(turn):
            for tool_call in message.get("tool_calls", []):
                assert following["role"] == "tool"
                assert following["tool_call_id"] == tool_call["id"]


def test_request_payload_case_extra_enables_thinking_above_runtime_defaults() -> None:
    payload = workloads.request_payload(
        "strata",
        "m",
        [{"role": "user", "content": "hi"}],
        workloads.PERFORMANCE,
        max_tokens=100,
        extra={},
        stream=True,
        case_extra={"reasoning_effort": "high"},
    )

    assert payload["reasoning_effort"] == "high"


def test_request_payload_user_extra_wins_over_case_extra() -> None:
    payload = workloads.request_payload(
        "strata",
        "m",
        [{"role": "user", "content": "hi"}],
        workloads.PERFORMANCE,
        max_tokens=100,
        extra={"reasoning_effort": "minimal"},
        stream=True,
        case_extra={"reasoning_effort": "high"},
    )

    assert payload["reasoning_effort"] == "minimal"


def test_reasoning_request_records_the_enabling_control_per_kind() -> None:
    assert workloads.reasoning_request("strata", {}) == {"reasoning_effort": "high"}
    assert workloads.reasoning_request("lmstudio", {}) == {}
    assert workloads.reasoning_request("strata", {"enable_thinking": False}) == {
        "reasoning_effort": "high",
        "enable_thinking": False,
    }
    assert workloads.reasoning_request("strata", {"reasoning_effort": "minimal"}) == {
        "reasoning_effort": "minimal"
    }


def test_request_payload_turns_off_thinking_for_lmstudio_via_chat_template_kwargs() -> None:
    payload = workloads.request_payload(
        "lmstudio", "m", [], workloads.PERFORMANCE, max_tokens=7, extra={}, stream=False
    )

    assert payload["chat_template_kwargs"] == {"enable_thinking": False}


def test_thinking_request_records_lmstudio_chat_template_kwargs() -> None:
    assert workloads.thinking_request("lmstudio", {}) == {
        "chat_template_kwargs": {"enable_thinking": False}
    }
    assert workloads.thinking_request("lmstudio", {"temperature": 1}) == {
        "chat_template_kwargs": {"enable_thinking": False}
    }
