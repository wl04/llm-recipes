#!/usr/bin/env python3
"""Launch prepared recipes and manage their named instances."""

import argparse
import os
import shlex
from pathlib import Path

from launcher import (
    LaunchOptions,
    discover_recipes,
    gpu_groups,
    lifecycle_command,
    prepare_start,
    run_command,
    running_command,
    start_command,
)

ROOT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    """Define the CLI without requiring recipe files or Docker access."""
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="action", required=True)
    commands.add_parser("list", help="list available recipes")
    commands.add_parser("ps", help="list running launcher instances")
    start = commands.add_parser("start")
    start.add_argument("recipe", help="recipe directory name; see list")
    start.add_argument("--name", help="instance name (default: recipe directory name)")
    start.add_argument("--draft", choices=("on", "off"))
    start.add_argument(
        "--vision", choices=("on", "off", "cpu"), help="TabbyAPI: on/off; Strata: cpu/off"
    )
    start.add_argument("--context", type=int)
    start.add_argument("--port", type=int)
    start.add_argument("--models", type=Path, default=Path.home() / "Models/llm-recipes")
    start.add_argument(
        "--logs", type=Path, help="persistent directory (default: per-instance state)"
    )
    start.add_argument("--detach", action="store_true")
    start.add_argument("--dry-run", action="store_true")
    for action in ("status", "logs", "stop"):
        sub = commands.add_parser(action)
        sub.add_argument("instance")
        if action == "logs":
            sub.add_argument("--follow", action="store_true")
    return cli


def main() -> int:
    """Resolve CLI inputs and invoke reusable launch operations."""
    cli = parser()
    args = cli.parse_args()
    try:
        if args.action == "ps":
            return run_command(running_command())
        if args.action != "start" and args.action != "list":
            return run_command(
                lifecycle_command(
                    args.action,
                    args.instance,
                    getattr(args, "follow", False),
                )
            )
        recipes = discover_recipes(ROOT / "recipes")
        if args.action == "list":
            print("RECIPE  |  API SERVER  |  ENGINE  |  PORT")
            for recipe in recipes.values():
                print(f"{recipe.name}  |  {recipe.adapter}  |  {recipe.engine}  |  {recipe.port}")
            return 0
        if args.recipe not in recipes:
            raise ValueError(f"Unknown recipe: {args.recipe}. Use 'list' to see available recipes.")
        recipe = recipes[args.recipe]
        name = args.name if args.name is not None else recipe.name
        state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
        options = LaunchOptions(
            name,
            args.models.expanduser().resolve(),
            (args.logs if args.logs is not None else state / "llm-recipes" / name)
            .expanduser()
            .resolve(),
            recipe.context if args.context is None else args.context,
            recipe.draft if args.draft is None else args.draft,
            recipe.vision if args.vision is None else args.vision,
            recipe.port if args.port is None else args.port,
            args.detach,
        )
        # Validate the plan before host-device access or directory creation.
        command = start_command(recipe, options, groups=[], uid=os.getuid(), gid=os.getgid())
        if args.dry_run:
            print("# GPU group IDs are resolved from device nodes at launch.")
            print(shlex.join(command))
            return 0
        groups = gpu_groups()
        command = start_command(recipe, options, groups=groups, uid=os.getuid(), gid=os.getgid())
        prepare_start(recipe, options)
        print(f"Instance: {name}\nPersistent logs: {options.logs}", flush=True)
        print(f"API address: http://127.0.0.1:{options.port}/v1 (after model loading)", flush=True)
        return run_command(command)
    except ValueError as error:
        cli.error(str(error))
    except OSError as error:
        cli.exit(1, f"launch: {error}\n")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
