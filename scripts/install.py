#!/usr/bin/env python3
"""Install the serving snapshot, runtime environment, and command shims."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import paths
from launcher import discover_recipes, local_selections, refresh_sudo_ticket

RUNTIME_INCLUDES = ("scripts", "recipes", "runtimes", "assets", "templates")
RUNTIME_REQUIREMENTS = ("PyYAML==6.0.3", "textual==8.2.8")
COMMANDS = {"llm-recipes": "launch.py", "llm-recipes-baseline": "run_baseline.py"}
IGNORED_DIRECTORIES = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def log(message: str) -> None:
    print(message, flush=True)


def run_process(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True, timeout=120)


def running_instances() -> list[str]:
    """Launcher-managed container names; empty when nothing is serving."""
    probe = run_process(
        [
            "sudo",
            "-n",
            "docker",
            "ps",
            "--filter",
            "label=io.llm-recipes.managed=true",
            "--format",
            "{{.Names}}",
        ]
    )
    if probe.returncode:
        detail = probe.stderr.strip() or "docker inspection failed"
        raise RuntimeError(
            f"cannot check running instances ({detail}); check Docker availability and sudo access"
        )
    return [name for name in probe.stdout.splitlines() if name.strip()]


def repository_commit(root: Path) -> str | None:
    """HEAD commit of the checkout; ``None`` for a source tree without git."""
    revision = run_process(["git", "-C", str(root), "rev-parse", "HEAD"])
    return revision.stdout.strip() if revision.returncode == 0 else None


def build_snapshot(root: Path, destination: Path) -> None:
    """Copy the runtime trees and stamp the snapshot into ``destination``."""
    destination.mkdir(parents=True)
    for name in RUNTIME_INCLUDES:
        source = root / name
        if source.is_dir():
            shutil.copytree(source, destination / name, ignore=IGNORED_DIRECTORIES)
    stamp = {
        "repo_commit": repository_commit(root),
        "installed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "version": "2",
    }
    (destination / "VERSION").write_text(json.dumps(stamp, indent=2) + "\n")


def create_venv(venv: Path, base_python: str) -> None:
    """Create the runtime venv with its dependencies, preferring ``uv`` when present."""
    if shutil.which("uv"):
        made = run_process(["uv", "venv", str(venv), "--python", base_python])
        if made.returncode == 0:
            installed = run_process(
                [
                    "uv",
                    "pip",
                    "install",
                    "--quiet",
                    "--python",
                    str(venv / "bin/python"),
                    *RUNTIME_REQUIREMENTS,
                ]
            )
            if installed.returncode:
                detail = installed.stderr.strip() or installed.stdout.strip()
                raise RuntimeError(f"runtime dependency install failed: {detail}")
            return
    created = run_process([base_python, "-m", "venv", str(venv)])
    if created.returncode:
        detail = created.stderr.strip() or created.stdout.strip()
        raise RuntimeError(f"venv creation failed: {detail}")
    installed = run_process([str(venv / "bin/pip"), "install", "--quiet", *RUNTIME_REQUIREMENTS])
    if installed.returncode:
        raise RuntimeError(f"runtime dependency install failed: {installed.stderr.strip()}")


def runtime_environment(prefix: Path) -> Path:
    """Reuse an environment at its permanent path for this Python and dependency set."""
    identity = json.dumps([sys.executable, sys.version, RUNTIME_REQUIREMENTS])
    key = hashlib.sha256(identity.encode()).hexdigest()[:16]
    environment = prefix / "environments" / key
    ready = environment / ".ready"
    if not ready.is_file():
        if environment.exists():
            shutil.rmtree(environment)
        environment.parent.mkdir(parents=True, exist_ok=True)
        create_venv(environment, sys.executable)
        ready.touch()
    return environment


def validate_shims(prefix: Path) -> None:
    """Refuse to replace commands owned by another installation or tool."""
    for name in COMMANDS:
        shim = prefix / "bin" / name
        if shim.is_symlink() or (shim.exists() and not shim.is_file()):
            raise RuntimeError(f"refusing to overwrite non-file shim: {shim}")
        link = Path.home() / ".local/bin" / name
        if link.is_symlink():
            if link.readlink() != prefix / "bin" / name:
                raise RuntimeError(f"refusing to replace unrelated command: {link}")
        elif link.exists():
            raise RuntimeError(f"refusing to replace unrelated command: {link}")


def write_shims(prefix: Path) -> None:
    """Write quoted command shims and link them into the user's PATH."""
    validate_shims(prefix)
    bin_dir = prefix / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    runtime_python = prefix / "app/.venv/bin/python"
    for shim, script in COMMANDS.items():
        path = bin_dir / shim
        command = shlex.join([str(runtime_python), str(prefix / "app/scripts" / script)])
        path.write_text(f'#!/bin/sh\nexec {command} "$@"\n')
        path.chmod(0o755)
    user_bin = Path.home() / ".local/bin"
    user_bin.mkdir(parents=True, exist_ok=True)
    for shim in COMMANDS:
        link = user_bin / shim
        if link.is_symlink():
            link.unlink()
        link.symlink_to(bin_dir / shim)


