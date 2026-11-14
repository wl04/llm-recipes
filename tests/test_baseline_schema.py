"""Baseline result contract: metric representation, validation, and serialization."""

import copy
import json
from typing import Any

import pytest
from baseline import schema
from baseline_data import sample_results


def valid_results() -> dict[str, Any]:
    return sample_results()


def test_measured_records_value_unit_and_source() -> None:
    metric = schema.measured(12.5, "s", "client monotonic clock")

    assert metric == {"value": 12.5, "unit": "s", "source": "client monotonic clock"}


def test_unavailable_records_null_value_and_reason() -> None:
    metric = schema.unavailable("sensor not readable")

    assert metric == {"value": None, "unavailable": "sensor not readable"}


def test_validate_results_accepts_complete_document() -> None:
    schema.validate_results(valid_results())


def test_validate_results_preserves_unavailable_metric_through_serialization() -> None:
    document = valid_results()

    restored = json.loads(schema.dump_results(document))

    schema.validate_results(restored)
    assert restored["cases"][0]["metrics"]["engine_decode_tok_s"]["value"] is None


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("schema_version",), 2, "schema_version"),
        (("suite_version",), "", "suite_version"),
        (("run", "status"), "unknown", "run.status"),
        (("server", "kind"), "other", "server.kind"),
        (("server", "context_tokens"), "big", "server.context_tokens"),
        (("cases", 0, "status"), "maybe", "cases[0].status"),
        (("cases", 0, "runs"), -1, "cases[0].runs"),
        (("functional", 0, "status"), "maybe", "functional[0].status"),
        (("resources", 0, "case"), "missing-case", "resources[0].case"),
        (("phases", 0, "status"), "maybe", "phases[0].status"),
        (("phases", 1, "id"), "", "phases[1].id"),
        (("warmup", "converged"), "yes", "warmup.converged"),
        (("warmup", "requests"), -1, "warmup.requests"),
        (("boot", "warnings"), "text", "boot.warnings"),
    ],
)
def test_validate_results_rejects_invalid_field(
    path: tuple[str | int, ...], value: object, message: str
) -> None:
    document = valid_results()
    target: Any = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValueError, match=message.replace("[", r"\[").replace("]", r"\]")):
        schema.validate_results(document)


@pytest.mark.parametrize(
    "metric",
    [
        {"value": 1.0, "unit": "s"},
        {"value": None},
        {"value": None, "unavailable": ""},
        {"value": float("nan"), "unit": "s", "source": "x"},
        {"value": True, "unit": "s", "source": "x"},
        {"value": "12", "unit": "s", "source": "x"},
        {"value": 0, "unavailable": "reason"},
    ],
    ids=["no-source", "no-reason", "empty-reason", "nan", "bool", "string", "zero-as-missing"],
)
def test_validate_results_rejects_malformed_metric(metric: dict[str, Any]) -> None:
    document = valid_results()
    document["cases"][0]["metrics"]["bad"] = metric

    with pytest.raises(ValueError, match="bad"):
        schema.validate_results(document)


def test_validate_results_rejects_duplicate_case_ids() -> None:
    document = valid_results()
    document["cases"].append(copy.deepcopy(document["cases"][0]))

    with pytest.raises(ValueError, match="duplicate"):
        schema.validate_results(document)


def test_validate_results_rejects_missing_top_level_key() -> None:
    document = valid_results()
    del document["cases"]

    with pytest.raises(ValueError, match="cases"):
        schema.validate_results(document)


def test_validate_results_rejects_non_mapping_document() -> None:
    with pytest.raises(ValueError, match="mapping"):
        schema.validate_results([])


def test_dump_results_is_deterministic_with_trailing_newline() -> None:
    first = schema.dump_results(valid_results())
    second = schema.dump_results(valid_results())

    assert first == second
    assert first.endswith("}\n")
    assert '\n  "schema_version": 1,' in first


def test_exit_codes_are_distinct_and_stable() -> None:
    assert {code.name: int(code) for code in schema.ExitCode} == {
        "OK": 0,
        "CHECKS_FAILED": 1,
        "USAGE": 2,
        "PREFLIGHT_FAILED": 3,
        "INTERRUPTED": 130,
    }
