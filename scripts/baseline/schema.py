"""Result contract shared by the runner, the offline renderer, and the document generator.

A result document is plain JSON. Every number carries a unit and a measurement source, and a
measurement that could not be taken is ``null`` with a stated reason, never zero or omitted.
"""

import json
import math
from enum import IntEnum
from typing import Any

SCHEMA_VERSION = 1
SUITE_VERSION = "3"

RUN_STATUSES = ("complete", "interrupted", "failed")
SERVER_KINDS = ("strata", "tabbyapi", "lmstudio")
CASE_STATUSES = ("ok", "insufficient_sample", "failed", "skipped")
FUNCTIONAL_STATUSES = ("pass", "fail", "unparsed", "skipped")
PHASE_STATUSES = ("ok", "failed", "skipped", "interrupted")
REQUIRED_KEYS = ("schema_version", "suite_version", "recipe", "run", "server", "cases")


class ExitCode(IntEnum):
    """Process exit statuses of the baseline command."""

    OK = 0
    CHECKS_FAILED = 1
    USAGE = 2
    PREFLIGHT_FAILED = 3
    INTERRUPTED = 130


def measured(value: float, unit: str, source: str) -> dict[str, Any]:
    """Describe a taken measurement with its unit and where the number came from."""
    return {"value": value, "unit": unit, "source": source}


def unavailable(reason: str) -> dict[str, Any]:
    """Describe a measurement that could not be taken and why."""
    return {"value": None, "unavailable": reason}


