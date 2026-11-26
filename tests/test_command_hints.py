import io
import shlex

import pytest
from command_hints import command_hint


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_hint_preserves_shell_arguments_and_separates_commands() -> None:
    command = ["cd", "/path with spaces/it's $here"]
    commands = command_hint("Next steps", command, ["pwd"], stream=io.StringIO()).splitlines()
    assert commands[:3] == ["", "Next steps", ""]
    assert [shlex.split(line) for line in commands[3:]] == [command, ["pwd"]]


def test_only_interactive_commands_get_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert command_hint("Next", ["pwd"], stream=Terminal()) == "\nNext\n\n\033[1;36mpwd\033[0m"
    plain = "\nNext\n\npwd"
    assert command_hint("Next", ["pwd"]) == plain
    monkeypatch.setenv("TERM", "dumb")
    assert command_hint("Next", ["pwd"], stream=Terminal()) == plain
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setenv("NO_COLOR", "1")
    assert command_hint("Next", ["pwd"], stream=Terminal()) == plain
