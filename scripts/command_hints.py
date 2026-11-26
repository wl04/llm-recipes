"""Render copyable next steps for people running the CLI."""

import os
import shlex
from collections.abc import Sequence
from typing import TextIO


def command_hint(label: str, *commands: Sequence[str], stream: TextIO | None = None) -> str:
    """Keep persisted messages plain and highlight commands on interactive terminals."""
    lines = [shlex.join(command) for command in commands]
    if (
        stream is not None
        and stream.isatty()
        and "NO_COLOR" not in os.environ
        and os.environ.get("TERM") != "dumb"
    ):
        lines = [f"\033[1;36m{line}\033[0m" for line in lines]
    return "\n" + label + "\n\n" + "\n".join(lines)
