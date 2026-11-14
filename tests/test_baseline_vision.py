"""Vision-check expectations and scoring of the model's answer."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from baseline import schema, vision

ROOT = Path(__file__).resolve().parents[1]
EXPECTATIONS = ROOT / "assets/checks/amdgpu-top.expected.json"


def expectations(*items: dict[str, Any]) -> vision.Expectations:
    return vision.Expectations(
        version=1,
        image="x.png",
        image_sha256="0" * 64,
        instruction="Read it.",
        items=tuple(
            vision.Expectation(
                id=item["id"],
                tier=item["tier"],
                description=item.get("description", item["id"]),
                all_of=tuple(item["all_of"]),
            )
            for item in items
        ),
    )


SAMPLE = expectations(
    {"id": "app", "tier": "identity", "all_of": ["amdgpu_top"]},
    {"id": "vram", "tier": "detail", "all_of": ["15737", "16304"]},
    {"id": "version", "tier": "detail", "all_of": ["0.11.5"]},
)


def outcomes(score: vision.VisionScore) -> dict[str, str]:
    return {field.id: field.outcome for field in score.fields}


def test_load_expectations_matches_repository_image_hash() -> None:
    loaded = vision.load_expectations(EXPECTATIONS)

    image = EXPECTATIONS.parent / loaded.image
    assert hashlib.sha256(image.read_bytes()).hexdigest() == loaded.image_sha256
    assert {item.tier for item in loaded.items} == {"identity", "detail"}


def test_load_expectations_rejects_unknown_tier(tmp_path: Path) -> None:
    path = tmp_path / "e.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "image": "x.png",
                "image_sha256": "0" * 64,
                "instruction": "Read it.",
                "expectations": [{"id": "a", "tier": "bonus", "description": "d", "all_of": ["x"]}],
            }
        )
    )

    with pytest.raises(ValueError, match="tier"):
        vision.load_expectations(path)


@pytest.mark.parametrize(
    "items",
    [
        [],
        [{"id": "a", "tier": "identity", "description": "d", "all_of": []}],
        [
            {"id": "a", "tier": "identity", "description": "d", "all_of": ["x"]},
            {"id": "a", "tier": "detail", "description": "d", "all_of": ["y"]},
        ],
    ],
    ids=["none", "no-tokens", "duplicate-id"],
)
def test_load_expectations_rejects_invalid_items(tmp_path: Path, items: list[Any]) -> None:
    path = tmp_path / "e.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "image": "x.png",
                "image_sha256": "0" * 64,
                "instruction": "Read it.",
                "expectations": items,
            }
        )
    )

    with pytest.raises(ValueError, match="expectations"):
        vision.load_expectations(path)


def test_build_prompt_lists_every_field_and_asks_for_json() -> None:
    prompt = vision.build_prompt(SAMPLE)

    assert all(item.id in prompt for item in SAMPLE.items)
    assert "JSON" in prompt


@pytest.mark.parametrize(
    "text",
    [
        '{"app": "amdgpu_top"}',
        '```json\n{"app": "amdgpu_top"}\n```',
        'Here you go: {"app": "amdgpu_top"} Hope that helps.',
        '{"nested": {"a": 1}} {"app": "amdgpu_top"}',
    ],
    ids=["plain", "fenced", "surrounded", "first-object-wins"],
)
def test_extract_answer_finds_first_json_object(text: str) -> None:
    answer = vision.extract_answer(text)

    assert answer is not None
    assert answer.get("app") == "amdgpu_top" or "nested" in answer


@pytest.mark.parametrize("text", ["no json here", "[1, 2]", '{"broken": ', ""])
def test_extract_answer_returns_none_without_object(text: str) -> None:
    assert vision.extract_answer(text) is None


def test_score_answer_passes_when_all_fields_match() -> None:
    answer = '{"app": "amdgpu_top v0.11.5", "vram": "15,737 / 16,304 MiB", "version": "v0.11.5"}'

    score = vision.score_answer(SAMPLE, answer)

    assert score.status == "pass"
    assert outcomes(score) == {"app": "match", "vram": "match", "version": "match"}


def test_score_answer_normalizes_case_and_thousands_separators() -> None:
    answer = '{"app": "AMDGPU_TOP", "vram": "15737 MiB of 16\u202f304 MiB", "version": null}'

    score = vision.score_answer(SAMPLE, answer)

    assert outcomes(score) == {"app": "match", "vram": "match", "version": "missing"}


def test_score_answer_reports_mismatch_without_failing_detail_tier() -> None:
    answer = '{"app": "amdgpu_top", "vram": "12,000 / 16,304 MiB", "version": "0.11.5"}'

    score = vision.score_answer(SAMPLE, answer)

    assert score.status == "pass"
    assert outcomes(score)["vram"] == "mismatch"


def test_score_answer_fails_when_identity_field_is_wrong() -> None:
    answer = '{"app": "nvidia-smi", "vram": "15737 / 16304", "version": "0.11.5"}'

    score = vision.score_answer(SAMPLE, answer)

    assert score.status == "fail"
    assert outcomes(score)["app"] == "mismatch"


def test_score_answer_fails_when_identity_field_is_missing() -> None:
    score = vision.score_answer(SAMPLE, '{"vram": "15737 / 16304"}')

    assert score.status == "fail"
    assert outcomes(score)["app"] == "missing"


def test_score_answer_reports_unparsed_and_keeps_answer_text() -> None:
    score = vision.score_answer(SAMPLE, "I see a dashboard.")

    assert score.status == "unparsed"
    assert score.answer == "I see a dashboard."
    assert {field.outcome for field in score.fields} == {"missing"}


def test_score_answer_does_not_match_numbers_inside_longer_numbers() -> None:
    sample = expectations({"id": "gtt", "tier": "detail", "all_of": ["116"]})

    score = vision.score_answer(sample, '{"gtt": "1160 / 30328"}')

    assert outcomes(score) == {"gtt": "mismatch"}


def test_score_answer_accepts_list_and_number_values() -> None:
    sample = expectations(
        {"id": "headings", "tier": "detail", "all_of": ["grbm", "sensors"]},
        {"id": "count", "tier": "detail", "all_of": ["4"]},
    )

    score = vision.score_answer(sample, '{"headings": ["GRBM", "Sensors"], "count": 4}')

    assert outcomes(score) == {"headings": "match", "count": "match"}


def test_to_result_produces_valid_functional_entry_with_tier_counts() -> None:
    answer = '{"app": "amdgpu_top", "vram": "wrong", "version": null}'
    score = vision.score_answer(SAMPLE, answer)

    entry = score.to_result(SAMPLE)

    assert entry["id"] == "vision"
    assert entry["status"] == "pass"
    assert entry["scores"] == {
        "identity": {"match": 1, "mismatch": 0, "missing": 0},
        "detail": {"match": 0, "mismatch": 1, "missing": 1},
    }
    assert entry["answer"] == answer
    document = {
        "schema_version": 1,
        "suite_version": "1",
        "recipe": "r",
        "run": {"status": "complete"},
        "server": {"kind": "strata", "model": "m", "context_tokens": 1},
        "functional": [entry],
        "cases": [],
    }
    schema.validate_results(document)
