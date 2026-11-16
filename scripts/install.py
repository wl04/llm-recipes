#!/usr/bin/env python3
"""Install the serving snapshot, runtime environment, and command shims."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import paths

RUNTIME_INCLUDES = ("scripts", "recipes", "runtimes", "assets", "templates")
RUNTIME_REQUIREMENTS = ("PyYAML==6.0.3",)
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
        raise RuntimeError(f"cannot check running instances ({detail}); stop them and retry")
    return [name for name in probe.stdout.splitlines() if name.strip()]


def repository_commit(root: Path) -> str | None:
    """HEAD commit of the checkout; ``None`` for a source tree without git."""
    revision = run_process(["git", "-C", str(root), "rev-parse", "HEAD"])
    return revision.stdout.strip() if revision.returncode == 0 else None


def build_snapshot(root: Path, destination: Path, *, with_dependencies: bool) -> None:
    """Copy the runtime trees and stamp the snapshot into ``destination``."""
    destination.mkdir(parents=True)
    for name in RUNTIME_INCLUDES:
        source = root / name
        if source.is_dir():
            shutil.copytree(source, destination / name, ignore=IGNORED_DIRECTORIES)
    stamp = {
        "repo_commit": repository_commit(root),
        "installed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "version": "1",
    }
    (destination / "VERSION").write_text(json.dumps(stamp, indent=2) + "\n")
    if with_dependencies:
        create_venv(destination / ".venv", sys.executable)


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


def write_shims(prefix: Path) -> None:
    """Command shims that run the installed snapshot with its own venv."""
    bin_dir = prefix / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    runtime_python = prefix / "app/.venv/bin/python"
    commands = {
        "llm-recipes": "launch.py",
        "llm-recipes-baseline": "run_baseline.py",
    }
    for shim, script in commands.items():
        path = bin_dir / shim
        path.write_text(
            f'#!/bin/sh\nexec "{runtime_python}" "{prefix / "app/scripts" / script}" "$@"\n'
        )
        path.chmod(0o755)
    user_bin = Path.home() / ".local/bin"
    user_bin.mkdir(parents=True, exist_ok=True)
    for shim in commands:
        link = user_bin / shim
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(bin_dir / shim)


def install(root: Path, prefix: Path, *, force: bool, with_dependencies: bool) -> int:
    """Build ``app.new``, swap it in atomically, and refresh the shims."""
    if not force and running_instances():
        log("refusing to swap while launcher instances run; stop them or pass --force")
        return 1
    staging = prefix / "app.new"
    if staging.exists():
        shutil.rmtree(staging)
    build_snapshot(root, staging, with_dependencies=with_dependencies)
    app = prefix / "app"
    previous = prefix / "app.prev"
    if app.exists():
        if previous.exists():
            shutil.rmtree(previous)
        app.rename(previous)
    staging.rename(app)
    write_shims(prefix)
    stamp = json.loads((app / "VERSION").read_text())
    log(f"installed snapshot of {stamp['repo_commit'] or 'unknown commit'} into {app}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("install", help="copy the runtime snapshot and refresh shims")
    setup.add_argument("--force", action="store_true", help="swap even while instances run")
    setup.add_argument(
        "--skip-deps", action="store_true", help="skip venv creation (development use)"
    )
    args = parser.parse_args(argv)
    prefix = paths.runtime_prefix()
    try:
        return install(repo_root(), prefix, force=args.force, with_dependencies=not args.skip_deps)
    except RuntimeError as error:
        log(f"error: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
