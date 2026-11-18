"""Instance ``facts.json``: assembly, atomic last-start-wins writes, and CLI wiring."""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import host_facts
import launch
import launcher
import pytest
from launcher import LaunchOptions, Recipe

HOST: dict[str, object] = {"hostname": "bench", "kernel": "7.3.0-10-generic"}
IMAGE: dict[str, object] = {
    "image_id": "sha256:aaa",
    "image_digests": ["registry/img@sha256:bbb"],
}


def make_recipe(tmp_path: Path, adapter: str = "tabbyapi") -> Recipe:
    directory = tmp_path / "recipes/experiment-recipe"
    config = directory / "config"
    config.mkdir(parents=True)
    (config / "launch.json").write_text('{"runtime": "strata"}')
    (config / ("tabby.yml" if adapter == "tabbyapi" else "strata.json")).write_text("port: 5000\n")
    (config / "models.lock.json").write_text('{"files": []}')
    runtime = tmp_path / "runtimes/strata"
    (runtime / "scripts").mkdir(parents=True)
    (runtime / "scripts/serve.py").write_text("")
    return Recipe(
        name="experiment-recipe",
        directory=directory,
        runtime="strata",
        runtime_directory=runtime,
        adapter=adapter,
        engine="exllamav3",
        image="registry/img:latest",
        port=5000,
        context=131072,
        draft="off",
        vision="off",
    )


def make_options(tmp_path: Path) -> LaunchOptions:
    return LaunchOptions(
        name="coding",
        models=tmp_path / "models",
        logs=tmp_path / "logs",
        context=65536,
        draft="on",
        vision="cpu",
        port=18123,
        detached=True,
    )


def test_start_facts_records_options_digest_and_recipe_hashes(tmp_path: Path) -> None:
    recipe, options = make_recipe(tmp_path), make_options(tmp_path)

    facts: dict[str, Any] = launcher.start_facts(
        recipe, options, host=HOST, image=IMAGE, started_at="2026-07-28T12:00:00+00:00"
    )

    assert facts["instance"] == "coding"
    assert facts["recipe"] == "experiment-recipe"
    assert facts["image"] == {"reference": "registry/img:latest", **IMAGE}
    assert facts["options"] == {
        "port": 18123,
        "context": 65536,
        "draft": "on",
        "vision": "cpu",
        "detached": True,
    }
    expected = {
        name: hashlib.sha256((recipe.directory / "config" / name).read_bytes()).hexdigest()
        for name in ("launch.json", "tabby.yml", "models.lock.json")
    }
    assert facts["config_sha256"] == expected
    assert facts["host"] == HOST
    assert facts["mounts"]["logs"] == str(tmp_path / "logs")


def test_facts_json_last_start_wins_on_restart(tmp_path: Path) -> None:
    path = tmp_path / "facts.json"

    launcher.write_json_atomic(path, {"started_at": "first"})
    launcher.write_json_atomic(path, {"started_at": "second"})

    assert json.loads(path.read_text()) == {"started_at": "second"}
    assert not list(tmp_path.glob("*.tmp"))


def test_parse_image_inspect_rejects_malformed_output() -> None:
    with pytest.raises(ValueError, match="image inspection"):
        launcher.parse_image_inspect('["not a dict"]')


def test_record_start_facts_writes_the_instance_file_and_returns_it(
    tmp_path: Path,
) -> None:
    recipe = make_recipe(tmp_path)
    options = make_options(tmp_path)
    options.logs.mkdir()
    output = json.dumps({"Id": IMAGE["image_id"], "RepoDigests": IMAGE["image_digests"]})

    facts = launcher.record_start_facts(
        recipe,
        options,
        run=lambda command: subprocess.CompletedProcess(command, 0, stdout=output, stderr=""),
        host=lambda: dict(HOST),
        started_at=lambda: "2026-11-15T12:00:00+00:00",
    )

    written = json.loads((options.logs / "facts.json").read_text())
    assert written == facts
    assert facts["started_at"] == "2026-11-15T12:00:00+00:00"
    assert facts["image"] == {"reference": "registry/img:latest", **IMAGE}
    assert facts["host"] == HOST


def test_record_start_facts_refuses_when_the_image_is_absent(tmp_path: Path) -> None:
    recipe = make_recipe(tmp_path)
    options = make_options(tmp_path)
    options.logs.mkdir()

    with pytest.raises(ValueError, match="No such image"):
        launcher.record_start_facts(
            recipe,
            options,
            run=lambda command: subprocess.CompletedProcess(
                command, 1, stdout="", stderr="No such image: registry/img:latest"
            ),
            host=lambda: dict(HOST),
        )

    assert not (options.logs / "facts.json").exists()


def start_argv(tmp_path: Path, port: str) -> list[str]:
    return [
        "start",
        "qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram",
        "--logs",
        str(tmp_path / "logs"),
        "--models",
        str(tmp_path / "models"),
        "--context",
        "65536",
        "--port",
        port,
        "--detach",
    ]


def fake_start(command: list[str], *, status: int = 0) -> int:
    Path(command[command.index("--cidfile") + 1]).write_text("abc123")
    return status


