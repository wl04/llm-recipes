"""Request policy, deterministic prompt construction, and case planning."""

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
    assert workloads.thinking_configured("strata") is True
    assert workloads.thinking_configured("tabbyapi") is False


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
    assert config.sustained_output == 2048
    assert config.sample_interval_s == 0.5
