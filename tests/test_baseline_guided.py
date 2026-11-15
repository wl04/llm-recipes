"""The guided desktop interview: scripted answers and a fake model list."""

import pytest
from baseline import guided


class ScriptedAsk:
    """Answers prompts in order and records what was asked."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.questions: list[str] = []

    def __call__(self, question: str, default: str | None) -> str:
        self.questions.append(question)
        return self.answers.pop(0)


def run_guide(
    ask: ScriptedAsk,
    *,
    served: list[str] | None = None,
    pids: list[int] | None = None,
    **given: object,
) -> guided.GuidedSetup:
    return guided.guide(
        lambda base: served if served is not None else ["only-model"],
        lambda: pids or [],
        ask,
        lambda message: None,
        **given,  # type: ignore[arg-type]
    )


def test_guide_returns_confirmed_answers_with_defaults_applied() -> None:
    ask = ScriptedAsk("", "", "2048", "", "")

    setup = run_guide(ask)

    assert setup == guided.GuidedSetup(
        base_url="http://127.0.0.1:1234", model="only-model", context=2048, pid=None
    )
    assert len(ask.questions) == 5


def test_guide_echoes_given_values_and_still_confirms_the_summary() -> None:
    ask = ScriptedAsk("")

    setup = run_guide(
        ask, base_url="http://127.0.0.1:9999/v1", model="only-model", context=1024, pid=7
    )

    assert setup == guided.GuidedSetup(
        base_url="http://127.0.0.1:9999", model="only-model", context=1024, pid=7
    )
    assert ask.questions == ["Start this baseline run?"]


def test_guide_yes_uses_detected_defaults_without_asking() -> None:
    def forbidden_ask(question: str, default: str | None) -> str:
        raise AssertionError(f"--yes asked {question!r}")

    setup = guided.guide(
        lambda base: ["only-model"],
        lambda: [4242],
        forbidden_ask,
        lambda message: None,
        yes=True,
    )

    assert setup == guided.GuidedSetup(
        base_url="http://127.0.0.1:1234",
        model="only-model",
        context=guided.DEFAULT_CONTEXT,
        pid=4242,
    )


@pytest.mark.parametrize(
    ("served", "expected"),
    [
        ([], "no models"),
        (["first", "second"], "pass --model"),
    ],
)
def test_guide_yes_stops_when_an_answer_is_not_determinable(
    served: list[str], expected: str
) -> None:
    with pytest.raises(guided.GuidedAborted, match=expected):
        run_guide(ScriptedAsk(), served=served, yes=True)


def test_guide_stops_when_the_model_list_cannot_be_read() -> None:
    def unreachable(base: str) -> list[str]:
        raise OSError("connection refused")

    with pytest.raises(guided.GuidedAborted, match="cannot read the model list"):
        guided.guide(unreachable, list, ScriptedAsk(""), lambda message: None)


def test_guide_rejects_unlisted_model_then_accepts_the_correction() -> None:
    ask = ScriptedAsk("", "nope", "second", "2048", "", "")

    setup = run_guide(ask, served=["first", "second"])

    assert setup.model == "second"


def test_guide_rejects_given_model_not_served() -> None:
    with pytest.raises(guided.GuidedAborted, match="not served"):
        run_guide(
            ScriptedAsk(),
            served=["first"],
            model="x",
            base_url="http://127.0.0.1:1234",
            context=2048,
        )


def test_guide_rejects_non_positive_context_then_accepts_a_valid_number() -> None:
    ask = ScriptedAsk("", "", "0", "abc", "1024", "", "")

    setup = run_guide(ask)

    assert setup.context == 1024


def test_guide_cancel_before_start() -> None:
    ask = ScriptedAsk("", "", "2048", "", "n")

    with pytest.raises(guided.GuidedAborted, match="cancel"):
        run_guide(ask)


def test_find_app_pids_finds_the_app_and_skips_other_processes(tmp_path: object) -> None:
    from pathlib import Path

    proc = Path(str(tmp_path))
    for pid, command in {
        "100": b"LM\x00Studio\x00--flag",
        "200": b"python3\x00run.py",
        "300": b"/usr/bin/lm-studio-helper\x00",
    }.items():
        directory = proc / pid
        directory.mkdir()
        (directory / "cmdline").write_bytes(command)
    (proc / "not-a-pid").mkdir()

    assert guided.find_app_pids(proc) == [100, 300]
