"""Stream and response handling against stored server captures."""

import io
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest
from baseline import api

FIXTURES = Path(__file__).parent / "fixtures"
SYNTHETIC = FIXTURES / "synthetic-openai"


class Ticker:
    """Deterministic clock: each reading is 0.1 s after the previous one."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.1
        return self.now


def lines_of(path: Path) -> list[str]:
    return path.read_text().splitlines()


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*/stream.sse")), ids=lambda p: p.parent.name)
def test_read_stream_parses_stored_text_stream(path: Path) -> None:
    result = api.read_stream(lines_of(path), Ticker(), started=0.0)

    assert result.text
    assert result.first_output_s is not None
    assert result.finish_reason is not None


def test_read_stream_reads_usage_from_final_chunk_without_choices() -> None:
    result = api.read_stream(lines_of(SYNTHETIC / "stream.sse"), Ticker(), started=0.0)

    assert result.text == "def dedupe(items):"
    assert result.usage == api.Usage(prompt_tokens=21, completion_tokens=6, cached_tokens=0)


def test_read_stream_assembles_stored_tool_call() -> None:
    result = api.read_stream(lines_of(SYNTHETIC / "stream_tool_call.sse"), Ticker(), started=0.0)

    assert result.finish_reason == "tool_calls"
    assert result.tool_calls[0]["function"]["name"] == "get_temperature"
    assert json.loads(result.tool_calls[0]["function"]["arguments"]) == {"city": "Belgrade"}


def test_read_stream_rejects_stored_error_stream() -> None:
    with pytest.raises(api.ApiError, match="out of memory"):
        api.read_stream(lines_of(SYNTHETIC / "stream_error.sse"), Ticker(), started=0.0)


def test_read_stream_keeps_text_of_stored_truncated_stream() -> None:
    with pytest.raises(api.StreamInterrupted) as raised:
        api.read_stream(lines_of(SYNTHETIC / "stream_truncated.sse"), Ticker(), started=0.0)

    assert raised.value.partial.text == "def dedupe"


def test_parse_usage_reads_stored_chat_response() -> None:
    body = json.loads((SYNTHETIC / "chat.json").read_text())

    usage = api.parse_usage(body["usage"])

    assert usage == api.Usage(prompt_tokens=21, completion_tokens=6, cached_tokens=0)


def test_post_json_reports_stored_error_body_with_status() -> None:
    body = (SYNTHETIC / "error.json").read_bytes()

    def opener(request: Any, timeout: float) -> object:
        raise HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(body))  # type: ignore[arg-type]

    with pytest.raises(api.ApiError, match=r"(?s)HTTP 404.*model not found"):
        api.post_json("http://h:1", "/v1/chat/completions", {}, timeout=5, opener=opener)
