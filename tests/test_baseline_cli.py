"""The command line: managed and desktop runs, render, argument validation, and output."""

import json
import os
from pathlib import Path
from typing import Any

import generate_configurations as generator
import pytest
from baseline import cli, host, schema
from baseline.schema import ExitCode
from fake_server import FakeServer
from launcher import LaunchOptions, Recipe
from test_baseline_runner import SUITE, FakeControl
from test_baseline_sources import make_cgroup

ROOT = Path(__file__).resolve().parents[1]
RECIPE = "qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram"


class Managed:
    """Replaces the container control with a fake and records how it was built."""

    def __init__(self, tmp_path: Path, server: FakeServer, monkeypatch: pytest.MonkeyPatch) -> None:
        self.control = FakeControl(tmp_path, server)
        self.options: list[LaunchOptions] = []

        def factory(recipe: Recipe, options: LaunchOptions, **kwargs: Any) -> FakeControl:
            self.options.append(options)
            return self.control

        monkeypatch.setattr(cli, "ContainerControl", factory)


def managed_argv(tmp_path: Path, server: FakeServer, *extra: str, name: str = "run") -> list[str]:
    port = server.base_url.rsplit(":", 1)[1]
    return ["run", RECIPE, "--output", str(tmp_path / name), "--port", port, "--no-gpu", *extra]


def run_managed(
    tmp_path: Path, server: FakeServer, monkeypatch: pytest.MonkeyPatch, *extra: str
) -> tuple[int, Managed]:
    managed = Managed(tmp_path, server, monkeypatch)
    return cli.main(managed_argv(tmp_path, server, *extra), suite=SUITE), managed


def test_managed_run_writes_results_summary_and_raw_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with FakeServer() as server:
        code, _ = run_managed(tmp_path, server, monkeypatch)

    output = tmp_path / "run"
    assert code == ExitCode.OK
    for name in ("meta.json", "requests.jsonl", "samples.jsonl", "results.json", "summary.md"):
        assert (output / name).is_file()
    document = json.loads((output / "results.json").read_text())
    schema.validate_results(document)
    assert [p["id"] for p in document["phases"]] == [
        "idle", "load", "settle", "loaded_idle", "unload"
    ]  # fmt: skip
    assert "## Baseline results" in (output / "summary.md").read_text()
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1
    assert str(output) in captured.out
    assert "[baseline]" in captured.err
    assert "[baseline]" not in captured.out


def test_managed_run_passes_recipe_defaults_and_log_location_to_the_launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with FakeServer() as server:
        _, managed = run_managed(tmp_path, server, monkeypatch)

    options = managed.options[0]
    assert (options.name, options.detached) == ("baseline", True)
    assert (options.context, options.draft, options.vision) == (131072, "on", "cpu")
    assert options.logs == (tmp_path / "run").resolve() / "server-logs"
    assert options.models == (Path.home() / "Models/llm-recipes").resolve()


def test_managed_run_applies_explicit_launch_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with FakeServer() as server:
        _, managed = run_managed(
            tmp_path, server, monkeypatch, "--context", "32768", "--draft", "off", "--vision", "off"
        )

    options = managed.options[0]
    assert (options.context, options.draft, options.vision) == (32768, "off", "off")


def test_managed_run_records_launch_settings_and_host_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with FakeServer() as server:
        run_managed(tmp_path, server, monkeypatch)

    meta = json.loads((tmp_path / "run" / "meta.json").read_text())
    assert meta["server"]["kind"] == "strata"
    assert meta["server"]["context_tokens"] == 131072
    assert meta["launch"]["vision"] == "cpu"
    assert meta["container"]["instance"] == "baseline"
    assert "uptime_s" in meta["boot"]["metrics"]
    assert meta["host"]["python"]
    assert meta["workload"]["corpus_sha256"]


def test_managed_run_summary_is_current_for_the_generator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with FakeServer() as server:
        run_managed(tmp_path, server, monkeypatch)

    _, before, after = generator.update_results(tmp_path / "run")

    assert before == after


def test_managed_run_stops_the_server_unless_asked_to_keep_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with FakeServer() as server:
        _, managed = run_managed(tmp_path, server, monkeypatch, "--keep-running")

    assert managed.control.calls == ["preflight", "start"]


def test_managed_run_reports_a_failed_preflight_with_its_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with FakeServer() as server:
        managed = Managed(tmp_path, server, monkeypatch)
        managed.control.preflight_error = "Launcher instance(s) already running: coding"
        code = cli.main(managed_argv(tmp_path, server), suite=SUITE)

    meta = json.loads((tmp_path / "run" / "meta.json").read_text())
    captured = capsys.readouterr()
    assert code == ExitCode.PREFLIGHT_FAILED
    assert "already running" in meta["run"]["error"]
    assert "already running" in captured.err
    assert "Baseline failed" in captured.out
    assert (tmp_path / "run" / "results.json").is_file()


