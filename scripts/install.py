#!/usr/bin/env python3
"""Install the serving snapshot and cut the machine over to the data home.

``install`` copies the runtime trees into ``~/.llm-recipes/app`` (as
``app.new`` first, then an atomic rename), stamps ``VERSION``, creates the
runtime venv, and writes the ``llm-recipes`` shims into the app prefix,
symlinked from ``~/.local/bin``. The development checkout keeps working
directly; serving always runs from the installed snapshot.

``migrate-data`` performs the one-time move of the legacy ``$HOME/Models``
data root into the data home under the strict layout. It is dry-run by
default, journals every completed move, resumes where an interrupted run
stopped, and never copies data or overwrites an existing destination.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import paths

RUNTIME_INCLUDES = ("scripts", "recipes", "runtimes", "assets", "templates")
RUNTIME_REQUIREMENTS = ("PyYAML==6.0.3",)
JOURNAL_NAME = "migrate-journal.jsonl"
IGNORED_DIRECTORIES = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv")
OLD_DATA_ROOT = Path.home() / "Models" / "llm-recipes"
SHARED_DIRECTORIES = (".cache", "baselines", "logs")
EXL3_RECIPE = "qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram"
ISTA_RECIPE = "qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram"
UNSLOTH_RECIPE = "qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram"
EXL3_DATA_FOLDERS = (
    "qwen3.8-27b-exl3-3bpw",
    "qwen3.8-27b-dflash2-exl3-3bpw",
    "qwen3.8-27b-dflash2-source",
    "draft-conversion-work",
)
RETIRED_DATA_FOLDERS = {
    **{folder: f"recipes/{EXL3_RECIPE}/{folder}" for folder in EXL3_DATA_FOLDERS},
    "strata": f"recipes/{ISTA_RECIPE}",
    "strata-unsloth": f"recipes/{UNSLOTH_RECIPE}",
}


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
        venv = destination / ".venv"
        created = run_process([sys.executable, "-m", "venv", str(venv)])
        if created.returncode:
            raise RuntimeError(f"venv creation failed: {created.stderr.strip()}")
        installed = run_process(
            [str(venv / "bin/pip"), "install", "--quiet", *RUNTIME_REQUIREMENTS]
        )
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


# ---------------------------------------------------------------- cutover


def move_plan(old_root: Path) -> list[tuple[Path, Path]]:
    """Every move of the cutover, as (source, destination) pairs."""
    moves = [(old_root / name, paths.data_home() / name) for name in SHARED_DIRECTORIES]
    for folder, relative in RETIRED_DATA_FOLDERS.items():
        moves.append((old_root / folder, paths.data_home() / relative))
    return moves


def read_journal(prefix: Path) -> set[str]:
    """Destination paths of moves already completed and journaled."""
    path = prefix / JOURNAL_NAME
    if not path.is_file():
        return set()
    completed = set()
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("done"):
            completed.add(entry["to"])
    return completed


def append_journal(prefix: Path, source: Path, destination: Path) -> None:
    prefix.mkdir(parents=True, exist_ok=True)
    with (prefix / JOURNAL_NAME).open("a") as journal:
        journal.write(
            json.dumps({"from": str(source), "to": str(destination), "done": True}) + "\n"
        )


def nearest_existing(path: Path) -> Path:
    while not path.exists():
        if path.parent == path:
            raise ValueError(f"no existing ancestor for {path}")
        path = path.parent
    return path


def same_device(source_parent: Path, destination_parent: Path) -> bool:
    """True when both paths live on the same filesystem device (rename is safe)."""
    return (
        nearest_existing(source_parent).stat().st_dev
        == nearest_existing(destination_parent).stat().st_dev
    )


def locked_elsewhere(old_root: Path) -> bool:
    return (old_root / ".prepare.lock").exists()


def post_check(app: Path, recipe: str) -> None:
    """Verify lock-referenced paths resolve under the moved recipe data root."""
    lock_path = app / "recipes" / recipe / "config/models.lock.json"
    root = paths.data_home() / "recipes" / recipe
    if not root.is_dir():
        raise ValueError(f"missing recipe data root: {root}")
    if not lock_path.is_file():
        return
    lock = json.loads(lock_path.read_text())
    if recipe == EXL3_RECIPE:
        folders = [
            lock["target"]["directory"],
            lock["draft"]["directory"],
            lock["conversion"]["directory"],
            lock["conversion"]["work_directory"],
        ]
        missing = [name for name in folders if not (root / name).is_dir()]
    else:
        missing = [
            item["path"] for item in lock["files"] if not (root / "models" / item["path"]).is_file()
        ]
    if missing:
        raise ValueError(f"{root}: missing lock-referenced entries: {', '.join(missing)}")


def migrate_data(app: Path, old_root: Path, *, apply: bool) -> int:
    """Move the old data root into the data home; dry-run unless ``apply``."""
    prefix = paths.runtime_prefix()
    if not (app / "scripts/launch.py").is_file():
        log(f"refusing: install the runtime snapshot first ({app} is missing)")
        return 1
    if not old_root.is_dir():
        log(f"nothing to migrate: {old_root} does not exist")
        return 0
    if locked_elsewhere(old_root):
        log(f"refusing: a model preparation holds {old_root / '.prepare.lock'}")
        return 1
    if running_instances():
        log("refusing: launcher-managed instances are running; stop them first")
        return 1
    completed = read_journal(prefix)
    moves = move_plan(old_root)
    unmapped = sorted(
        path.name
        for path in old_root.iterdir()
        if path.is_dir()
        and path.name not in {*SHARED_DIRECTORIES, *RETIRED_DATA_FOLDERS}
        and f"{paths.data_home() / path.name}" not in completed
    )
    if unmapped:
        log(f"refusing: unmapped directories under {old_root}: {', '.join(unmapped)}")
        return 1
    for source, destination in moves:
        key = str(destination)
        if key in completed:
            log(f"skip (journaled): {source} -> {destination}")
            continue
        if not source.exists():
            log(f"skip (absent): {source}")
            continue
        if destination.exists():
            log(f"refusing: destination already exists: {destination}")
            return 1
        if not same_device(source.parent, destination.parent):
            log(f"refusing: cross-device move for {source}; move it manually")
            return 1
    for source, destination in moves:
        if str(destination) in completed or not source.exists():
            continue
        if not apply:
            log(f"move: {source} -> {destination}")
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.rename(source, destination)
        append_journal(prefix, source, destination)
        log(f"moved: {source} -> {destination}")
    if not apply:
        log("dry run only; pass --apply to perform the moves above")
        return 0
    for recipe in (EXL3_RECIPE, ISTA_RECIPE, UNSLOTH_RECIPE):
        try:
            post_check(app, recipe)
        except ValueError as error:
            log(f"post-check FAILED: {error}")
            log(f"journal for reverse application: {prefix / JOURNAL_NAME}")
            return 1
    leftover = sorted(entry.name for entry in old_root.iterdir()) if old_root.exists() else []
    if leftover:
        log(f"old root not empty, keeping it: {old_root} ({', '.join(leftover)})")
    else:
        old_root.rmdir()
        log(f"removed empty {old_root}")
        models = old_root.parent
        if models.is_dir() and not any(models.iterdir()):
            models.rmdir()
            log(f"removed empty {models}")
    for recipe_folder in sorted((app / "recipes").iterdir()):
        diagnosis = run_process(
            [
                sys.executable,
                str(app / "scripts/launch.py"),
                "doctor",
                recipe_folder.name,
                "--models",
                str(paths.data_home()),
            ]
        )
        log(f"doctor {recipe_folder.name}:")
        log(diagnosis.stdout.strip() or diagnosis.stderr.strip() or "(no output)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("install", help="copy the runtime snapshot and refresh shims")
    setup.add_argument("--force", action="store_true", help="swap even while instances run")
    setup.add_argument(
        "--skip-deps", action="store_true", help="skip venv creation (development use)"
    )
    cutover = commands.add_parser("migrate-data", help="move the old data root into the data home")
    cutover.add_argument(
        "--apply", action="store_true", help="perform the moves (default: dry run)"
    )
    args = parser.parse_args(argv)
    prefix = paths.runtime_prefix()
    try:
        if args.command == "install":
            return install(
                repo_root(), prefix, force=args.force, with_dependencies=not args.skip_deps
            )
        return migrate_data(prefix / "app", OLD_DATA_ROOT, apply=args.apply)
    except RuntimeError as error:
        log(f"error: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
