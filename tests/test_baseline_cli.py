"""The command line: managed and desktop runs, render, argument validation, and output."""

import json
import os
import shlex
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import generate_configurations as generator
import paths
import pytest
from baseline import cli, guided, host, lifecycle, schema
from baseline.schema import ExitCode
from fake_server import FakeServer
from launcher import LaunchOptions, Recipe
from test_baseline_lifecycle import FakeDocker, done, make_control
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
        monkeypatch.setattr(cli, "refresh_sudo_ticket", lambda: None)


def managed_argv(tmp_path: Path, server: FakeServer, *extra: str, name: str = "run") -> list[str]:
    port = server.base_url.rsplit(":", 1)[1]
    return ["run", RECIPE, "--output", str(tmp_path / name), "--port", port, "--no-gpu", *extra]


def run_managed(
    tmp_path: Path, server: FakeServer, monkeypatch: pytest.MonkeyPatch, *extra: str
) -> tuple[int, Managed]:
    managed = Managed(tmp_path, server, monkeypatch)
    return cli.main(managed_argv(tmp_path, server, *extra), suite=SUITE), managed


def test_run_baseline_refreshes_sudo_ticket_once_before_noninteractive_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []

    with FakeServer() as server:
        control = FakeControl(tmp_path, server)

        def control_factory(recipe: Recipe, options: LaunchOptions, **kwargs: Any) -> FakeControl:
            order.append("control")
            return control

        monkeypatch.setattr(cli, "ContainerControl", control_factory)
        monkeypatch.setattr(cli, "refresh_sudo_ticket", lambda: order.append("refresh"))

        code = cli.main(managed_argv(tmp_path, server), suite=SUITE)

    assert code == ExitCode.OK
    assert order == ["refresh", "control"]


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        ("complete", ExitCode.OK),
        ("interrupted", ExitCode.INTERRUPTED),
        ("revoked", ExitCode.CHECKS_FAILED),
    ],
)
def test_managed_run_renews_cleanup_authorization_during_workloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str, expected: ExitCode
) -> None:
    now = 0.0
    expires_at = 60.0
    attempted = threading.Event()
    workers: set[threading.Thread] = set()

    def renew(command: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal expires_at
        assert command == ["sudo", "-n", "-v"]
        workers.add(threading.current_thread())
        current_time = now
        if current_time == 0:
            return done()
        if outcome != "revoked":
            expires_at = current_time + 60
        attempted.set()
        return done(code=1, error="sudo credentials revoked") if outcome == "revoked" else done()

    class TicketedDocker(FakeDocker):
        def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
            if now >= expires_at:
                return done(code=1, error="sudo credentials expired")
            return super().__call__(command)

    def progress(message: str) -> None:
        nonlocal now
        checkpoint = "Warming up the server" if outcome == "interrupted" else "Stopping the server"
        if message != checkpoint:
            return
        now = 45
        attempted.wait(1)
        now = 90
        if outcome == "interrupted":
            raise KeyboardInterrupt

    make_cgroup(tmp_path / "cg")
    docker = TicketedDocker()
    control = make_control(tmp_path, docker)
    monkeypatch.setattr(cli, "ContainerControl", lambda *args, **kwargs: control)
    monkeypatch.setattr(cli, "refresh_sudo_ticket", lambda: None)
    monkeypatch.setattr(cli, "_progress", progress)
    original_run = host.run_command

    def run(command: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
        if command == ["sudo", "-n", "-v"]:
            return renew(command)
        return original_run(command, timeout)

    monkeypatch.setattr(host, "run_command", run)
    monkeypatch.setattr(lifecycle, "SUDO_TICKET_RENEW_INTERVAL_S", 0.01, raising=False)

    with FakeServer() as server:
        code = cli.main(managed_argv(tmp_path, server), suite=SUITE)

    output = tmp_path / "run"
    meta = json.loads((output / "meta.json").read_text())
    assert attempted.is_set()
    assert all(not worker.is_alive() for worker in workers)
    assert code == expected
    if outcome == "revoked":
        assert "sudo docker stop abc123" in " ".join(meta["problems"])
        assert (output / "requests.jsonl").stat().st_size > 0
    else:
        assert ["sudo", "-n", "docker", "stop", "abc123"] in docker.commands


def test_managed_run_writes_results_summary_and_raw_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "operator's run"
    with FakeServer() as server:
        code, _ = run_managed(tmp_path, server, monkeypatch, "--output", output.name)

    assert code == ExitCode.OK
    for name in ("meta.json", "requests.jsonl", "samples.jsonl", "results.json", "summary.md"):
        assert (output / name).is_file()
    document = json.loads((output / "results.json").read_text())
    schema.validate_results(document)
    assert [p["id"] for p in document["phases"]] == [
        "idle", "load", "settle", "loaded_idle", "unload", "after_unload"
    ]  # fmt: skip
    assert "## Baseline results" in (output / "summary.md").read_text()
    captured = capsys.readouterr()
    assert "Baseline written to" in captured.out
    assert shlex.split(captured.out.splitlines()[-1]) == [
        "python3",
        "scripts/run_baseline.py",
        "import",
        str(output),
    ]
    assert "[baseline]" in captured.err
    assert "[baseline]" not in captured.out


def test_managed_run_passes_recipe_defaults_and_log_location_to_the_launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_home = tmp_path / "data-home"
    monkeypatch.setenv(paths.DATA_HOME_ENV, str(data_home))
    with FakeServer() as server:
        _, managed = run_managed(tmp_path, server, monkeypatch)

    options = managed.options[0]
    assert (options.name, options.detached) == ("baseline", True)
    assert (options.context, options.draft, options.vision) == (131072, "on", "cpu")
    assert options.logs == (tmp_path / "run").resolve() / "server-logs"
    assert options.models == data_home.resolve()


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

    _, before, after = generator.update_results_block(tmp_path / "run")

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
    assert "scripts/run_baseline.py import" not in captured.out
    assert (tmp_path / "run" / "results.json").is_file()


def test_default_output_is_resolved_from_the_models_directory_and_time() -> None:
    from datetime import datetime

    path = cli.default_output(Path("/data/models"), "my-recipe", datetime(2026, 11, 14, 13, 51))

    assert path == Path("/data/models/baselines/my-recipe/2026-11-14-1351")


def test_run_without_output_writes_under_the_data_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_home = tmp_path / "home" / "llm-recipes"
    data_home.mkdir(parents=True)
    monkeypatch.setenv(paths.DATA_HOME_ENV, str(data_home))
    with FakeServer() as server:
        Managed(tmp_path, server, monkeypatch)
        port = server.base_url.rsplit(":", 1)[1]
        code = cli.main(["run", RECIPE, "--port", port, "--no-gpu"], suite=SUITE)

    runs = list((data_home / "baselines" / RECIPE).iterdir())
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


def test_desktop_recipe_runs_against_a_running_app_without_sudo(
    tmp_path: Path, desktop_scope: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_sudo(*_args: object) -> None:
        pytest.fail("attached runs must not request or renew sudo credentials")

    monkeypatch.setattr(cli, "refresh_sudo_ticket", unexpected_sudo)
    monkeypatch.setattr(lifecycle, "maintain_sudo_ticket", unexpected_sudo)
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


def test_run_without_endpoint_starts_the_guided_interview_and_stops_without_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recipes = tmp_path / "recipes"
    (recipes / "desktop-recipe").mkdir(parents=True)

    code = cli.main(
        ["run", "desktop-recipe", "--output", str(tmp_path / "out")], suite=SUITE, recipes=recipes
    )

    assert code == ExitCode.USAGE
    assert "Guided setup stopped" in capsys.readouterr().err


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
    summary.write_text(summary.read_text() + "\nMy own notes\n")
    (tmp_path / "run" / "results.json").unlink()

    code = cli.main(["render", str(tmp_path / "run")])

    assert code == ExitCode.OK
    assert (tmp_path / "run" / "results.json").is_file()
    assert "My own notes" in summary.read_text()


def test_render_rejects_a_directory_that_is_not_a_run(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()

    assert cli.main(["render", str(tmp_path / "empty")]) == ExitCode.USAGE


def _in_order(answers: list[str]) -> Callable[[str], str]:
    remaining = list(answers)

    def answer(prompt: str) -> str:
        return remaining.pop(0)

    return answer


@pytest.fixture
def no_app_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep host process detection out of tests; the app is not running on CI."""
    monkeypatch.setattr(guided, "find_app_pids", list)


def desktop_recipe_dir(tmp_path: Path) -> Path:
    recipes = tmp_path / "recipes"
    (recipes / "desktop-recipe").mkdir(parents=True)
    return recipes


def test_guided_desktop_run_answers_prompts_and_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_app_processes: None
) -> None:
    recipes = desktop_recipe_dir(tmp_path)
    with FakeServer() as server:
        monkeypatch.setattr("builtins.input", _in_order([server.base_url, "", "2048", "", ""]))
        code = cli.main(
            ["run", "desktop-recipe", "--output", str(tmp_path / "run"), "--no-gpu"],
            suite=SUITE,
            recipes=recipes,
        )

    meta = json.loads((tmp_path / "run" / "meta.json").read_text())
    assert code == ExitCode.OK
    assert meta["server"]["kind"] == "lmstudio"
    assert meta["server"]["model"] == "test-model"
    assert meta["server"]["context_tokens"] == 2048
    assert meta["desktop"]["pid"] is None


def test_guided_yes_accepts_every_default_against_the_fake_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_app_processes: None
) -> None:
    recipes = desktop_recipe_dir(tmp_path)

    def forbidden_input(prompt: str) -> str:
        raise AssertionError(f"--yes asked interactively: {prompt!r}")

    monkeypatch.setattr("builtins.input", forbidden_input)
    with FakeServer() as server:
        code = cli.main(
            [
                "run",
                "desktop-recipe",
                "--output",
                str(tmp_path / "run"),
                "--no-gpu",
                "--base-url",
                server.base_url,
                "--yes",
            ],
            suite=SUITE,
            recipes=recipes,
        )

    meta = json.loads((tmp_path / "run" / "meta.json").read_text())
    assert code == ExitCode.OK
    assert meta["server"]["model"] == "test-model"
    assert meta["server"]["context_tokens"] == guided.DEFAULT_CONTEXT


def test_guided_yes_stops_when_several_models_are_listed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    no_app_processes: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recipes = desktop_recipe_dir(tmp_path)
    with FakeServer() as server:
        server.models = ["model-a", "model-b"]
        code = cli.main(
            [
                "run",
                "desktop-recipe",
                "--output",
                str(tmp_path / "run"),
                "--no-gpu",
                "--base-url",
                server.base_url,
                "--yes",
            ],
            suite=SUITE,
            recipes=recipes,
        )

    assert code == ExitCode.USAGE
    assert "pass --model" in capsys.readouterr().err
    assert not (tmp_path / "run").exists()


def test_guided_declining_the_summary_cancels_before_the_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    no_app_processes: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recipes = desktop_recipe_dir(tmp_path)
    with FakeServer() as server:
        monkeypatch.setattr("builtins.input", _in_order([server.base_url, "", "2048", "", "n"]))
        code = cli.main(
            ["run", "desktop-recipe", "--output", str(tmp_path / "run"), "--no-gpu"],
            suite=SUITE,
            recipes=recipes,
        )

    assert code == ExitCode.USAGE
    assert "cancelled" in capsys.readouterr().err
    assert not (tmp_path / "run").exists()


def test_yes_option_is_rejected_for_container_recipes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["run", RECIPE, "--output", str(tmp_path / "out"), "--yes"], suite=SUITE)

    assert code == ExitCode.USAGE
    assert "--yes" in capsys.readouterr().err


@pytest.mark.parametrize("explicit", [False, True])
def test_managed_tabbyapi_chooses_target_among_served_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, explicit: bool
) -> None:
    target = "qwen3.8-27b-exl3-3bpw"
    requested = "alternate" if explicit else target
    with FakeServer() as server:
        server.models = ["draft", target, "alternate"]
        Managed(tmp_path, server, monkeypatch)
        argv = managed_argv(tmp_path, server)
        argv[1] = "qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram"
        if explicit:
            argv.extend(["--model", requested])
        code = cli.main(argv, suite=SUITE)

    assert code == ExitCode.OK
    assert {request["model"] for request in server.requests} == {requested}
    thinking = [request["chat_template_kwargs"]["enable_thinking"] for request in server.requests]
    assert thinking.count(True) == 1
    assert thinking[-1] is True