def test_default_output_is_resolved_from_the_models_directory_and_time() -> None:
    from datetime import datetime

    path = cli.default_output(Path("/data/models"), "my-recipe", datetime(2026, 11, 14, 13, 51))

    assert path == Path("/data/models/baselines/my-recipe/2026-11-14-1351")


def test_run_without_output_writes_under_the_home_models_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home" / "Models" / "llm-recipes").mkdir(parents=True)
    monkeypatch.setattr(cli, "DEFAULT_MODELS", tmp_path / "home" / "Models" / "llm-recipes")
    with FakeServer() as server:
        Managed(tmp_path, server, monkeypatch)
        port = server.base_url.rsplit(":", 1)[1]
        code = cli.main(["run", RECIPE, "--port", port, "--no-gpu"], suite=SUITE)

    runs = list((tmp_path / "home/Models/llm-recipes/baselines" / RECIPE).iterdir())
    assert code == ExitCode.OK
    assert len(runs) == 1
    assert (runs[0] / "results.json").is_file()


@pytest.fixture
def desktop_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Resolve any --pid to a fake application scope so tests do not read the real cgroup."""
    cgroup = make_cgroup(tmp_path / "cgroups", name="app-test-1.scope")
    (cgroup / "cgroup.procs").write_text(f"{os.getpid()}\n")
    monkeypatch.setattr(host, "cgroup_path_of", lambda pid: cgroup)
    return cgroup


def test_desktop_recipe_runs_against_a_running_app(tmp_path: Path, desktop_scope: Path) -> None:
    recipes = tmp_path / "recipes"
    (recipes / "desktop-recipe").mkdir(parents=True)
    with FakeServer() as server:
        argv = [
            "run", "desktop-recipe", "--output", str(tmp_path / "run"),
            "--base-url", server.base_url + "/v1", "--model", "test-model", "--context", "2048",
            "--no-gpu", "--pid", str(os.getpid()),
        ]  # fmt: skip
        code = cli.main(argv, suite=SUITE, recipes=recipes)

    meta = json.loads((tmp_path / "run" / "meta.json").read_text())
    document = json.loads((tmp_path / "run" / "results.json").read_text())
    assert code == ExitCode.OK
    assert meta["server"]["kind"] == "lmstudio"
    assert meta["workload"]["image"].endswith("amdgpu-top.png")
    assert [p["id"] for p in document["phases"]] == ["settle", "loaded_idle"]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["run", "no-such-recipe", "--output", "{out}"], "Unknown recipe"),
        (["run", RECIPE, "--output", "{out}", "--pid", "1"], "started by the runner"),
        (["run", RECIPE, "--output", "{out}", "--base-url", "http://x"], "started by the runner"),
        (["run", RECIPE, "--output", "{out}", "--request-extra", "[1]"], "--request-extra"),
        (["run", RECIPE, "--output", "{out}", "--request-extra", "nope"], "--request-extra"),
        (["run", RECIPE, "--output", str(ROOT / "result")], "outside the repository"),
    ],
)
def test_run_rejects_invalid_arguments_with_usage_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str], message: str
) -> None:
    argv = [item.replace("{out}", str(tmp_path / "out")) for item in argv]

    code = cli.main(argv, suite=SUITE)

    assert code == ExitCode.USAGE
    assert message in capsys.readouterr().err


def test_instance_option_no_longer_exists() -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["run", RECIPE, "--instance", "coding"], suite=SUITE)

    assert raised.value.code == 2


def test_run_needs_endpoint_and_context_for_a_desktop_recipe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recipes = tmp_path / "recipes"
    (recipes / "desktop-recipe").mkdir(parents=True)

    code = cli.main(
        ["run", "desktop-recipe", "--output", str(tmp_path / "out")], suite=SUITE, recipes=recipes
    )

    assert code == ExitCode.USAGE
    assert "--base-url and --context" in capsys.readouterr().err


def test_run_refuses_to_reuse_an_output_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "run").mkdir()
    with FakeServer() as server:
        code, managed = run_managed(tmp_path, server, monkeypatch)

    assert code == ExitCode.USAGE
    assert managed.control.calls == []


def test_render_rebuilds_results_and_keeps_authored_summary_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with FakeServer() as server:
        run_managed(tmp_path, server, monkeypatch)
    summary = tmp_path / "run" / "summary.md"
    summary.write_text(summary.read_text().replace("Observations", "My own observations"))
    (tmp_path / "run" / "results.json").unlink()

    code = cli.main(["render", str(tmp_path / "run")])

    assert code == ExitCode.OK
    assert (tmp_path / "run" / "results.json").is_file()
    assert "My own observations" in summary.read_text()


def test_render_rejects_a_directory_that_is_not_a_run(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()

    assert cli.main(["render", str(tmp_path / "empty")]) == ExitCode.USAGE
