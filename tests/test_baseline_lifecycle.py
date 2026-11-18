"""Starting and stopping a launcher container for a baseline, with Docker faked."""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from baseline import host, lifecycle
from doctor import Finding
from launcher import LaunchOptions, discover_recipes

ROOT = Path(__file__).resolve().parents[1]
RECIPE = discover_recipes(ROOT / "recipes")[
    "qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram"
]


def done(output: str = "", code: int = 0, error: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, output, error)


class FakeDocker:
    """Answers the docker commands the control issues and records them."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.managed = ""  # output of the managed-instance listing
        self.run_result = done("abc123\n")
        self.running = True
        self.stop_result = done()
        self.inspect_error: str | None = None

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if "ps" in command:
            if "id=abc123" in command:
                if self.inspect_error:
                    return done("", 1, self.inspect_error)
                return done("abc123\n" if self.running else "")
            return done(self.managed)
        if "run" in command:
            return self.run_result
        if "stop" in command:
            if self.stop_result.returncode == 0:
                self.running = False
            return self.stop_result
        raise AssertionError(command)


def make_control(
    tmp_path: Path,
    docker: FakeDocker,
    *,
    findings: list[Finding] | None = None,
    vram_gib: float | None = 0.2,
    record_facts: Callable[[host.ContainerInfo], dict[str, object]] = lambda _: {},
) -> lifecycle.ContainerControl:
    options = LaunchOptions(
        "baseline", tmp_path / "models", tmp_path / "logs", 131072, "on", "cpu", 8080, True
    )
    (tmp_path / "models").mkdir(exist_ok=True)

    def resolve(instance: str) -> host.ContainerInfo:
        return host.ContainerInfo("abc123", 77, tmp_path / "cg", "sha256:img", "repo/image:tag")

    return lifecycle.ContainerControl(
        RECIPE,
        options,
        run=docker,
        slow_run=docker,
        diagnose=lambda recipe, models: findings or [Finding("Docker", "PASS", "ok")],
        gpu_vram_gib=lambda: vram_gib,
        resolve=resolve,
        gpu_groups=lambda: [44, 105],
        record_facts=record_facts,
    )


def test_preflight_passes_on_a_clean_machine(tmp_path: Path) -> None:
    make_control(tmp_path, FakeDocker()).preflight()


def test_preflight_reports_failed_diagnostics(tmp_path: Path) -> None:
    findings = [Finding("Model files", "FAIL", "shard missing"), Finding("Docker", "PASS", "ok")]

    with pytest.raises(lifecycle.LifecycleError, match="Model files: shard missing"):
        make_control(tmp_path, FakeDocker(), findings=findings).preflight()


def test_preflight_refuses_while_another_launcher_instance_runs(tmp_path: Path) -> None:
    docker = FakeDocker()
    docker.managed = "coding\n"

    with pytest.raises(lifecycle.LifecycleError, match=r"coding.*launch\.py stop"):
        make_control(tmp_path, docker).preflight()


def test_preflight_refuses_when_the_gpu_is_already_in_use(tmp_path: Path) -> None:
    with pytest.raises(lifecycle.LifecycleError, match=r"15\.3 GiB"):
        make_control(tmp_path, FakeDocker(), vram_gib=15.3).preflight()


def test_preflight_tolerates_unreadable_gpu_memory(tmp_path: Path) -> None:
    make_control(tmp_path, FakeDocker(), vram_gib=None).preflight()


def test_start_runs_a_detached_labeled_container_and_resolves_its_cgroup(tmp_path: Path) -> None:
    docker = FakeDocker()

    started = make_control(tmp_path, docker).start()

    command = next(c for c in docker.commands if "run" in c)
    assert command[:4] == ["sudo", "-n", "docker", "run"]
    assert "--detach" in command
    assert "io.llm-recipes.instance=baseline" in command
    assert f"{tmp_path / 'logs'}:/logs" in " ".join(command) or str(tmp_path / "logs") in " ".join(
        command
    )
    assert started.cgroup == tmp_path / "cg"
    assert started.meta["container_id"] == "abc123"
    assert started.meta["image_id"] == "sha256:img"
    assert started.meta["instance"] == "baseline"
    assert started.meta["launch_facts"] is None


def test_start_attaches_recorded_facts_to_the_started_meta(tmp_path: Path) -> None:
    facts = {"started_at": "2026-11-15T12:00:00+00:00", "host": {"hostname": "bench"}}

    started = make_control(tmp_path, FakeDocker(), record_facts=lambda _: dict(facts)).start()

    assert started.meta["launch_facts"] == facts


def test_start_reports_failure_when_facts_cannot_be_recorded(tmp_path: Path) -> None:
    def broken_facts(_info: host.ContainerInfo) -> dict[str, object]:
        raise OSError("log directory is not writable")

    docker = FakeDocker()

    with pytest.raises(lifecycle.LifecycleError, match="start facts"):
        make_control(tmp_path, docker, record_facts=broken_facts).start()

    assert any("run" in command for command in docker.commands)


def test_start_reports_a_failed_launch_with_docker_output(tmp_path: Path) -> None:
    docker = FakeDocker()
    docker.run_result = done("", 125, "port is already allocated")

    with pytest.raises(lifecycle.LifecycleError, match="port is already allocated"):
        make_control(tmp_path, docker).start()


def test_start_rejects_invalid_options_before_running_docker(tmp_path: Path) -> None:
    docker = FakeDocker()
    control = make_control(tmp_path, docker)
    control._options = LaunchOptions(
        "baseline", tmp_path / "models", tmp_path / "logs", 100, "on", "cpu", 8080, True
    )

    with pytest.raises(lifecycle.LifecycleError, match="context"):
        control.start()

    assert not any("run" in command for command in docker.commands)


def test_is_running_asks_docker_about_the_container(tmp_path: Path) -> None:
    docker = FakeDocker()
    control = make_control(tmp_path, docker)

    control.start()
    assert control.is_running() is True
    docker.running = False
    assert control.is_running() is False


def test_stop_targets_the_owned_container_id(tmp_path: Path) -> None:
    docker = FakeDocker()

    control = make_control(tmp_path, docker)
    control.start()
    control.stop()

    assert ["sudo", "-n", "docker", "stop", "abc123"] in docker.commands


def test_stop_does_nothing_when_the_container_is_already_gone(tmp_path: Path) -> None:
    docker = FakeDocker()
    docker.running = False

    control = make_control(tmp_path, docker)
    control.start()
    control.stop()

    assert not any("stop" in command for command in docker.commands)


def test_stop_failure_says_which_command_to_run(tmp_path: Path) -> None:
    docker = FakeDocker()
    docker.stop_result = done("", 1, "daemon error")

    control = make_control(tmp_path, docker)
    control.start()
    with pytest.raises(lifecycle.LifecycleError, match="sudo docker stop abc123"):
        control.stop()


def test_stop_reports_expired_sudo_for_owned_container(tmp_path: Path) -> None:
    docker = FakeDocker()
    control = make_control(tmp_path, docker)
    control.start()
    docker.inspect_error = "sudo: a password is required"

    with pytest.raises(lifecycle.LifecycleError, match="a password is required"):
        control.stop()


def test_stop_does_not_touch_an_unowned_container_after_start_failure(tmp_path: Path) -> None:
    docker = FakeDocker()
    docker.run_result = done("", 125, "name is already in use")
    control = make_control(tmp_path, docker)
    with pytest.raises(lifecycle.LifecycleError, match="already in use"):
        control.start()

    control.stop()

    assert docker.running
    assert not any("stop" in command for command in docker.commands)
