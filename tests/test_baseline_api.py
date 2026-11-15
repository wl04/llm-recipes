"""OpenAI-compatible request and stream handling without a server."""

import io
import json
from collections.abc import Iterator
from typing import Any
from urllib.error import HTTPError

import pytest
from baseline import api, stats


def event(**delta: Any) -> str:
    return "data: " + json.dumps({"choices": [{"delta": delta}]})


def clock_of(*values: float) -> Iterator[float]:
    return iter(values)


def test_read_stream_collects_text_usage_and_finish_reason() -> None:
    lines = [
        event(role="assistant"),
        event(content="Hel"),
        event(content="lo"),
        "data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]}),
        "data: "
        + json.dumps(
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 2,
                    "prompt_tokens_details": {"cached_tokens": 4},
                },
            }
        ),
        "data: [DONE]",
    ]

    result = api.read_stream(lines, clock_of(1.0, 2.0).__next__, started=0.0)

    assert result.text == "Hello"
    assert result.finish_reason == "stop"
    assert result.usage == api.Usage(prompt_tokens=12, completion_tokens=2, cached_tokens=4)


def test_read_stream_measures_first_and_last_output_from_request_start() -> None:
    lines = [event(role="assistant"), event(content="a"), event(content="b"), "data: [DONE]"]

    result = api.read_stream(lines, clock_of(12.5, 13.5).__next__, started=10.0)

    assert (result.first_output_s, result.last_output_s) == (2.5, 3.5)


def test_read_stream_counts_reasoning_delta_as_first_output() -> None:
    lines = [event(reasoning_content="thinking"), event(content="answer"), "data: [DONE]"]

    result = api.read_stream(lines, clock_of(1.0, 2.0).__next__, started=0.0)

    assert (result.first_output_s, result.reasoning, result.text) == (1.0, "thinking", "answer")


def test_read_stream_separates_first_visible_output_from_first_reasoning() -> None:
    lines = [
        event(role="assistant"),
        event(reasoning_content="Thinking"),
        event(content="Answer"),
        "data: [DONE]",
    ]

    result = api.read_stream(lines, clock_of(1.0, 5.0).__next__, started=0.0)

    assert result.first_output_s == 1.0
    assert result.first_content_s == 5.0


def test_read_stream_has_no_first_content_when_reply_is_all_reasoning() -> None:
    lines = [event(reasoning_content="Thinking"), "data: [DONE]"]

    result = api.read_stream(lines, clock_of(1.0).__next__, started=0.0)

    assert result.first_output_s == 1.0
    assert result.first_content_s is None


def test_read_stream_assembles_tool_call_fragments() -> None:
    first = {
        "index": 0,
        "id": "call_1",
        "function": {"name": "get_temperature", "arguments": '{"ci'},
    }
    second = {"index": 0, "function": {"arguments": 'ty":"Belgrade"}'}}
    lines = [event(tool_calls=[first]), event(tool_calls=[second]), "data: [DONE]"]

    result = api.read_stream(lines, clock_of(1.0, 2.0).__next__, started=0.0)

    assert result.tool_calls == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "get_temperature", "arguments": '{"city":"Belgrade"}'},
        }
    ]
    assert result.first_output_s == 1.0


def test_read_stream_ignores_comments_and_blank_lines() -> None:
    lines = [": keep-alive", "", event(content="x"), "", "data: [DONE]"]

    result = api.read_stream(lines, clock_of(1.0).__next__, started=0.0)

    assert result.text == "x"


def test_read_stream_without_output_has_no_timings() -> None:
    result = api.read_stream(["data: [DONE]"], clock_of().__next__, started=0.0)

    assert (result.text, result.first_output_s, result.last_output_s) == ("", None, None)


def test_read_stream_rejects_error_event() -> None:
    lines = [event(content="x"), 'data: {"error": {"message": "out of memory"}}']

    with pytest.raises(api.ApiError, match="out of memory"):
        api.read_stream(lines, clock_of(1.0).__next__, started=0.0)


def test_read_stream_keeps_partial_result_when_stream_is_interrupted() -> None:
    lines = [event(content="par"), event(content="tial")]

    with pytest.raises(api.StreamInterrupted) as raised:
        api.read_stream(lines, clock_of(1.0, 2.0).__next__, started=0.0)

    assert raised.value.partial.text == "partial"
    assert raised.value.partial.last_output_s == 2.0


