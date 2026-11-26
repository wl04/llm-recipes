#!/usr/bin/env python3
"""Launch prepared recipes and manage their named instances."""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import paths
from doctor import diagnose
from launcher import (
    Recipe,
    dashboard_url,
    discover_recipes,
    gpu_groups,
    instances_command,
    lifecycle_command,
    parse_instances,
    prepare_start,
    refresh_sudo_ticket,
    resolve_launch_options,
    run_command,
    running_command,
    select_image,
    start_command,
    start_with_facts,
    status_query_command,
)

ROOT = Path(__file__).resolve().parents[1]


def capture(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a command quietly; JSON callers surface stderr themselves."""
    return subprocess.run(command, check=False, capture_output=True, text=True)


def parser() -> argparse.ArgumentParser:
    """Define the CLI without requiring recipe files or Docker access."""
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="action", required=True)
    commands.add_parser("tui", help="open the terminal dashboard")
    list_command = commands.add_parser(
        "list", help="list recipes and their selected runtime images"
    )
    list_command.add_argument("--json", action="store_true", help="machine-readable output")
    ps_command = commands.add_parser("ps", help="list running launcher instances")
    ps_command.add_argument("--json", action="store_true", help="machine-readable output")
    doctor = commands.add_parser("doctor", help="read-only host and recipe diagnostics")
    doctor.add_argument("--json", action="store_true", help="machine-readable output")
    doctor.add_argument("recipe", help="recipe directory name; see list")
    doctor.add_argument("--models", type=Path, default=paths.data_home())
    doctor.add_argument("--runtime-image", help="Use a local image with the selected runtime lock")
    start = commands.add_parser("start")
    start.add_argument("recipe", help="recipe directory name; see list")
    start.add_argument("--name", help="instance name (default: recipe directory name)")
    start.add_argument("--draft", choices=("on", "off"))
    start.add_argument(
        "--vision", choices=("on", "off", "cpu"), help="TabbyAPI: on/off; Strata: cpu/off"
    )
    start.add_argument(
        "--api-monitor", action="store_true", help="enable the Strata API request monitor"
    )
    start.add_argument("--context", type=int)
    start.add_argument("--port", type=int)
    start.add_argument("--models", type=Path, default=paths.data_home())
    start.add_argument("--runtime-image", help="Use a local image with the selected runtime lock")
    start.add_argument(
        "--logs", type=Path, help="persistent directory (default: <models root>/logs/<instance>)"
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


def _ps(args: argparse.Namespace) -> int:
    """List running launcher instances as a table or as JSON."""
    refresh_sudo_ticket()
    if not args.json:
        return run_command(running_command())
    listing = capture(instances_command())
    if listing.returncode:
        sys.stderr.write(listing.stderr)
        return listing.returncode
    print(json.dumps(parse_instances(listing.stdout), indent=2))
    return 0


def _status(args: argparse.Namespace) -> int:
    """Report one instance as JSON without a Docker table."""
    command = status_query_command(args.instance)
    error = None
    status = "error"
    try:
        refresh_sudo_ticket()
        inspection = capture(command)
        if inspection.returncode:
            error = inspection.stderr.strip() or "Docker status query failed"
        else:
            status = inspection.stdout.strip() or "not-found"
            if status not in {
                "not-found",
                "created",
                "running",
                "paused",
                "restarting",
                "removing",
                "exited",
                "dead",
            }:
                error = f"Unexpected Docker container state: {status!r}"
    except (OSError, ValueError, subprocess.SubprocessError) as failure:
        error = str(failure) or type(failure).__name__
    result = {"instance": args.instance, "status": "error" if error else status}
    if error:
        result["error"] = error
    print(json.dumps(result, indent=2))
    return 1 if error else 0


def _lifecycle(args: argparse.Namespace) -> int:
    """Run ``status``, ``logs``, or ``stop`` as a Docker command."""
    refresh_sudo_ticket()
    return run_command(
        lifecycle_command(args.action, args.instance, getattr(args, "follow", False))
    )


def _list(recipes: dict[str, Recipe], args: argparse.Namespace) -> int:
    """Print available recipes as a table or as JSON."""
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "name": recipe.name,
                        "runtime": recipe.runtime,
                        "adapter": recipe.adapter,
                        "engine": recipe.engine,
                        "engine_version": recipe.engine_version,
                        "engine_source_version": recipe.engine_source_version,
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
    if not recipes:
        print("No launchable recipes found.")
        return 0

    headers = ("RECIPE", "API SERVER", "ENGINE", "PORT", "SELECTED IMAGE")
    rows = []
    for recipe in recipes.values():
        version = recipe.engine_source_version or recipe.engine_version
        engine = f"{recipe.engine} {version}" if version else recipe.engine
        rows.append((recipe.name, recipe.adapter, engine, str(recipe.port), recipe.image))

    width = shutil.get_terminal_size().columns
    widths = [max(map(len, column)) for column in zip(headers, *rows, strict=True)]
    if sum(widths) + 2 * (len(headers) - 1) <= width:
        for row in [headers, *rows]:
            print(
                "  ".join(
                    value.ljust(size) for value, size in zip(row, widths, strict=True)
                ).rstrip()
            )
    else:
        for index, (name, adapter, engine, port, image) in enumerate(rows):
            if index:
                print()
            for line in (
                name,
                f"  API server: {adapter}    Engine: {engine}    Port: {port}",
                f"  Image: {image}",
            ):
                print(textwrap.fill(line, width=width, break_on_hyphens=False))
    return 0


def _doctor(recipe: Recipe, args: argparse.Namespace) -> int:
    """Print read-only diagnostics; the exit status reports whether any check failed."""
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
    else:
        for item in findings:
            print(f"{item.status}: {item.name}: {item.detail}")
        print(
            "Checks use recipe defaults. No GPU execution, image build-pin inspection, "
            "or weight rehashing performed."
        )
    return int(any(item.status == "FAIL" for item in findings))


def _start(recipe: Recipe, args: argparse.Namespace) -> int:
    """Validate the launch plan, then start the container after the host is prepared."""
    name = args.name if args.name is not None else recipe.name
    models = args.models.expanduser().resolve()
    options = resolve_launch_options(
        recipe,
        name=name,
        models=models,
        logs=(args.logs if args.logs is not None else paths.logs_dir(models, name))
        .expanduser()
        .resolve(),
        context=args.context,
        draft=args.draft,
        vision=args.vision,
        port=args.port,
        detached=args.detach,
        api_monitor=args.api_monitor,
    )
    uid, gid = os.getuid(), os.getgid()
    # Validate the plan before host-device access or directory creation.
    command = start_command(recipe, options, groups=[], uid=uid, gid=gid)
    if args.dry_run:
        print("# GPU group IDs are resolved from device nodes at launch.")
        print(shlex.join(command))
        return 0
    command = start_command(recipe, options, groups=gpu_groups(), uid=uid, gid=gid)
    prepare_start(recipe, options)
    refresh_sudo_ticket()
    print(f"Instance: {name}\nPersistent logs: {options.logs}", flush=True)
    print(f"API address: http://127.0.0.1:{options.port}/v1 (after model loading)", flush=True)
    print(f"Dashboard: {dashboard_url(recipe.adapter, options.port)}", flush=True)
    if options.api_monitor:
        print(f"Request monitor: http://127.0.0.1:{options.port}/api-monitor", flush=True)
    status, warning = start_with_facts(recipe, options, command, run_command)
    if warning:
        print(warning, file=sys.stderr)
    return status


def main(argv: list[str] | None = None) -> int:
    """Resolve CLI inputs and invoke reusable launch operations."""
    cli = parser()
    args = cli.parse_args(argv)
    try:
        if args.action == "tui":
            from tui import main as run_tui

            return run_tui()
        if args.action == "ps":
            return _ps(args)
        if args.action == "status" and args.json:
            return _status(args)
        if args.action not in ("start", "list", "doctor"):
            return _lifecycle(args)
        recipes = discover_recipes(ROOT / "recipes")
        if args.action == "list":
            return _list(recipes, args)
        if args.recipe not in recipes:
            raise ValueError(f"Unknown recipe: {args.recipe}. Use 'list' to see available recipes.")
        recipe = select_image(recipes[args.recipe], args.runtime_image)
        if args.action == "doctor":
            return _doctor(recipe, args)
        return _start(recipe, args)
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