def dump_results(document: dict[str, Any]) -> str:
    """Serialize deterministically: insertion key order, two-space indent, trailing newline."""
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _sequence(value: object, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _choice(value: object, choices: tuple[str, ...], name: str) -> None:
    if value not in choices:
        raise ValueError(f"{name} must be one of: {', '.join(choices)}")


def _validate_metrics(value: object, name: str) -> None:
    for key, metric in _mapping(value, name).items():
        label = f"{name}.{key}"
        item = _mapping(metric, label)
        if item.get("value") is None:
            if set(item) != {"value", "unavailable"}:
                raise ValueError(f"{label}: an unavailable metric needs only a reason")
            _text(item["unavailable"], f"{label}.unavailable")
            continue
        number = item["value"]
        if isinstance(number, bool) or not isinstance(number, int | float):
            raise ValueError(f"{label}.value must be a number")
        if not math.isfinite(number):
            raise ValueError(f"{label}.value must be finite")
        if set(item) != {"value", "unit", "source"}:
            raise ValueError(f"{label}: a measured metric needs value, unit, and source")
        _text(item["unit"], f"{label}.unit")
        _text(item["source"], f"{label}.source")


def _validate_functional(entries: object) -> None:
    """Check each functional check entry."""
    for index, entry in enumerate(_sequence(entries, "functional")):
        item = _mapping(entry, f"functional[{index}]")
        _text(item.get("id"), f"functional[{index}].id")
        _choice(item.get("status"), FUNCTIONAL_STATUSES, f"functional[{index}].status")


def _validate_boot(data: dict[str, object]) -> None:
    """Check the optional cold-boot section."""
    boot = _mapping(data["boot"], "boot")
    _validate_metrics(boot.get("metrics", {}), "boot.metrics")
    for note in _sequence(boot.get("warnings", []), "boot.warnings"):
        _text(note, "boot.warnings entry")


def _validate_warmup(data: dict[str, object]) -> None:
    """Check the optional warmup section."""
    warmup = _mapping(data["warmup"], "warmup")
    requests = warmup.get("requests")
    if type(requests) is not int or requests < 0:
        raise ValueError("warmup.requests must be a non-negative integer")
    if type(warmup.get("converged")) is not bool:
        raise ValueError("warmup.converged must be true or false")
    _validate_metrics(warmup.get("metrics", {}), "warmup.metrics")


def _validate_phases(entries: object) -> None:
    """Check each run phase entry."""
    for index, entry in enumerate(_sequence(entries, "phases")):
        item = _mapping(entry, f"phases[{index}]")
        _text(item.get("id"), f"phases[{index}].id")
        _choice(item.get("status"), PHASE_STATUSES, f"phases[{index}].status")
        _validate_metrics(item.get("metrics", {}), f"phases[{index}].metrics")


def _validate_cases(entries: object) -> set[str]:
    """Check every case entry and return the case identifiers they declare."""
    case_ids: set[str] = set()
    for index, entry in enumerate(_sequence(entries, "cases")):
        name = f"cases[{index}]"
        item = _mapping(entry, name)
        case_id = _text(item.get("id"), f"{name}.id")
        if case_id in case_ids:
            raise ValueError(f"{name}.id is a duplicate: {case_id}")
        case_ids.add(case_id)
        _choice(item.get("status"), CASE_STATUSES, f"{name}.status")
        runs = item.get("runs")
        if type(runs) is not int or runs < 0:
            raise ValueError(f"{name}.runs must be a non-negative integer")
        _validate_metrics(item.get("metrics", {}), f"{name}.metrics")
    return case_ids


def _validate_resources(entries: object, case_ids: set[str]) -> None:
    """Check each resource entry and that it names a declared case."""
    for index, entry in enumerate(_sequence(entries, "resources")):
        name = f"resources[{index}]"
        item = _mapping(entry, name)
        if item.get("case") not in case_ids:
            raise ValueError(f"{name}.case must name an existing case")
        _validate_metrics(item.get("metrics", {}), f"{name}.metrics")


def validate_results(document: object) -> None:
    """Reject a document that violates the contract.

    Raises:
        ValueError: names the first offending field.
    """
    data = _mapping(document, "results")
    for key in REQUIRED_KEYS:
        if key not in data:
            raise ValueError(f"results is missing {key}")
    if data["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    _text(data["suite_version"], "suite_version")
    _text(data["recipe"], "recipe")
    _choice(_mapping(data["run"], "run").get("status"), RUN_STATUSES, "run.status")
    server = _mapping(data["server"], "server")
    _choice(server.get("kind"), SERVER_KINDS, "server.kind")
    _text(server.get("model"), "server.model")
    context = server.get("context_tokens")
    if type(context) is not int or context < 1:
        raise ValueError("server.context_tokens must be a positive integer")
    _validate_functional(data.get("functional", []))
    if "boot" in data:
        _validate_boot(data)
    if "warmup" in data:
        _validate_warmup(data)
    _validate_phases(data.get("phases", []))
    case_ids = _validate_cases(data["cases"])
    _validate_resources(data.get("resources", []), case_ids)


SESSION_SCHEMA_VERSION = 1
SESSION_KIND = "session"
SESSION_ENGINES = ("strata", "tabbyapi", "lm-studio")
SESSION_COUNT_KEYS = (
    "requests",
    "cancelled",
    "unclosed_requests",
    "prompt_tokens",
    "reused_prompt_tokens",
    "read_prompt_tokens",
    "generated_tokens",
    "drafts_accepted",
    "drafts_proposed",
)
SESSION_RATE_KEYS = (
    "prefill_seconds",
    "decode_seconds",
    "prefill_tok_s",
    "decode_tok_s",
    "decode_tok_s_median",
    "draft_acceptance",
)


def _count(value: object, name: str) -> None:
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError(f"{name} must be a non-negative integer or null")


def _nonnegative_number(value: object, name: str) -> None:
    if value is None:
        return
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number or null")


def validate_session(document: object) -> None:
    """Validate a session-results.json document produced by the session report.

    Raises:
        ValueError: names the first offending field.
    """
    data = _mapping(document, "session results")
    for key in ("schema_version", "kind", "engine", "window", "availability", "totals"):
        if key not in data:
            raise ValueError(f"session results is missing {key}")
    version = data["schema_version"]
    if type(version) is not int or version != SESSION_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SESSION_SCHEMA_VERSION}")
    if data["kind"] != SESSION_KIND:
        raise ValueError(f"kind must be {SESSION_KIND!r}")
    _choice(data.get("engine"), SESSION_ENGINES, "engine")
    for key in ("first_request", "last_request"):
        value = data.get(key)
        if value is not None:
            _text(value, key)
    for index, name in enumerate(_sequence(data.get("log_files"), "log_files")):
        _text(name, f"log_files[{index}]")
    window = _mapping(data["window"], "window")
    for key in ("since", "until"):
        if key not in window:
            raise ValueError(f"window is missing {key}")
        value = window.get(key)
        if value is not None:
            _text(value, f"window.{key}")
    availability = _mapping(data["availability"], "availability")
    for key in ("timestamps", "draft_acceptance", "unclosed_requests"):
        if key not in availability:
            raise ValueError(f"availability is missing {key}")
    for key, value in availability.items():
        if type(value) is not bool:
            raise ValueError(f"availability.{key} must be true or false")
    totals = _mapping(data["totals"], "totals")
    for key in SESSION_COUNT_KEYS:
        _count(totals.get(key), f"totals.{key}")
    for key in SESSION_RATE_KEYS:
        _nonnegative_number(totals.get(key), f"totals.{key}")
    buckets = _sequence(totals.get("context_buckets"), "totals.context_buckets")
    for index, entry in enumerate(buckets):
        name = f"context_buckets[{index}]"
        item = _mapping(entry, name)
        _text(item.get("label"), f"{name}.label")
        for key in ("requests", "prompt_tokens", "generated_tokens"):
            _count(item.get(key), f"{name}.{key}")
