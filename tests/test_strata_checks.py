"""Generation-check validation without a model server."""

import json
from pathlib import Path

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


def test_long_progress_keeps_stdout_available_for_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def request(base: str, route: str, payload: object = None) -> dict[str, object]:
        if route.endswith("count_tokens"):
            return {"input_tokens": 1}
        return {"content": [{"text": "answer"}]}

    monkeypatch.setattr(checks, "request", request)

    checks.check_long("http://localhost", 32, "test-model")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Sending 1 input tokens" in captured.err


@pytest.mark.parametrize("custom", [False, True], ids=["baseline", "custom-image"])
def test_vision_uses_baseline_or_override_outside_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, custom: bool
) -> None:
    import base64
    import sys
    from typing import Any

    folder = tmp_path
    baseline = RUNTIME.parents[1] / "assets/checks/amdgpu-top.png"
    selected = baseline
    argv = ["check_generation.py", "vision", "--model", "test-model"]
    if custom:
        selected = folder / "custom.png"
        selected.write_bytes(b"\x89PNG\r\n\x1a\ncustom")
        argv += ["--image", str(selected)]
    payloads: list[dict[str, Any]] = []

    def request(base: str, route: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if route == "/v1/models":
            return {"data": [{"id": "test-model"}]}
        assert payload is not None
        payloads.append(payload)
        return {"choices": [{"message": {"content": "description"}}]}

    monkeypatch.chdir(folder)
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(checks, "request", request)

    checks.main()

    image_url = payloads[0]["messages"][0]["content"][1]["image_url"]["url"]
    assert base64.b64decode(image_url.split(",", 1)[1]) == selected.read_bytes()
