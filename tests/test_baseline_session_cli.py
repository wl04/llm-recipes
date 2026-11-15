"""End-to-end tests for the ``session`` command over instance log directories."""

import json
from pathlib import Path
from typing import Any

import generate_configurations as gen
import pytest
import test_baseline_import as runfixtures
import yaml
from baseline import cli, importer, report, schema

TABBY_LOG = (
    "\n".join(
        (
            "2026-11-15 09:00:01.000 | INFO     | Sampler overrides (inline): temperature 1.0, "
            "top_k 20, top_p 0.95, min_p 0, repetition_penalty 1, presence_penalty 0",
            "2026-11-15 09:00:02.000 | INFO     | #1 chat/completions (stream): "
            "1,200 prompt tokens",
            "2026-11-15 09:00:12.500 | INFO     | #1 chat/completions (stream): 512 tokens "
            "generated at 64.0 T/s · prompt 1,200 tokens, 60% cached, 480 new in 0.50 s (960 T/s) "
            "· first "
            "token 0.50 s, total 8.5 s · draft 300/400 accepted (75%)",
            "2026-11-15 09:20:00.000 | INFO     | #2 chat/completions (stream): "
            "60,000 prompt tokens",
            "2026-11-15 09:21:00.000 | INFO     | #2 chat/completions (stream): 1,024 tokens "
            "generated at 32.0 T/s · prompt 60,000 tokens, none cached, 60,000 new in 60.0 s "
            "(1,000 T/s) · first token 60.0 s, total 92.0 s",
            "2026-11-15 09:40:00.000 | INFO     | #3 chat/completions (stream): 900 prompt tokens",
            "2026-11-15 09:40:05.000 | WARNING  | #3 chat/completions: client disconnected, "
            "generation cancelled",
            "2026-11-15 09:50:00.000 | INFO     | #4 chat/completions (stream): 900 prompt tokens",
        )
    )
    + "\n"
)

STRATA_ENGINE_LOG = (
    "\n".join(
        (
            "strata serve: prompt 1000 tokens = 400 reused + 600 read in 500 ms (1200.0 tok/s), "
            "100 generated in 1000 ms (100.0 tok/s), drafts accepted 40 of 80",
            "strata serve: prompt 2000 tokens = 0 reused + 2000 read in 2000 ms (1000.0 tok/s), "
            "200 generated in 4000 ms (50.0 tok/s)",
        )
    )
    + "\n"
)
STRATA_SERVER_LOG = (
    "\n".join(
        (
            "[strata] sampling defaults from the config: temperature=1.0, top_k=20, top_p=0.95, "
            "min_p=0.0, repetition_penalty=1.0, presence_penalty=0.0",
            "[strata] done: 100 tokens in 1 s (100.0 tok/s) (stop, cancel=False), "
            "expert cache 54% hit",
            "[strata] done: 3 tokens in 1 s (3.0 tok/s) (user_cancel, cancel=True), "
            "expert cache 60%",
        )
    )
    + "\n"
)


def _facts(**overrides: Any) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "started_at": "2026-11-15T08:00:00+00:00",
        "instance": "coding-session",
        "recipe": runfixtures.RECIPE,
        "runtime": "exllamav3-tabbyapi",
        "adapter": "tabbyapi",
        "engine": "exllamav3",
        "image": {"reference": "llm-recipes/exl3:probe", "image_id": "sha256:abc"},
        "options": {"port": 8080, "context": 65536, "draft": "on", "vision": "off"},
        "mounts": {},
        "config_sha256": {},
        "host": runfixtures.SYSTEM,
    }
    facts.update(overrides)
    return facts


def _log_dir(tmp_path: Path, facts: dict[str, Any] | None, *named: tuple[str, str]) -> Path:
    directory = tmp_path / "logs"
    directory.mkdir()
    for name, text in named:
        (directory / name).write_text(text)
    if facts is not None:
        (directory / "facts.json").write_text(json.dumps(facts))
    return directory