def published_selections(staging: Path, prefix: Path) -> list[Path]:
    """Find active Strata trials whose release and build lock the snapshot now ships."""
    matches: list[Path] = []
    selections = sorted((prefix / "selections").glob("*.json"))
    if not selections:
        return matches
    recipes = discover_recipes(staging / "recipes", local=False)
    for selection in selections:
        recipe = recipes.get(selection.stem)
        if not recipe or not recipe.runtime.startswith("strata/releases/"):
            continue
        stack = local_selections(recipe.name, prefix=prefix)
        if not stack:
            continue
        checkout = Path(stack[-1])
        manifest = checkout / recipe.data_subpath / "config/launch.json"
        lock = Path("container/versions.lock.json")
        try:
            if json.loads(manifest.read_text())["runtime"] != recipe.runtime:
                continue
            trial = json.loads((checkout / "runtimes" / recipe.runtime / lock).read_text())
            incoming = json.loads((recipe.runtime_directory / lock).read_text())
            if isinstance(incoming, dict) and incoming and incoming == trial:
                matches.append(selection)
        except (OSError, ValueError, KeyError, TypeError) as error:
            log(f"{recipe.name}: keeping adopted selection; cannot verify build: {error}")
    return matches


def activate_snapshot(prefix: Path, selections: list[Path]) -> None:
    """Publish staged code and shims, restoring the active installation on failure."""
    app, previous = prefix / "app", prefix / "app.prev"
    bin_dir = prefix / "bin"
    links = {
        Path.home() / ".local/bin" / name: (prefix / "bin" / name)
        for name in COMMANDS
        if (Path.home() / ".local/bin" / name).is_symlink()
    }
    with tempfile.TemporaryDirectory(prefix=".shims-", dir=prefix) as temporary:
        backup = Path(temporary) / "bin"
        if bin_dir.exists():
            shutil.copytree(bin_dir, backup, symlinks=True)
        had_app = app.exists()
        if had_app:
            if previous.exists():
                shutil.rmtree(previous)
            app.rename(previous)
        try:
            (prefix / "app.new").rename(app)
            write_shims(prefix)
            for selection in selections:
                selection.rename(Path(temporary) / selection.name)
        except BaseException:  # Roll back interruptions as well as errors, then re-raise.
            for selection in selections:
                saved = Path(temporary) / selection.name
                if saved.exists():
                    saved.rename(selection)
            if app.exists():
                shutil.rmtree(app)
            if had_app:
                previous.rename(app)
            if bin_dir.exists():
                shutil.rmtree(bin_dir)
            if backup.exists():
                shutil.copytree(backup, bin_dir, symlinks=True)
            for name in COMMANDS:
                link = Path.home() / ".local/bin" / name
                if link.is_symlink():
                    link.unlink()
                if link in links:
                    link.symlink_to(links[link])
            raise


def install(root: Path, prefix: Path, *, force: bool, with_dependencies: bool) -> int:
    """Serialize snapshot preparation and activate it with rollback on failure."""
    prefix = prefix.expanduser().resolve()
    prefix.mkdir(parents=True, exist_ok=True)
    with (prefix / ".install.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("another installation is in progress") from error
        validate_shims(prefix)
        if not force and running_instances():
            log("refusing to swap while launcher instances run; stop them or pass --force")
            return 1
        staging = prefix / "app.new"
        if staging.exists():
            shutil.rmtree(staging)
        try:
            build_snapshot(root, staging)
            if with_dependencies:
                (staging / ".venv").symlink_to(
                    runtime_environment(prefix), target_is_directory=True
                )
            stamp = json.loads((staging / "VERSION").read_text())
            selections = published_selections(staging, prefix)
            activate_snapshot(prefix, selections)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        for selection in selections:
            log(f"{selection.stem}: using installed configuration (adopted build matches)")
        revision = stamp["repo_commit"] or "unknown commit"
        log(f"installed snapshot of {revision} into {prefix / 'app'}")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("install", help="copy the runtime snapshot and refresh shims")
    setup.add_argument("--force", action="store_true", help="swap even while instances run")
    setup.add_argument(
        "--skip-deps", action="store_true", help="skip venv creation (development use)"
    )
    args = parser.parse_args(argv)
    prefix = paths.runtime_prefix()
    try:
        if not args.force:
            try:
                refresh_sudo_ticket()
            except ValueError as error:
                raise RuntimeError(str(error)) from error
        return install(repo_root(), prefix, force=args.force, with_dependencies=not args.skip_deps)
    except subprocess.TimeoutExpired as error:
        command = shlex.join(error.cmd) if isinstance(error.cmd, list) else str(error.cmd)
        print(
            f"install: command timed out after {error.timeout}s: {command}; "
            "check the command's availability or network access and retry",
            file=sys.stderr,
        )
        return 1
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"install: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
