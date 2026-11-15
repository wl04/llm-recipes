"""Contract checks for the host launcher; no Docker or GPU required."""

import json
import subprocess
import sys
from pathlib import Path

import launch
import launcher
import pytest

ROOT = Path(__file__).resolve().parents[1]


def recipe_for(adapter: str) -> launcher.Recipe:
    """A checked-in recipe for one adapter; the CLI cases run the real launcher."""
    recipes = launcher.discover_recipes(ROOT / "recipes")
    matches = sorted((r for r in recipes.values() if r.adapter == adapter), key=lambda r: r.name)
    if not matches:
        pytest.fail(f"no checked-in {adapter} recipe to exercise the launcher CLI")
    return matches[0]


@pytest.fixture(scope="module")
def recipe() -> launcher.Recipe:
    return recipe_for("tabbyapi")


def record_run_command(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Replace the execution step with a recorder of the commands it was given."""
    commands: list[list[str]] = []

    def run(command: list[str]) -> int:
        commands.append(command)
        return 0

    monkeypatch.setattr(launch, "run_command", run)
    monkeypatch.setattr(launch, "refresh_sudo_ticket", lambda: None)
    return commands


def test_stop_propagates_docker_invocation(monkeypatch: pytest.MonkeyPatch) -> None:
    commands = record_run_command(monkeypatch)

    assert launch.main(["stop", "exl3"]) == 0
    assert commands == [["sudo", "docker", "stop", "llm-recipes-exl3"]]


def test_logs_follows_console_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    commands = record_run_command(monkeypatch)

    assert launch.main(["logs", "exl3", "--follow"]) == 0
    assert commands == [["sudo", "docker", "logs", "--follow", "llm-recipes-exl3"]]


def test_mount_rejects_delimiters_in_paths() -> None:
    with pytest.raises(ValueError, match="comma or newline"):
        launcher.mount(Path("/models,readonly"), "/models")


def test_parse_instances_rejects_malformed_line() -> None:
    with pytest.raises(ValueError, match="unexpected instance listing line"):
        launcher.parse_instances("alpha\texl3\n")


def test_start_preserves_mount_boundaries_with_spaces(recipe: launcher.Recipe) -> None:
    command = launcher.start_command(
        recipe,
        launcher.LaunchOptions(
            "coding", Path("/models with spaces"), Path("/logs"), 131072, "on", "on", 5001
        ),
        groups=[109],
        uid=1000,
        gid=1000,
    )

    assert "type=bind,src=/models with spaces,dst=/models,readonly" in command
    assert "type=bind,src=/logs,dst=/logs" in command
    assert "127.0.0.1:5001:5000" in command
    assert command[-8:] == [
        "--draft",
        "on",
        "--vision",
        "on",
        "--context",
        "131072",
        "--recipe",
        f"/recipes/{recipe.name}",
    ]


def test_start_rejects_invalid_context_before_execution(recipe: launcher.Recipe) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/launch.py"),
            "start",
            recipe.name,
            "--context",
            "1025",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "multiple of 256" in result.stderr


def test_start_rejects_unsupported_vision_before_execution(recipe: launcher.Recipe) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/launch.py"),
            "start",
            recipe.name,
            "--vision",
            "cpu",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2


def test_start_dry_run_leaves_directories_absent_without_gpu(
    recipe: launcher.Recipe, tmp_path: Path
) -> None:
    models = tmp_path / "models"
    logs = tmp_path / "logs"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/launch.py"),
            "start",
            recipe.name,
            "--models",
            str(models),
            "--logs",
            str(logs),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "sudo docker run" in result.stdout
    assert not models.exists()
    assert not logs.exists()


def test_instances_command_emits_machine_readable_fields() -> None:
    command = launcher.instances_command()

    format_argument = command[command.index("--format") + 1]

    assert "table " not in format_argument
    assert '{{.Label "io.llm-recipes.instance"}}' in format_argument


def test_parse_instances_reads_tab_separated_records() -> None:
    output = "alpha\texl3\tUp 2 minutes\t0.0.0.0:5000->5000/tcp\nbeta\tstrata\tUp 9 seconds\t\n\n"

    records = launcher.parse_instances(output)

    assert records[0] == {
        "instance": "alpha",
        "recipe": "exl3",
        "status": "Up 2 minutes",
        "ports": "0.0.0.0:5000->5000/tcp",
    }
    assert records[1]["ports"] == ""


def test_list_json_emits_recipe_records(
    recipe: launcher.Recipe, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(launch, "discover_recipes", lambda _: {recipe.name: recipe})

    assert launch.main(["list", "--json"]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data[0]["name"] == recipe.name
    assert data[0]["port"] == recipe.port


def test_ps_json_parses_instance_listing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    listing = subprocess.CompletedProcess(
        launcher.instances_command(),
        0,
        "alpha\texl3\tUp 2 minutes\t0.0.0.0:5000->5000/tcp\n",
        "",
    )
    monkeypatch.setattr(launch, "capture", lambda _: listing)
    monkeypatch.setattr(launch, "refresh_sudo_ticket", lambda: None)

    assert launch.main(["ps", "--json"]) == 0

    assert json.loads(capsys.readouterr().out)[0]["instance"] == "alpha"


def test_status_json_reports_missing_instances_as_not_found(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    inspection = subprocess.CompletedProcess(
        launcher.lifecycle_command("status", "gone"), 1, "", "Error: No such object"
    )
    monkeypatch.setattr(launch, "capture", lambda _: inspection)
    monkeypatch.setattr(launch, "refresh_sudo_ticket", lambda: None)

    assert launch.main(["status", "gone", "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == {"instance": "gone", "status": "not-found"}
