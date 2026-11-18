"""Start and stop the server of a launcher recipe for the duration of a baseline.

The runner never builds Docker commands itself: it reuses the launcher's validated start and stop
commands, under a dedicated instance name so an instance the user started is never touched.
"""

import os
import re
import shlex
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import doctor
import launcher
from launcher import LaunchOptions, Recipe

from baseline import host

INSTANCE = "baseline"
GPU_IN_USE_GIB = 2.0
RESOLVE_ATTEMPTS = 20
SLOW_COMMAND_TIMEOUT_S = 300.0


class LifecycleError(Exception):
    """The server could not be started or stopped; the message says what to do."""


@dataclass(frozen=True)
class StartedServer:
    """A running server: where to measure it, and what to record about it."""

    cgroup: Path
    meta: dict[str, Any]


def _non_interactive(command: list[str]) -> list[str]:
    """Make a ``sudo`` command fail instead of prompting for a password mid-run."""
    return [command[0], "-n", *command[1:]] if command and command[0] == "sudo" else command


class ContainerControl:
    """Lifecycle of one launcher container, with every outside dependency injectable."""

    def __init__(
        self,
        recipe: Recipe,
        options: LaunchOptions,
        *,
        run: host.Run = host.run_command,
        slow_run: host.Run = lambda command: host.run_command(command, SLOW_COMMAND_TIMEOUT_S),
        diagnose: Callable[[Recipe, Path], list[doctor.Finding]] = doctor.diagnose,
        gpu_vram_gib: Callable[[], float | None] = lambda: None,
        resolve: Callable[[str], host.ContainerInfo] = host.resolve_container,
        gpu_groups: Callable[[], list[int]] = launcher.gpu_groups,
        sleep: Callable[[float], None] = time.sleep,
        record_facts: Callable[[host.ContainerInfo], dict[str, object]] = lambda _: {},
    ) -> None:
        self._recipe = recipe
        self._options = options
        self._run = run
        self._slow_run = slow_run
        self._diagnose = diagnose
        self._gpu_vram_gib = gpu_vram_gib
        self._resolve = resolve
        self._gpu_groups = gpu_groups
        self._sleep = sleep
        self._record_facts = record_facts
        self._container: str | None = None

    def preflight(self) -> None:
        """Refuse to start unless the recipe is prepared and the machine is free for it.

        Raises:
            LifecycleError: diagnostics failed, another launcher instance runs, or the GPU is
                already holding memory.
        """
        failed = [
            f"{item.name}: {item.detail}"
            for item in self._diagnose(self._recipe, self._options.models)
            if item.status == "FAIL"
        ]
        if failed:
            raise LifecycleError("The recipe is not ready: " + "; ".join(failed))
        listing = self._run(
            _non_interactive(
                [
                    "sudo", "docker", "ps",
                    "--filter", f"label={host.MANAGED_LABEL}=true",
                    "--format", f'{{{{.Label "{host.INSTANCE_LABEL}"}}}}',
                ]
            )
        )  # fmt: skip
        if listing.returncode:
            raise LifecycleError(
                f"Docker inspection failed: {listing.stderr.strip()}. "
                "Re-run to refresh sudo credentials."
            )
        names = listing.stdout.split()
        if names:
            raise LifecycleError(
                f"Launcher instance(s) already running: {', '.join(names)}. "
                "Stop them first, for example `python3 scripts/launch.py stop " + names[0] + "`."
            )
        used = self._gpu_vram_gib()
        if used is not None and used > GPU_IN_USE_GIB:
            raise LifecycleError(
                f"The GPU already holds {used:.1f} GiB. Close the application or server using it "
                "so the baseline starts from an idle GPU."
            )

    def start(self) -> StartedServer:
        """Start the container detached and resolve its cgroup.

        Raises:
            LifecycleError: the options are invalid, Docker refused, or the container is gone.
        """
        try:
            command = launcher.start_command(
                self._recipe,
                self._options,
                groups=self._gpu_groups(),
                uid=os.getuid(),
                gid=os.getgid(),
            )
            launcher.prepare_start(self._recipe, self._options)
        except (ValueError, OSError) as error:
            raise LifecycleError(f"Cannot start {self._recipe.name}: {error}") from error
        command = _non_interactive(command)
        result = self._slow_run(command)
        if result.returncode:
            raise LifecycleError(f"Docker could not start the server: {result.stderr.strip()}")
        container_id = result.stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{6,64}", container_id):
            raise LifecycleError("Docker did not return a container ID for the baseline")
        self._container = container_id
        info = self._wait_for_container(container_id)
        try:
            facts = self._record_facts(info)
        except (ValueError, OSError) as error:
            raise LifecycleError(f"Cannot record the start facts: {error}") from error
        return StartedServer(
            info.cgroup,
            {
                "instance": self._options.name,
                "container_id": info.container_id,
                "image": info.image,
                "image_id": info.image_id,
                "logs": str(self._options.logs),
                "launch_command": shlex.join(command),
                "launch_facts": facts or None,
            },
        )

    def _wait_for_container(self, container_id: str) -> host.ContainerInfo:
        last = ""
        for _ in range(RESOLVE_ATTEMPTS):
            try:
                info = self._resolve(self._options.name)
            except host.HostError as error:
                last = str(error)
                self._sleep(0.5)
            else:
                if not container_id.startswith(info.container_id):
                    raise LifecycleError("The baseline instance belongs to a different container")
                return info
        raise LifecycleError(f"The container did not appear: {last}")

    def is_running(self) -> bool:
        """Whether the container is still running."""
        if self._container is None:
            return False
        result = self._run(
            [
                "sudo",
                "-n",
                "docker",
                "ps",
                "--no-trunc",
                "--filter",
                f"id={self._container}",
                "--format",
                "{{.ID}}",
            ]
        )
        if result.returncode:
            detail = result.stderr.strip() or "Docker inspection failed"
            raise LifecycleError(
                f"Cannot inspect baseline container {self._container}: {detail}. "
                f"Check sudo or Docker and stop it with: sudo docker stop {self._container}"
            )
        return self._container in result.stdout.split()

    def stop(self) -> None:
        """Stop the owned container if still running."""
        if self._container is None or not self.is_running():
            return
        result = self._slow_run(["sudo", "-n", "docker", "stop", self._container])
        if result.returncode:
            if not self.is_running():
                return
            raise LifecycleError(
                f"Docker could not stop the server ({result.stderr.strip()}). "
                f"Stop it yourself with: sudo docker stop {self._container}"
            )
