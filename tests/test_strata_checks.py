"""Generation-check validation without a model server."""

import json

import pytest
from test_strata import RUNTIME, load_module

checks = load_module("strata_checks", RUNTIME / "scripts/check_generation.py")


def test_read_stream_combines_text_and_requires_done() -> None:
    event = {"choices": [{"delta": {"content": "hello"}}]}
    lines = ["data: " + json.dumps(event), "", "data: [DONE]"]

    result = checks.read_stream(lines)

    assert result["text"] == "hello"


def test_read_stream_rejects_interrupted_response() -> None:
    with pytest.raises(ValueError, match="DONE"):
        checks.read_stream(['data: {"choices": []}'])


def test_validate_call_rejects_wrong_arguments() -> None:
    message = {
        "tool_calls": [
            {"id": "1", "function": {"name": "get_temperature", "arguments": '{"city":"Paris"}'}}
        ]
    }

    with pytest.raises(ValueError, match="Belgrade"):
        checks.validate_call(message)


def test_chat_payload_targets_explicit_model() -> None:
    payload = checks.chat_payload("Hello", "qwen3.8-flash-next-ud-iq3_xxs")
    assert payload["model"] == "qwen3.8-flash-next-ud-iq3_xxs"
    assert checks.chat_payload("Hello", "another-model")["model"] == "another-model"
