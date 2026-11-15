"""Pure validators and builders for the functional checks."""

import json
from typing import Any

import pytest
from baseline import functional


def call(name: str = "get_temperature", arguments: str = '{"city": "Belgrade"}') -> dict[str, Any]:
    return {"id": "call_1", "type": "function", "function": {"name": name, "arguments": arguments}}


def test_check_tool_call_accepts_the_requested_call() -> None:
    assert functional.check_tool_call([call()])["id"] == "call_1"


@pytest.mark.parametrize(
    ("calls", "message"),
    [
        ([], "one tool call"),
        ([call(), call()], "one tool call"),
        ([call(arguments='{"city": "Paris"}')], "Belgrade"),
        ([call(name="other")], "get_temperature"),
        ([call(arguments="not json")], "arguments"),
        ([{**call(), "id": ""}], "ID"),
    ],
)
def test_check_tool_call_rejects_wrong_calls(calls: list[dict[str, Any]], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        functional.check_tool_call(calls)


def test_tool_followup_messages_return_the_supplied_temperature_for_the_call() -> None:
    messages = functional.tool_followup(functional.TOOL_PROMPT, [call()])

    assert messages[1]["tool_calls"] == [call()]
    assert messages[2]["tool_call_id"] == "call_1"
    assert json.loads(messages[2]["content"]) == {"city": "Belgrade", "temperature_c": 17}


@pytest.mark.parametrize(
    ("raw", "mime"),
    [(b"\x89PNG\r\n\x1a\nrest", "image/png"), (b"\xff\xd8\xffrest", "image/jpeg")],
)
def test_image_content_embeds_the_image_as_a_data_uri(raw: bytes, mime: str) -> None:
    content = functional.image_content("Read it.", raw)

    assert content[0] == {"type": "text", "text": "Read it."}
    assert content[1]["image_url"]["url"].startswith(f"data:{mime};base64,")


def test_image_content_rejects_unsupported_format() -> None:
    with pytest.raises(ValueError, match="PNG or JPEG"):
        functional.image_content("x", b"GIF89a")


def test_answer_mentions_temperature_only_when_it_reports_it() -> None:
    assert functional.reports_temperature("It is 17 degrees in Belgrade.")
    assert not functional.reports_temperature("It is sunny.")


def test_forced_tool_choice_returns_string_required_for_lmstudio_only() -> None:
    assert functional.forced_tool_choice("lmstudio") == "required"
    assert functional.forced_tool_choice("strata") == functional.TOOL_CHOICE
    assert functional.forced_tool_choice("tabbyapi") == functional.TOOL_CHOICE