def test_read_stream_rejects_malformed_event() -> None:
    with pytest.raises(api.ApiError, match="malformed"):
        api.read_stream(["data: {not json"], clock_of().__next__, started=0.0)


def test_parse_usage_leaves_cached_tokens_unknown_when_absent() -> None:
    usage = api.parse_usage({"prompt_tokens": 5, "completion_tokens": 1})

    assert usage == api.Usage(prompt_tokens=5, completion_tokens=1, cached_tokens=None)


def test_parse_usage_returns_none_when_server_reports_no_usage() -> None:
    assert api.parse_usage(None) is None


def test_parse_usage_rejects_non_integer_counts() -> None:
    with pytest.raises(api.ApiError, match="prompt_tokens"):
        api.parse_usage({"prompt_tokens": "many", "completion_tokens": 1})


@pytest.mark.parametrize(
    ("tokens", "first", "last", "expected"),
    [
        (101, 1.0, 3.0, 50.0),
        (2, 1.0, 1.5, 2.0),
        (1, 1.0, 2.0, None),
        (10, 2.0, 2.0, None),
        (10, None, 3.0, None),
        (None, 1.0, 3.0, None),
    ],
)
def test_client_decode_rate_estimates_tokens_after_first_output(
    tokens: int | None, first: float | None, last: float | None, expected: float | None
) -> None:
    assert stats.client_decode_rate(tokens, first, last) == expected


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([10.0, 11.0, 12.0], 2 / 11),
        ([5.0, 5.0], 0.0),
        ([4.0], None),
        ([], None),
        ([0.0, 0.0], None),
    ],
)
def test_relative_spread_is_range_over_median(values: list[float], expected: float | None) -> None:
    result = stats.relative_spread(values)

    assert result == pytest.approx(expected) if expected is not None else result is None


class FakeResponse(io.BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def test_post_json_returns_parsed_body_and_sends_json() -> None:
    sent: list[Any] = []

    def opener(request: Any, timeout: float) -> FakeResponse:
        sent.append((request.full_url, json.loads(request.data), timeout))
        return FakeResponse(b'{"ok": true}')

    result = api.post_json("http://h:1", "/v1/x", {"a": 1}, timeout=5, opener=opener)

    assert result == {"ok": True}
    assert sent == [("http://h:1/v1/x", {"a": 1}, 5)]


def test_post_json_includes_status_and_body_on_http_error() -> None:
    def opener(request: Any, timeout: float) -> FakeResponse:
        raise HTTPError(request.full_url, 400, "Bad", {}, io.BytesIO(b'{"detail":"bad model"}'))  # type: ignore[arg-type]

    with pytest.raises(api.ApiError, match=r"HTTP 400.*bad model"):
        api.post_json("http://h:1", "/v1/x", {}, timeout=5, opener=opener)


def test_post_json_rejects_error_object_in_successful_response() -> None:
    def opener(request: Any, timeout: float) -> FakeResponse:
        return FakeResponse(b'{"error": {"message": "model not loaded"}}')

    with pytest.raises(api.ApiError, match="model not loaded"):
        api.post_json("http://h:1", "/v1/x", {}, timeout=5, opener=opener)


def test_require_model_rejects_mismatched_identity() -> None:
    with pytest.raises(api.ApiError, match=r"expected-model.*other-model"):
        api.require_model(["other-model"], "expected-model")


def test_require_model_accepts_loaded_model() -> None:
    api.require_model(["a", "expected-model"], "expected-model")


def test_read_stream_keeps_partial_result_when_connection_breaks() -> None:
    def lines() -> Iterator[str]:
        yield event(content="before")
        raise ConnectionResetError("reset")

    with pytest.raises(api.StreamInterrupted, match="reset") as raised:
        api.read_stream(lines(), clock_of(1.0).__next__, started=0.0)

    assert raised.value.partial.text == "before"


def test_read_stream_stops_with_partial_result_when_deadline_passes() -> None:
    lines = [event(content="a"), event(content="b"), event(content="c"), "data: [DONE]"]
    readings = iter([1.0, 2.0, 99.0, 100.0, 101.0])

    with pytest.raises(api.StreamInterrupted, match="deadline") as raised:
        api.read_stream(lines, readings.__next__, started=0.0, deadline_s=50.0)

    assert raised.value.partial.text == "ab"
