"""Vision check: expected screenshot fields, the prompt that requests them, and scoring.

The answer is requested as a JSON object keyed by expectation id. Each field is scored as
``match``, ``mismatch`` (a different value, such as a misread), or ``missing``. The check passes
when every ``identity`` field matches; ``detail`` fields are informational because small
on-screen text depends strongly on the image-token budget.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TIERS = ("identity", "detail")
OUTCOMES = ("match", "mismatch", "missing")
_THOUSANDS = re.compile(r"(?<=\d)[,\u202f\u00a0\u2009](?=\d{3}(?!\d))")
_NUMERIC = re.compile(r"[0-9.]+")


@dataclass(frozen=True)
class Expectation:
    """One field of the screenshot: every token in ``all_of`` must appear in the answer."""

    id: str
    tier: str
    description: str
    all_of: tuple[str, ...]


@dataclass(frozen=True)
class Expectations:
    """The expected fields for one image, bound to the image by hash."""

    version: int
    image: str
    image_sha256: str
    instruction: str
    items: tuple[Expectation, ...]


@dataclass(frozen=True)
class FieldScore:
    id: str
    tier: str
    outcome: str


@dataclass(frozen=True)
class VisionScore:
    """Scored answer: ``status`` is ``pass``, ``fail``, or ``unparsed``."""

    status: str
    fields: tuple[FieldScore, ...]
    answer: str

    def to_result(self, expectations: Expectations) -> dict[str, Any]:
        """Describe the check as a functional entry of the result document."""
        scores = {
            tier: {
                outcome: sum(1 for f in self.fields if f.tier == tier and f.outcome == outcome)
                for outcome in OUTCOMES
            }
            for tier in TIERS
        }
        return {
            "id": "vision",
            "status": self.status,
            "image_sha256": expectations.image_sha256,
            "expectations_version": expectations.version,
            "scores": scores,
            "fields": [
                {"id": field.id, "tier": field.tier, "outcome": field.outcome}
                for field in self.fields
            ],
            "answer": self.answer,
        }


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"expectations {name} must be a nonempty string")
    return value


def load_expectations(path: Path) -> Expectations:
    """Read and validate an expectations file.

    Raises:
        OSError: the file cannot be read.
        ValueError: the file is not valid JSON or violates the format.
    """
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ValueError(f"expectations file {path} is not valid JSON") from error
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("expectations must be a mapping with version 1")
    sha = _text(data.get("image_sha256"), "image_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("expectations image_sha256 must be 64 lowercase hex digits")
    raw_items = data.get("expectations")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("expectations must list at least one field")
    items: list[Expectation] = []
    for index, raw in enumerate(raw_items):
        name = f"expectations[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{name} must be a mapping")
        if raw.get("tier") not in TIERS:
            raise ValueError(f"{name}.tier must be one of: {', '.join(TIERS)}")
        tokens = raw.get("all_of")
        if not isinstance(tokens, list) or not tokens:
            raise ValueError(f"{name}.all_of must list at least one token")
        item = Expectation(
            id=_text(raw.get("id"), f"{name}.id"),
            tier=raw["tier"],
            description=_text(raw.get("description"), f"{name}.description"),
            all_of=tuple(_text(token, f"{name}.all_of") for token in tokens),
        )
        if any(existing.id == item.id for existing in items):
            raise ValueError(f"{name}.id duplicates an earlier expectations id: {item.id}")
        items.append(item)
    return Expectations(
        version=1,
        image=_text(data.get("image"), "image"),
        image_sha256=sha,
        instruction=_text(data.get("instruction"), "instruction"),
        items=tuple(items),
    )


def build_prompt(expectations: Expectations) -> str:
    """Compose the vision prompt from the expectations so the two cannot drift apart."""
    fields = "\n".join(f"- {item.id}: {item.description}" for item in expectations.items)
    return (
        f"{expectations.instruction}\n\nFields:\n{fields}\n\n"
        "Reply with only a JSON object whose keys are the field names above."
    )


def extract_answer(text: str) -> dict[str, Any] | None:
    """Return the first JSON object found in ``text``, tolerating fences and surrounding prose."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def normalize(text: str) -> str:
    """Lowercase, drop thousands separators inside numbers, and collapse whitespace."""
    return " ".join(_THOUSANDS.sub("", text.lower()).split())


def _contains(haystack: str, token: str) -> bool:
    wanted = normalize(token)
    if _NUMERIC.fullmatch(wanted):
        return re.search(rf"(?<!\d){re.escape(wanted)}(?!\d)", haystack) is not None
    return wanted in haystack


def _value_text(value: object) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return normalize(text) if text.strip() else None


def score_answer(expectations: Expectations, answer_text: str) -> VisionScore:
    """Score the model's answer text against the expectations."""
    answer = extract_answer(answer_text)
    fields: list[FieldScore] = []
    for item in expectations.items:
        value = _value_text(answer.get(item.id)) if answer is not None else None
        if value is None:
            outcome = "missing"
        elif all(_contains(value, token) for token in item.all_of):
            outcome = "match"
        else:
            outcome = "mismatch"
        fields.append(FieldScore(item.id, item.tier, outcome))
    if answer is None:
        status = "unparsed"
    elif all(f.outcome == "match" for f in fields if f.tier == "identity"):
        status = "pass"
    else:
        status = "fail"
    return VisionScore(status, tuple(fields), answer_text)
