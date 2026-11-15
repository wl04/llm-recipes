#!/usr/bin/env python3
"""Launch prepared recipes and manage their named instances."""

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import host_facts
from doctor import diagnose
from launcher import (
    FACTS_NAME,
    LaunchOptions,
    Recipe,
    discover_recipes,
    gpu_groups,
    image_inspect_command,
    instances_command,
    lifecycle_command,
    parse_image_inspect,
    parse_instances,
    prepare_start,
    refresh_sudo_ticket,
    resolve_launch_options,
    run_command,
    running_command,
    start_command,
    start_facts,
    write_json_atomic,
)

ROOT = Path(__file__).resolve().parents[1]


def capture(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a command quietly; JSON callers surface stderr themselves."""
    return subprocess.run(command, check=False, capture_output=True, text=True)


def write_start_facts(recipe: Recipe, options: LaunchOptions) -> None:
    """Record the instance ``facts.json``: effective options, image digest, hashes, host.

    Written before the container runs so both foreground and detached starts record it.
    Raises OSError, ValueError, or host/subprocess errors when a fact is unavailable.
    """
    inspection = capture(image_inspect_command(recipe.image))
    if inspection.returncode:
        raise ValueError((inspection.stderr.strip() or "docker image inspect failed")[:200])
    facts = start_facts(
        recipe,
        options,
        host=host_facts.collect(),
        image=parse_image_inspect(inspection.stdout),
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    write_json_atomic(options.logs / FACTS_NAME, facts)


def parser() -> argparse.ArgumentParser:
    """Define the CLI without requiring recipe files or Docker access."""
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="action", required=True)
    list_command = commands.add_parser("list", help="list available recipes")
    list_command.add_argument("--json", action="store_true", help="machine-readable output")
    ps_command = commands.add_parser("ps", help="list running launcher instances")
    ps_command.add_argument("--json", action="store_true", help="machine-readable output")
    doctor = commands.add_parser("doctor", help="read-only host and recipe diagnostics")
    doctor.add_argument("--json", action="store_true", help="machine-readable output")
    doctor.add_argument("recipe", help="recipe directory name; see list")
    doctor.add_argument("--models", type=Path, default=Path.home() / "Models/llm-recipes")
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
        if action == "status":
            sub.add_argument("--json", action="store_true", help="machine-readable output")
        if action == "logs":
            sub.add_argument("--follow", action="store_true")
    return cli


def main(argv: list[str] | None = None) -> int:
    """Resolve CLI inputs and invoke reusable launch operations."""
    cli = parser()
    args = cli.parse_args(argv)
    try:
        if args.action == "ps":
            refresh_sudo_ticket()
            if args.json:
                listing = capture(instances_command())
                if listing.returncode:
                    sys.stderr.write(listing.stderr)
                    return listing.returncode
                print(json.dumps(parse_instances(listing.stdout), indent=2))
                return 0
            return run_command(running_command())
        if args.action == "status" and args.json:
            refresh_sudo_ticket()
            inspection = capture(lifecycle_command("status", args.instance))
            status = inspection.stdout.strip() or "not-found"
            print(json.dumps({"instance": args.instance, "status": status}, indent=2))
            return 0
        if args.action not in ("start", "list", "doctor"):
            refresh_sudo_ticket()
            return run_command(
                lifecycle_command(
                    args.action,
                    args.instance,
                    getattr(args, "follow", False),
                )
            )
        recipes = discover_recipes(ROOT / "recipes")
        if args.action == "list":
            if args.json:
                print(
                    json.dumps(
                        [
                            {
                                "name": recipe.name,
                                "runtime": recipe.runtime,
                                "adapter": recipe.adapter,
                                "engine": recipe.engine,
                                "image": recipe.image,
                                "port": recipe.port,
                                "context": recipe.context,
                            }
                            for recipe in recipes.values()
                        ],
                        indent=2,
                    )
                )
                return 0
            print("RECIPE  |  API SERVER  |  ENGINE  |  PORT")
            for recipe in recipes.values():
                print(f"{recipe.name}  |  {recipe.adapter}  |  {recipe.engine}  |  {recipe.port}")
            return 0
        if args.recipe not in recipes:
            raise ValueError(f"Unknown recipe: {args.recipe}. Use 'list' to see available recipes.")
        recipe = recipes[args.recipe]
        if args.action == "doctor":
            findings = diagnose(recipe, args.models.expanduser().resolve())
            if args.json:
                print(
                    json.dumps(
                        [
                            {"status": item.status, "name": item.name, "detail": item.detail}
                            for item in findings
                        ],
                        indent=2,
                    )
                )
                return int(any(item.status == "FAIL" for item in findings))
            for item in findings:
                print(f"{item.status}: {item.name}: {item.detail}")
            print(
                "Checks use recipe defaults. No GPU execution, image build-pin inspection, "
                "or weight rehashing performed."
            )
            return int(any(item.status == "FAIL" for item in findings))
        name = args.name if args.name is not None else recipe.name
        state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
        options = resolve_launch_options(
            recipe,
            name=name,
            models=args.models.expanduser().resolve(),
            logs=(args.logs if args.logs is not None else state / "llm-recipes" / name)
            .expanduser()
            .resolve(),
            context=args.context,
            draft=args.draft,
            vision=args.vision,
            port=args.port,
            detached=args.detach,
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
        refresh_sudo_ticket()
        try:
            write_start_facts(recipe, options)
        except (
            OSError,
            ValueError,
            subprocess.SubprocessError,
            host_facts.HostFactsError,
        ) as error:
            print(f"warning: {FACTS_NAME} was not written: {error}", file=sys.stderr)
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
