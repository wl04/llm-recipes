#!/usr/bin/env python3
"""Launch prepared recipe images on Linux using the host's Docker installation."""

import argparse
import os
import shlex
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Recipe:
    """Host-side image identity; native engine settings remain in the recipe."""

    name: str
    directory: Path
    image: str
    container: str
    port: int


EXL3 = Recipe(
    "exl3",
    ROOT / "recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram",
    "llm-recipes/exl3-rdna4:probe",
    "llm-recipes-exl3",
    5000,
)
RECIPES = {EXL3.name: EXL3}


def context_tokens(value: str) -> int:
    """Parse a context capacity accepted by the current adapter."""
    if not value.isascii() or not value.isdigit() or len(value) > 9:
        raise argparse.ArgumentTypeError("context must be an integer of at most 9 digits")
    number = int(value)
    if number < 1024 or number % 256:
        raise argparse.ArgumentTypeError("context must be at least 1024 and a multiple of 256")
    return number


def port_number(value: str) -> int:
    """Parse a TCP port without silently accepting a random port allocation."""
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return number


def mount(source: Path, destination: str, readonly: bool = False) -> list[str]:
    """Return a bind mount, rejecting Docker CSV delimiters in host paths."""
    if "," in str(source) or "\n" in str(source):
        raise ValueError(f"Mount path contains a comma or newline: {source}")
    suffix = ",readonly" if readonly else ""
    return ["--mount", f"type=bind,src={source},dst={destination}{suffix}"]


def engine_command(recipe: Recipe, context: int, draft: str, vision: str) -> list[str]:
    """Translate launch options into the recipe's native entry point."""
    if recipe.name != "exl3":
        raise ValueError(f"No serving adapter for {recipe.name}")
    return [
        "python3",
        "/recipe/scripts/serve.py",
        "--draft",
        draft,
        "--vision",
        vision,
        "--context",
        str(context),
    ]


def start_command(
    recipe: Recipe,
    models: Path,
    logs: Path,
    *,
    context: int,
    draft: str,
    vision: str,
    port: int,
    groups: list[int],
    uid: int,
    gid: int,
    detached: bool,
) -> list[str]:
    """Build Docker argv without filesystem changes or shell evaluation."""
    command = ["sudo", "docker", "run", "--rm", "--init", "--name", recipe.container]
    if detached:
        command.append("--detach")
    command += ["--user", f"{uid}:{gid}"]
    for group in sorted(set(groups)):
        command += ["--group-add", str(group)]
    command += [
        "--device=/dev/kfd",
        "--device=/dev/dri",
        "--publish",
        f"127.0.0.1:{port}:{recipe.port}",
    ]
    for setting in (
        "XDG_CACHE_HOME=/cache",
        "HF_HOME=/cache/huggingface",
        "TRITON_CACHE_DIR=/cache/triton",
        "PYTHONUNBUFFERED=1",
    ):
        command += ["--env", setting]
    command += mount(recipe.directory, "/recipe", readonly=True)
    command += mount(models, "/models", readonly=True)
    command += mount(models / ".cache", "/cache")
    command += mount(logs, "/logs")
    return [*command, recipe.image, *engine_command(recipe, context, draft, vision)]


def gpu_groups() -> list[int]:
    """Read AMD device group IDs; fail before launch when devices are absent."""
    kfd = Path("/dev/kfd")
    renders = sorted(Path("/dev/dri").glob("renderD*"))
    if not kfd.exists() or not renders:
        raise ValueError("AMD devices missing: /dev/kfd and /dev/dri/renderD* are required")
    return [node.stat().st_gid for node in [kfd, *renders]]


def parser() -> argparse.ArgumentParser:
    """Construct the common lifecycle CLI and the supported recipe options."""
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="action", required=True)
    commands.add_parser("list", help="list launchable recipes")
    for action in ("start", "status", "logs", "stop"):
        sub = commands.add_parser(action)
        sub.add_argument("recipe", choices=RECIPES)
        if action == "logs":
            sub.add_argument("--follow", action="store_true")
        if action != "start":
            continue
        sub.add_argument("--draft", choices=("on", "off"), default="on")
        sub.add_argument(
            "--vision", choices=("on", "off"), default="off", help="GPU vision on/off for exl3"
        )
        sub.add_argument("--context", type=context_tokens, default=4096)
        sub.add_argument("--models", type=Path, default=Path.home() / "Models/llm-recipes")
        state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
        sub.add_argument("--logs", type=Path, default=state / "llm-recipes/exl3")
        sub.add_argument("--port", type=port_number, default=5000)
        sub.add_argument("--detach", action="store_true")
        sub.add_argument(
            "--dry-run",
            action="store_true",
            help="print command without creating directories or requiring GPU devices",
        )
    return cli


def main() -> None:
    """Validate host inputs, prepare writable mounts, and replace this process."""
    cli = parser()
    args = cli.parse_args()
    if args.action == "list":
        for recipe in RECIPES.values():
            print(f"{recipe.name}: {recipe.directory.name}")
        return
    recipe = RECIPES[args.recipe]
    try:
        if args.action == "start":
            models = args.models.expanduser().resolve()
            logs = args.logs.expanduser().resolve()
            groups = [] if args.dry_run else gpu_groups()
            command = start_command(
                recipe,
                models,
                logs,
                context=args.context,
                draft=args.draft,
                vision=args.vision,
                port=args.port,
                groups=groups,
                uid=os.getuid(),
                gid=os.getgid(),
                detached=args.detach,
            )
            if args.dry_run:
                print("# GPU group IDs are resolved from device nodes at launch.")
                print(shlex.join(command))
                return
            if not models.is_dir():
                raise ValueError(f"Model directory does not exist: {models}")
            (models / ".cache").mkdir(exist_ok=True)
            logs.mkdir(parents=True, exist_ok=True)
            print(f"Persistent logs: {logs}", flush=True)
            print(
                f"API address: http://127.0.0.1:{args.port}/v1 (available after model loading)",
                flush=True,
            )
        elif args.action == "status":
            command = [
                "sudo",
                "docker",
                "inspect",
                "--format",
                "{{.State.Status}}",
                recipe.container,
            ]
        elif args.action == "logs":
            command = ["sudo", "docker", "logs"]
            if args.follow:
                command.append("--follow")
            command.append(recipe.container)
        else:
            command = ["sudo", "docker", "stop", recipe.container]
        os.execvp(command[0], command)
    except (OSError, ValueError) as error:
        cli.exit(1, f"launch: {error}\n")


if __name__ == "__main__":
    main()