def drive_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, port: str) -> Path:
    """Run ``launch.py start`` with every external process replaced by a fake."""
    (tmp_path / "models").mkdir()
    monkeypatch.setattr(launch, "refresh_sudo_ticket", lambda: None)
    monkeypatch.setattr(launch, "gpu_groups", list)
    monkeypatch.setattr(launch, "run_command", fake_start)
    monkeypatch.setattr(host_facts, "collect", lambda: dict(HOST))

    def fake_inspect(command: list[str]) -> subprocess.CompletedProcess[str]:
        if command[3] == "container":
            return subprocess.CompletedProcess(command, 0, f"true {IMAGE['image_id']}", "")
        assert command[:4] == ["sudo", "-n", "docker", "image"]
        output = json.dumps({"Id": IMAGE["image_id"], "RepoDigests": IMAGE["image_digests"]})
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    monkeypatch.setattr(launcher, "_capture_quiet", fake_inspect)
    logs = tmp_path / "logs"
    logs.mkdir()
    code = launch.main(start_argv(tmp_path, port))
    assert code == 0
    return logs / "facts.json"


def test_start_writes_facts_json_with_effective_options_in_instance_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = drive_start(tmp_path, monkeypatch, "18123")

    facts = json.loads(path.read_text())
    assert facts["container_id"] == "abc123"
    assert facts["options"]["port"] == 18123
    assert facts["options"]["context"] == 65536
    assert facts["image"]["image_digests"] == ["registry/img@sha256:bbb"]
    assert "tabby.yml" in facts["config_sha256"]
    assert facts["host"] == HOST


def test_facts_json_start_survives_a_missing_image_inspect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "models").mkdir()
    monkeypatch.setattr(launch, "refresh_sudo_ticket", lambda: None)
    monkeypatch.setattr(launch, "gpu_groups", list)
    monkeypatch.setattr(launch, "run_command", fake_start)
    monkeypatch.setattr(
        launcher,
        "_capture_quiet",
        lambda command: subprocess.CompletedProcess(command, 1, stdout="", stderr="No such image"),
    )
    logs = tmp_path / "logs"
    logs.mkdir()

    code = launch.main(start_argv(tmp_path, "18123"))

    assert code == 0
    assert "facts.json was not written" in capsys.readouterr().err
    assert not (logs / "facts.json").exists()


def test_launch_refreshes_sudo_ticket_once_per_docker_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(launch, "refresh_sudo_ticket", lambda: calls.append(1))
    monkeypatch.setattr(launch, "run_command", lambda command: 0)

    code = launch.main(["ps"])

    assert code == 0
    assert calls == [1]


def test_start_facts_records_runtime_descriptor_and_build_lock(tmp_path: Path) -> None:
    recipe = make_recipe(tmp_path)
    runtime = recipe.runtime_directory
    (runtime / "container").mkdir(parents=True, exist_ok=True)
    (runtime / "runtime.json").write_text("{}")
    (runtime / "container/versions.lock.json").write_text('{"version": 1}')

    facts: dict[str, Any] = launcher.start_facts(
        recipe, make_options(tmp_path), host=HOST, image=IMAGE, started_at="2026-11-16"
    )

    assert facts["config_sha256"]["runtime.json"] == hashlib.sha256(b"{}").hexdigest()
    assert (
        facts["config_sha256"]["versions.lock.json"]
        == hashlib.sha256(b'{"version": 1}').hexdigest()
    )


def test_failed_start_preserves_existing_launch_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "models").mkdir()
    logs = tmp_path / "logs"
    logs.mkdir()
    facts = logs / "facts.json"
    facts.write_text('{"container_id":"original"}')
    monkeypatch.setattr(launch, "refresh_sudo_ticket", lambda: None)
    monkeypatch.setattr(launch, "gpu_groups", list)
    monkeypatch.setattr(launch, "run_command", lambda command: fake_start(command, status=125))

    assert launch.main(start_argv(tmp_path, "18123")) == 125
    assert json.loads(facts.read_text()) == {"container_id": "original"}


def test_foreground_start_publishes_only_after_docker_reports_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace
    from threading import Event

    recipe = make_recipe(tmp_path)
    options = replace(make_options(tmp_path), detached=False)
    observed = Event()
    running = Event()
    published = Event()

    def inspect(command: list[str]) -> subprocess.CompletedProcess[str]:
        state = "true" if running.is_set() else "false"
        observed.set()
        return subprocess.CompletedProcess(command, 0, f"{state} sha256:accepted", "")

    def run(command: list[str]) -> int:
        Path(command[command.index("--cidfile") + 1]).write_text("abc123")
        assert observed.wait(5)
        assert not published.is_set()
        running.set()
        assert published.wait(5)
        return 0

    monkeypatch.setattr(launcher, "_capture_quiet", inspect)
    monkeypatch.setattr(launcher, "record_start_facts", lambda *args, **kwargs: published.set())

    assert launcher.start_with_facts(recipe, options, ["sudo", "docker", "run"], run) == (0, None)