def _experiment(root: Path, name: str = "003-2026-11-15-coding-session") -> Path:
    experiment = root / "recipes" / runfixtures.RECIPE / name
    experiment.mkdir()
    (experiment / "summary.md").write_text("# Experiment\n\nHuman narrative.\n")
    (experiment / "configuration.md").write_text(
        f"# Experiment\n\n{gen.START}\n\nplaceholder\n{gen.END}\n"
    )
    return experiment


def test_session_cli_writes_results_block_and_seeds_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = runfixtures._make_repo(tmp_path)
    monkeypatch.setattr(
        importer, "_repository_url", lambda _root: "https://github.com/wl04/llm-recipes"
    )
    log_dir = _log_dir(tmp_path, _facts(), ("tabbyapi.log", TABBY_LOG))
    experiment = _experiment(root)

    code = cli.main(["session", "--logs", str(log_dir), "--experiment", str(experiment)], root=root)

    assert code == 0
    document = json.loads((experiment / "session-results.json").read_text())
    schema.validate_session(document)
    assert document["engine"] == "tabbyapi"
    totals = document["totals"]
    assert totals["requests"] == 2
    assert totals["cancelled"] == 1
    assert totals["unclosed_requests"] == 1
    assert totals["generated_tokens"] == 1536
    summary = (experiment / "summary.md").read_text()
    assert report.SESSION_START in summary
    assert "Human narrative." in summary
    assert "### Session activity" in summary
    profile = yaml.safe_load((experiment / "profile.yaml").read_text())
    assert profile["id"] == "Qwen3.8-27B / EXL3 / RX 9070 XT / 16 GB VRAM"
    assert profile["settings"]["sampling"]["top_p"] == 0.95
    assert profile["settings"]["serving"]["context_length_tokens"] == 65536
    assert profile["software"]["python"] == "3.12.3"
    out = capsys.readouterr().out
    assert "coding-session" in out and "completions" in out


def test_session_cli_keeps_existing_profile_and_replaces_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = runfixtures._make_repo(tmp_path)
    monkeypatch.setattr(importer, "_repository_url", lambda _root: None)
    log_dir = _log_dir(tmp_path, _facts(), ("tabbyapi.log", TABBY_LOG))
    experiment = _experiment(root)
    (experiment / "profile.yaml").write_text("id: keep me\n")

    code = cli.main(["session", "--logs", str(log_dir), "--experiment", str(experiment)], root=root)

    assert code == 0
    assert (experiment / "profile.yaml").read_text() == "id: keep me\n"
    assert (experiment / "summary.md").read_text().count(report.SESSION_START) == 1


def test_session_cli_prints_document_without_experiment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log_dir = _log_dir(tmp_path, _facts(), ("tabbyapi.log", TABBY_LOG))

    code = cli.main(["session", "--logs", str(log_dir)], root=tmp_path)

    assert code == 0
    document = json.loads(capsys.readouterr().out)
    schema.validate_session(document)
    assert document["totals"]["requests"] == 2


def test_session_cli_detects_strata_by_instance_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    log_dir = _log_dir(
        tmp_path, None, ("engine.log", STRATA_ENGINE_LOG), ("server.log", STRATA_SERVER_LOG)
    )
    (tmp_path / "state" / "llm-recipes").mkdir(parents=True)
    log_dir.rename(tmp_path / "state" / "llm-recipes" / "coding-x")

    code = cli.main(["session", "coding-x"], root=tmp_path)

    assert code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["engine"] == "strata"
    assert document["totals"]["requests"] == 2
    assert document["totals"]["cancelled"] == 1
    assert document["totals"]["unclosed_requests"] is None
    assert document["availability"]["timestamps"] is False


def test_session_cli_rejects_window_without_timestamps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log_dir = _log_dir(tmp_path, {"adapter": "strata"}, ("engine.log", STRATA_ENGINE_LOG))

    code = cli.main(
        ["session", "--logs", str(log_dir), "--since", "2026-11-15T09:00"], root=tmp_path
    )

    assert code != 0
    assert "no timestamps" in capsys.readouterr().err


def test_session_cli_requires_instance_or_logs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["session"], root=tmp_path)

    assert code != 0
    assert "instance name or --logs" in capsys.readouterr().err
