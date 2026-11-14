"""Builders and validators for the functional checks (text, forced tool call, vision)."""

import base64
import json
import re
from typing import Any

TEXT_PROMPT = "Write a Python function that deduplicates a list in order."
TOOL_PROMPT = "Use get_temperature for Belgrade, then report its returned temperature."
TOOL_NAME = "get_temperature"
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
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
TOOL_CHOICE = {"type": "function", "function": {"name": TOOL_NAME}}
TEMPERATURE_C = 17


def check_tool_call(calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Require exactly the requested call; model-supplied code is never executed.

    Raises:
        ValueError: the call is missing, repeated, or has the wrong name or arguments.
    """
    if len(calls) != 1:
        raise ValueError(f"Expected one tool call, got {len(calls)}")
    call = calls[0]
    function = call.get("function", {})
    if function.get("name") != TOOL_NAME:
        raise ValueError(f"Expected {TOOL_NAME}: {call}")
    try:
        arguments = json.loads(function.get("arguments", ""))
    except json.JSONDecodeError as error:
        raise ValueError(f"Tool call arguments are not JSON: {call}") from error
    if arguments != {"city": "Belgrade"}:
        raise ValueError(f"Expected {TOOL_NAME} for Belgrade: {call}")
    if not call.get("id"):
        raise ValueError("Tool call has no ID")
    return call


def tool_followup(prompt: str, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Messages that answer the model's tool call with a fixed result."""
    call = check_tool_call(calls)
    result = {"city": "Belgrade", "temperature_c": TEMPERATURE_C}
    return [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": None, "tool_calls": calls},
        {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)},
    ]


def reports_temperature(answer: str) -> bool:
    return re.search(rf"(?<!\d){TEMPERATURE_C}(?!\d)", answer) is not None


def image_content(prompt: str, raw: bytes) -> list[dict[str, Any]]:
    """A user message body with the prompt and the image inline.

    Raises:
        ValueError: the image is neither PNG nor JPEG.
    """
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif raw.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    else:
        raise ValueError("Use a PNG or JPEG image")
    uri = f"data:{mime};base64," + base64.b64encode(raw).decode()
    return [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": uri}}]
