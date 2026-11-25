"""OpenAI-compatible request and stream handling shared by all server adapters.

Timings are seconds from the start of the request on the supplied monotonic clock. They are
client-side observations, not engine measurements.
"""

import json
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

Opener = Callable[..., Any]
Clock = Callable[[], float]


class ApiError(ValueError):
    """A request failed, or a server response was an error or malformed."""


@dataclass(frozen=True)
class Usage:
    """Token counts reported by the server; ``None`` means the server did not report it."""

    prompt_tokens: int | None
    completion_tokens: int | None
    cached_tokens: int | None


@dataclass(frozen=True)
class StreamResult:
    """Everything observed on one streamed completion."""

    text: str = ""
    reasoning: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    usage: Usage | None = None
    first_output_s: float | None = None
    last_output_s: float | None = None
    first_content_s: float | None = None


class StreamInterrupted(ApiError):
    """The stream ended or broke before ``[DONE]``; ``partial`` keeps what was received."""

    def __init__(self, message: str, partial: StreamResult) -> None:
        super().__init__(message)
        self.partial = partial


def _count(value: object, name: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ApiError(f"Usage field {name} must be a non-negative integer")
    return value


def parse_usage(usage: object) -> Usage | None:
    """Read OpenAI-style usage, or ``None`` when the server reported none.

    Raises:
        ApiError: a reported count is not a non-negative integer.
    """
    if usage is None:
        return None
    if not isinstance(usage, dict):
        raise ApiError("Usage must be an object")
    details = usage.get("prompt_tokens_details")
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    return Usage(
        prompt_tokens=_count(usage.get("prompt_tokens"), "prompt_tokens"),
        completion_tokens=_count(usage.get("completion_tokens"), "completion_tokens"),
        cached_tokens=_count(cached, "cached_tokens"),
    )


def _merge_tool_calls(calls: dict[int, dict[str, Any]], fragments: list[dict[str, Any]]) -> None:
    for fragment in fragments:
        call = calls.setdefault(
            fragment.get("index", 0),
            {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
        )
        call["id"] = fragment.get("id") or call["id"]
        function = fragment.get("function") or {}
        call["function"]["name"] += function.get("name") or ""
        call["function"]["arguments"] += function.get("arguments") or ""


def read_stream(
    lines: Iterable[str], clock: Clock, started: float, deadline_s: float | None = None
) -> StreamResult:
    """Collect an OpenAI server-sent-event completion with client-side output timings.

    ``clock`` is read once per event that carries output (content, reasoning, or a tool call);
    with a ``deadline_s`` it is read for every received line, including keep-alives and ``[DONE]``.

    Raises:
        ApiError: an error event or a malformed event.
        StreamInterrupted: the stream ended or broke before ``[DONE]``.
    """
    text = reasoning = ""
    calls: dict[int, dict[str, Any]] = {}
    finish_reason: str | None = None
    usage: Usage | None = None
    first = last = first_content = None

    def snapshot() -> StreamResult:
        return StreamResult(
            text,
            reasoning,
            [calls[key] for key in sorted(calls)],
            finish_reason,
            usage,
            first,
            last,
            first_content,
        )

    try:
        for line in lines:
            now = clock() if deadline_s is not None else None
            if now is not None and deadline_s is not None and now - started > deadline_s:
                raise StreamInterrupted(
                    f"Request deadline of {deadline_s:g} s exceeded", snapshot()
                )
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                return snapshot()
            try:
                item = json.loads(payload)
            except json.JSONDecodeError as error:
                raise ApiError("Received a malformed stream event") from error
            if item.get("error"):
                raise ApiError(f"Streaming error: {item['error']}")
            produced = False
            produced_content = False
            for choice in item.get("choices", []):
                delta = choice.get("delta") or {}
                content = delta.get("content") or ""
                thought = delta.get("reasoning_content") or delta.get("reasoning") or ""
                fragments = delta.get("tool_calls") or []
                text += content
                reasoning += thought
                _merge_tool_calls(calls, fragments)
                produced = produced or bool(content or thought or fragments)
                produced_content = produced_content or bool(content)
                finish_reason = choice.get("finish_reason") or finish_reason
            if produced:
                last = (now if now is not None else clock()) - started
                first = last if first is None else first
                if produced_content and first_content is None:
                    first_content = last
            usage = parse_usage(item.get("usage")) or usage
    except OSError as error:
        raise StreamInterrupted(f"Stream broke: {error}", snapshot()) from error
    raise StreamInterrupted("Stream ended before [DONE]", snapshot())


def _request(base_url: str, route: str, payload: dict[str, Any] | None) -> Request:
    return Request(
        base_url.rstrip("/") + route,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )


def _http_error(error: HTTPError) -> ApiError:
    body = error.read().decode("utf-8", errors="replace")
    return ApiError(f"HTTP {error.code}: {body}")


def post_json(
    base_url: str,
    route: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float,
    opener: Opener = urlopen,
) -> dict[str, Any]:
    """Call a JSON route and return the parsed body.

    Raises:
        ApiError: the server is unreachable, returned an HTTP error, or reported an error body.
    """
    try:
        with opener(_request(base_url, route, payload), timeout=timeout) as response:
            result = json.load(response)
    except HTTPError as error:
        raise _http_error(error) from error
    except (URLError, OSError) as error:
        raise ApiError(f"Cannot reach {base_url}: {error}") from error
    except json.JSONDecodeError as error:
        raise ApiError("Received a malformed response body") from error
    if not isinstance(result, dict):
        raise ApiError("Response body must be an object")
    if result.get("error"):
        raise ApiError(f"API error: {result['error']}")
    return result


def stream_chat(
    base_url: str,
    route: str,
    payload: dict[str, Any],
    *,
    timeout: float,
    clock: Clock = time.monotonic,
    opener: Opener = urlopen,
    deadline_s: float | None = None,
) -> StreamResult:
    """Run one streamed completion; the request clock starts before the connection opens.

    Raises:
        ApiError: see ``read_stream`` and ``post_json``.
    """
    started = clock()
    try:
        with opener(_request(base_url, route, payload), timeout=timeout) as response:
            return read_stream(
                (line.decode("utf-8") for line in response), clock, started, deadline_s
            )
    except HTTPError as error:
        raise _http_error(error) from error
    except URLError as error:
        raise ApiError(f"Cannot reach {base_url}: {error}") from error


def require_model(loaded: list[str], expected: str) -> None:
    """Fail when the server's loaded models do not include the expected identity."""
    if expected not in loaded:
        raise ApiError(f"Expected model {expected}; the server reports: {', '.join(loaded)}")
