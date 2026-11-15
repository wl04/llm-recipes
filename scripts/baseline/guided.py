"""Prompt-driven setup for desktop recipes: one interview, fully injectable.

Every external contact is injected — answers through ``ask``, the served model list
through ``list_models``, process detection through ``find_pids`` — so tests drive the
whole interview with scripted answers and a fake server instead of a real app.
"""

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from baseline import api

DEFAULT_BASE_URL = "http://127.0.0.1:1234"
DEFAULT_CONTEXT = 4096
ANSWER_LIMIT = 3


class GuidedAborted(Exception):
    """The interview cannot continue: unreachable server, ambiguity, or a cancel."""


@dataclass(frozen=True)
class GuidedSetup:
    """The confirmed answers a desktop run needs."""

    base_url: str
    model: str
    context: int
    pid: int | None


def find_app_pids(proc_root: Path = Path("/proc")) -> list[int]:
    """Process ids whose command line mentions LM Studio; empty when the app is absent."""
    pids = []
    entries = proc_root.iterdir() if proc_root.is_dir() else []
    for entry in entries:
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            command_line = entry.joinpath("cmdline").read_bytes().replace(b"\0", b" ")
        except OSError:
            continue
        text = command_line.decode(errors="replace").lower()
        if "lm studio" in text or "lmstudio" in text or "lm-studio" in text:
            pids.append(int(entry.name))
    return sorted(pids)


def _normalize(url: str) -> str:
    return url.rstrip("/").removesuffix("/v1").rstrip("/")


class _Interview:
    """One question style: given value, then --yes default, then ask, with validation."""

    def __init__(
        self, ask: Callable[[str, str | None], str], log: Callable[[str], None], yes: bool
    ) -> None:
        self._ask = ask
        self._log = log
        self._yes = yes

    def text(self, question: str, default: str | None, given: str | None = None) -> str:
        if given is not None:
            self._log(f"{question}: {given} (given)")
            return given
        if self._yes:
            if default is None:
                raise GuidedAborted(
                    f"{question}: --yes cannot guess this; pass the matching option"
                )
            self._log(f"{question}: {default} (--yes)")
            return default
        answer = self._ask(question, default)
        return answer or (default or "")

    def model(self, served: Sequence[str], given: str | None) -> str:
        if given is not None:
            if given not in served:
                raise GuidedAborted(
                    f"model {given!r} is not served; the server lists: {', '.join(served)}"
                )
            self._log(f"Served model loaded in the app: {given} (given)")
            return given
        if len(served) == 1:
            default: str | None = served[0]
        elif self._yes:
            raise GuidedAborted(
                f"{len(served)} models are listed ({', '.join(served)}); pass --model to choose"
            )
        else:
            default = None
        for _ in range(ANSWER_LIMIT):
            value = self.text("Served model loaded in the app", default)
            if value in served:
                return value
            self._log(f"not one of the listed models: {', '.join(served)} (got {value!r})")
        raise GuidedAborted("no valid model id given")

    def context(self, given: int | None) -> int:
        if given is not None:
            if given <= 0:
                raise GuidedAborted("--context must be positive")
            self._log(f"Context length configured in the app: {given} (given)")
            return given
        for _ in range(ANSWER_LIMIT):
            value = self.text("Context length configured in the app (tokens)", str(DEFAULT_CONTEXT))
            if value.isdigit() and int(value) > 0:
                return int(value)
            self._log("enter a positive whole number of tokens")
        raise GuidedAborted("no valid context length given")

    def pid(self, detected: Sequence[int], given: int | None) -> int | None:
        if given is not None:
            if given <= 0:
                raise GuidedAborted("--pid must be positive")
            self._log(f"Process id of the app: {given} (given)")
            return given
        default = str(detected[0]) if detected else None
        if default is None and self._yes:
            self._log("Process id of the app: none detected (--yes)")
            return None
        for _ in range(ANSWER_LIMIT):
            value = self.text("Process id of the app (for CPU, RAM, and process VRAM)", default)
            if value == "":
                return None
            if value.isdigit() and int(value) > 0:
                return int(value)
            self._log("enter a positive process id, or press Enter to measure the whole system")
        raise GuidedAborted("no valid process id given")


def guide(
    list_models: Callable[[str], list[str]],
    find_pids: Callable[[], list[int]],
    ask: Callable[[str, str | None], str],
    log: Callable[[str], None],
    *,
    yes: bool = False,
    base_url: str | None = None,
    model: str | None = None,
    context: int | None = None,
    pid: int | None = None,
) -> GuidedSetup:
    """Walk the prompt-driven phases and return the confirmed setup.

    Phases: server URL, served-model confirmation, context confirmation, app scope
    detection, then a summary the operator approves. Values already given as options
    are echoed instead of asked; ``yes`` accepts every available default.

    Raises:
        GuidedAborted: the server cannot be read, an answer cannot be determined or
            validated, or the operator declined the summary.
    """
    interview = _Interview(ask, log, yes)
    base = _normalize(interview.text("Server URL of the running app", DEFAULT_BASE_URL, base_url))
    try:
        served = list_models(base)
    except (api.ApiError, OSError, ValueError) as error:
        raise GuidedAborted(f"cannot read the model list from {base}: {error}") from error
    if not served:
        raise GuidedAborted("the server lists no models; load one in the app first")
    chosen = interview.model(served, model)
    context_tokens = interview.context(context)
    detected = find_pids()
    if detected:
        log(f"found app processes: {', '.join(str(p) for p in detected)}")
    app_pid = interview.pid(detected, pid)
    scope = f"pid {app_pid}" if app_pid is not None else "system telemetry only"
    log(f"run: {base} | model {chosen} | context {context_tokens} | scope {scope}")
    if interview.text("Start this baseline run?", "y").lower() not in ("", "y", "yes"):
        raise GuidedAborted("cancelled by the operator")
    return GuidedSetup(base_url=base, model=chosen, context=context_tokens, pid=app_pid)
