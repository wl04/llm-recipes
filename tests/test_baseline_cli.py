"""The command line: run, render, argument validation, and output conventions."""

import json
import os
from pathlib import Path

import generate_configurations as generator
import pytest
from baseline import cli, host, schema
from baseline.schema import ExitCode
from fake_server import FakeServer
from test_baseline_runner import SUITE
from test_baseline_sources import make_cgroup

ROOT = Path(__file__).resolve().parents[1]
RECIPE = "qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram"


@pytest.fixture(autouse=True)
def fake_server_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Resolve any --pid to a fake application scope so tests do not read the real cgroup."""
    cgroup = make_cgroup(tmp_path / "cgroups")
    (cgroup / "cgroup.procs").write_text(f"{os.getpid()}\n")
    monkeypatch.setattr(host, "cgroup_path_of", lambda pid: cgroup)
    return cgroup


def run_cli(
    tmp_path: Path, server: FakeServer, *extra: str, recipe: str = RECIPE, name: str = "run"
) -> int:
    argv = [
        "run", recipe, "--output", str(tmp_path / name), "--base-url", server.base_url + "/v1",
        "--model", "test-model", "--context", "2048", "--no-gpu", "--pid", str(os.getpid()),
        *extra,
    ]  # fmt: skip
    return cli.main(argv, suite=SUITE)


def test_run_writes_results_summary_and_raw_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with FakeServer() as server:
        code = run_cli(tmp_path, server)

    output = tmp_path / "run"
    assert code == ExitCode.OK
    for name in ("meta.json", "requests.jsonl", "samples.jsonl", "results.json", "summary.md"):
        assert (output / name).is_file()
    schema.validate_results(json.loads((output / "results.json").read_text()))
    assert "## Baseline results" in (output / "summary.md").read_text()
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1
    assert str(output) in captured.out
    assert "[baseline]" in captured.err
    assert "[baseline]" not in captured.out


def test_run_summary_is_current_for_the_generator(tmp_path: Path) -> None:
    with FakeServer() as server:
        run_cli(tmp_path, server)

    _, before, after = generator.update_results(tmp_path / "run")

    assert before == after


def test_run_records_host_and_workload_facts_in_meta(tmp_path: Path) -> None:
    with FakeServer() as server:
        run_cli(tmp_path, server)

    meta = json.loads((tmp_path / "run" / "meta.json").read_text())
    assert meta["server"]["kind"] == "strata"
    assert meta["server"]["model"] == "test-model"
    assert "uptime_s" in meta["boot"]["metrics"]
    assert meta["host"]["python"]
    assert meta["workload"]["corpus_sha256"]


def test_run_accepts_a_desktop_recipe_with_explicit_endpoint(tmp_path: Path) -> None:
    recipes = tmp_path / "recipes"
    (recipes / "desktop-recipe").mkdir(parents=True)
    with FakeServer() as server:
        argv = [
            "run", "desktop-recipe", "--output", str(tmp_path / "run"),
            "--base-url", server.base_url, "--model", "test-model", "--context", "2048", "--no-gpu",
            "--server-kind", "lmstudio", "--pid", str(os.getpid()),
        ]  # fmt: skip
        code = cli.main(argv, suite=SUITE, recipes=recipes)

    meta = json.loads((tmp_path / "run" / "meta.json").read_text())
    assert code == ExitCode.OK
    assert meta["server"]["kind"] == "lmstudio"
    assert meta["workload"]["image"].endswith("amdgpu-top.png")


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["run", "no-such-recipe", "--output", "{out}"], "Unknown recipe"),
        (["run", RECIPE, "--output", "{out}", "--instance", "a", "--pid", "1"], "not both"),
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


def test_run_refuses_to_reuse_an_output_directory(tmp_path: Path) -> None:
    (tmp_path / "run").mkdir()
    with FakeServer() as server:
        code = run_cli(tmp_path, server)

    assert code == ExitCode.USAGE
    assert server.requests == []


def test_run_reports_unreachable_container_with_preflight_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(instance: str) -> host.ContainerInfo:
        raise host.HostError("No running instance 'x' was found")

    monkeypatch.setattr(host, "resolve_container", fail)

    code = cli.main(
        ["run", RECIPE, "--output", str(tmp_path / "out"), "--instance", "x", "--no-gpu"],
        suite=SUITE,
    )

    assert code == ExitCode.PREFLIGHT_FAILED
    assert "No running instance" in capsys.readouterr().err


def test_run_exits_with_preflight_code_when_the_server_is_unreachable(tmp_path: Path) -> None:
    argv = [
        "run", RECIPE, "--output", str(tmp_path / "run"), "--base-url", "http://127.0.0.1:9",
        "--model", "m", "--context", "2048", "--no-gpu",
    ]  # fmt: skip

    code = cli.main(argv, suite=SUITE)

    meta = json.loads((tmp_path / "run" / "meta.json").read_text())
    assert code == ExitCode.PREFLIGHT_FAILED
    assert meta["run"]["status"] == "failed"
    assert (tmp_path / "run" / "results.json").is_file()


def test_render_rebuilds_results_and_keeps_authored_summary_text(tmp_path: Path) -> None:
    with FakeServer() as server:
        run_cli(tmp_path, server)
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
