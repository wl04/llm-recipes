"""Run explicit text, tool, image, or long-context checks against local Strata."""

import argparse
import base64
import json
import time
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def read_stream(lines: Iterable[str]) -> dict[str, Any]:
    """Collect OpenAI SSE text and usage, rejecting error or interrupted streams."""
    text = ""
    usage = None
    for line in lines:
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            if not text.strip():
                raise ValueError("Stream returned no answer text")
            return {"text": text, "usage": usage}
        event = json.loads(data)
        if event.get("error"):
            raise ValueError(f"Streaming error: {event['error']}")
        for choice in event.get("choices", []):
            text += choice.get("delta", {}).get("content") or ""
        usage = event.get("usage") or usage
    raise ValueError("Stream ended before [DONE]")


def request(base: str, route: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call the API, including its response body when an HTTP error occurs."""
    req = Request(
        base + route,
        data=json.dumps(payload).encode() if payload else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=3600) as response:
            if payload and payload.get("stream"):
                return read_stream(line.decode("utf-8") for line in response)
            result: dict[str, Any] = json.load(response)
            if result.get("error"):
                raise ValueError(f"API error: {result['error']}")
            return result
    except HTTPError as error:
        raise ValueError(
            f"HTTP {error.code}: {error.read().decode('utf-8', errors='replace')}"
        ) from error


def validate_call(message: dict[str, Any]) -> dict[str, Any]:
    """Require the requested tool name and arguments; execute no model-supplied code."""
    calls = message.get("tool_calls") or []
    if len(calls) != 1:
        raise ValueError(f"Expected one tool call: {message}")
    call = calls[0]
    function = call["function"]
    if function["name"] != "get_temperature" or json.loads(function["arguments"]) != {
        "city": "Belgrade"
    }:
        raise ValueError(f"Expected get_temperature for Belgrade: {call}")
    if not call.get("id"):
        raise ValueError("Tool call has no ID")
    return call


def answer(result: dict[str, Any]) -> dict[str, Any]:
    choices = result.get("choices") or []
    if not choices or not choices[0].get("message", {}).get("content"):
        raise ValueError(f"Empty answer: {result}")
    return result


def chat_payload(content: Any, model: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "max_completion_tokens": 256,
        "reasoning_effort": "none",
    }


def check_tools(base: str, model: str) -> dict[str, Any]:
    payload = chat_payload(
        "Use get_temperature for Belgrade, then report its returned temperature.", model
    )
    payload["tools"] = [
        {
            "type": "function",
            "function": {
                "name": "get_temperature",
                "description": "Read a city's temperature.",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                    "additionalProperties": False,
                },
            },
        }
    ]
    payload["tool_choice"] = {"type": "function", "function": {"name": "get_temperature"}}
    first = request(base, "/v1/chat/completions", payload)
    message = first["choices"][0]["message"]
    call = validate_call(message)
    payload["messages"] += [
        message,
        {
            "role": "tool",
            "tool_call_id": call["id"],
            "content": '{"city":"Belgrade","temperature_c":17}',
        },
    ]
    payload["tool_choice"] = "none"
    second = answer(request(base, "/v1/chat/completions", payload))
    if "17" not in second["choices"][0]["message"]["content"]:
        raise ValueError(f"Answer did not report the supplied temperature: {second}")
    return {"tool_request": first, "tool_result_response": second}


def check_long(base: str, target: int, model: str) -> dict[str, Any]:
    """Count and generate through the same Anthropic endpoint family."""
    nonce = uuid.uuid4().hex

    def payload(rows: int) -> dict[str, Any]:
        records = "\n".join(
            f"service_{i % 97}: request={i}, duration_ms={i % 211}" for i in range(rows)
        )
        return {
            "model": model,
            "max_tokens": 128,
            "temperature": 0,
            "thinking": {"type": "disabled"},
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Run {nonce}\n{records}\n"
                        "Write a Python function counting records by service."
                    ),
                }
            ],
        }

    low, high = 0, target
    selected = payload(0)
    count = request(base, "/v1/messages/count_tokens", selected)["input_tokens"]
    if count > target:
        raise ValueError("Target is smaller than the base prompt")
    while low <= high:
        middle = (low + high) // 2
        candidate = payload(middle)
        tokens = request(base, "/v1/messages/count_tokens", candidate)["input_tokens"]
        if tokens <= target:
            selected, count, low = candidate, tokens, middle + 1
        else:
            high = middle - 1
    print(f"Sending {count:,} input tokens; up to 128 output tokens.", flush=True)
    started = time.monotonic()
    result = request(base, "/v1/messages", selected)
    if not any(part.get("text") for part in result.get("content", [])):
        raise ValueError(f"Empty long-context answer: {result}")
    return {
        "tokenizer_prompt_tokens": count,
        "generation_request_seconds": time.monotonic() - started,
        "response": result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("text", "tools", "vision", "long"))
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:8080", help="Server URL without /v1"
    )
    parser.add_argument("--model", required=True, help="Expected server model ID")
    parser.add_argument("--image", type=Path, help="PNG or JPEG for the vision check")
    parser.add_argument("--input-tokens", type=int, default=120000)
    options = parser.parse_args()
    if options.mode == "vision" and not options.image:
        parser.error("vision requires --image")
    if options.input_tokens < 1024:
        parser.error("--input-tokens must be at least 1024")
    base = options.base_url.rstrip("/")
    try:
        models = request(base, "/v1/models").get("data", [])
        if not any(model.get("id") == options.model for model in models):
            raise ValueError(f"Expected loaded model {options.model}: {models}")
        started = time.monotonic()
        if options.mode == "tools":
            result = check_tools(base, options.model)
        elif options.mode == "long":
            result = check_long(base, options.input_tokens, options.model)
        elif options.mode == "vision":
            raw = options.image.read_bytes()
            if raw.startswith(b"\x89PNG\r\n\x1a\n"):
                mime = "image/png"
            elif raw.startswith(b"\xff\xd8\xff"):
                mime = "image/jpeg"
            else:
                raise ValueError("Use a PNG or JPEG image")
            content = [
                {"type": "text", "text": "Describe the image and read its visible text."},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64," + base64.b64encode(raw).decode()},
                },
            ]
            result = answer(
                request(base, "/v1/chat/completions", chat_payload(content, options.model))
            )
        else:
            payload = chat_payload(
                "Write a Python function that deduplicates a list in order.", options.model
            )
            payload.update(stream=True, stream_options={"include_usage": True})
            result = request(base, "/v1/chat/completions", payload)
        print(
            json.dumps(
                {
                    "check": options.mode,
                    "request_seconds": time.monotonic() - started,
                    "result": result,
                },
                indent=2,
            )
        )
    except (OSError, URLError, ValueError, KeyError, IndexError) as error:
        parser.exit(1, f"Check failed: {error}\n")


if __name__ == "__main__":
    main()
