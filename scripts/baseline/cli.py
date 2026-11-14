"""Command line for the baseline runner: ``run`` a suite against a server, or ``render`` a run."""

import argparse
import json
import platform
import shutil
import signal
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

import generate_configurations as generator
from launcher import Recipe, discover_recipes

from baseline import aggregate, host, monitor, schema, sources, vision, workloads
from baseline.rawlog import RunWriter, read_run
from baseline.runner import RunConfig, Runner
from baseline.sampler import Sampler
from baseline.schema import ExitCode
from baseline.sources import SourceError
from baseline.workloads import SuiteConfig

ROOT = Path(__file__).resolve().parents[2]
SERVER_KINDS = schema.SERVER_KINDS


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run the baseline suite against a running server")
    run.add_argument("recipe", help="Recipe folder name")
    run.add_argument(
        "--output", type=Path, required=True, help="New directory outside the repository"
    )
    run.add_argument("--instance", help="Launcher instance name (container recipes)")
    run.add_argument("--pid", type=int, help="Server process ID (desktop recipes)")
    run.add_argument("--base-url", help="Server URL, with or without /v1")
    run.add_argument("--model", help="Served model ID (default: the only served model)")
    run.add_argument("--context", type=int, help="Actual context length in tokens")
    run.add_argument(
        "--server-kind", choices=SERVER_KINDS, help="API server (default: from recipe)"
    )
    run.add_argument("--gpu-pci", help="GPU PCI address (default: the AMD GPU with most VRAM)")
    run.add_argument("--no-gpu", action="store_true", help="Skip GPU telemetry")
    run.add_argument("--image", type=Path, help="Vision image to use instead of the shared one")
    run.add_argument("--request-extra", help="JSON object merged into every request body")
    render = commands.add_parser("render", help="Render results.json and summary.md for a run")
    render.add_argument("run_dir", type=Path)
    return parser


def _progress(message: str) -> None:
    print(f"[baseline] {message}", file=sys.stderr, flush=True)


def render_run(directory: Path, root: Path = ROOT) -> Path:
    """Write ``results.json`` and the generated block of ``summary.md`` from a run's raw files.

    An existing ``summary.md`` keeps its authored text; a new one starts from the template.

    Raises:
        ValueError: the run directory is unreadable or its records violate the contract.
    """
    document = aggregate.build_results(read_run(directory))
    generator.write_atomic(directory / "results.json", schema.dump_results(document))
    summary = directory / "summary.md"
    if not summary.exists():
        summary.write_text((root / "templates/recipe/baseline-summary.md").read_text())
    path, _, rendered = generator.update_results(directory)
    generator.write_atomic(path, rendered)
    return directory / "results.json"


def _normalize_url(url: str) -> str:
    url = url.rstrip("/")
    return url.removesuffix("/v1").rstrip("/")


def _recipe_kind(recipe: Recipe | None, requested: str | None) -> str:
    if requested:
        return requested
    return recipe.adapter if recipe else "lmstudio"


def _versions() -> dict[str, Any]:
    versions: dict[str, Any] = {"python": platform.python_version(), "kernel": platform.release()}
    executable = shutil.which("amdgpu_top")
    if executable:
        result = host.run_command([executable, "-V"])
        versions["amdgpu_top"] = result.stdout.strip() or "unknown"
    return versions


def _run_command(args: argparse.Namespace, suite: SuiteConfig, root: Path, recipes: Path) -> int:
    if args.output.resolve().is_relative_to(root.resolve()):
        print("--output must be outside the repository", file=sys.stderr)
        return ExitCode.USAGE
    if args.pid is not None and args.instance:
        print("Use --instance or --pid, not both", file=sys.stderr)
        return ExitCode.USAGE
    try:
        found = discover_recipes(recipes)
    except ValueError as error:
        print(f"Recipe discovery failed: {error}", file=sys.stderr)
        return ExitCode.USAGE
    recipe = found.get(args.recipe)
    if recipe is None and not (recipes / args.recipe).is_dir():
        print(f"Unknown recipe: {args.recipe}", file=sys.stderr)
        return ExitCode.USAGE
    base_url = args.base_url or (f"http://127.0.0.1:{recipe.port}" if recipe else None)
    context = args.context or (recipe.context if recipe else None)
    if base_url is None or context is None:
        print("A desktop recipe needs --base-url and --context", file=sys.stderr)
        return ExitCode.USAGE
    extra: dict[str, Any] = {}
    if args.request_extra:
        try:
            extra = json.loads(args.request_extra)
        except json.JSONDecodeError:
            extra = {}
        if not isinstance(extra, dict) or not extra:
            print("--request-extra must be a non-empty JSON object", file=sys.stderr)
            return ExitCode.USAGE
    kind = _recipe_kind(recipe, args.server_kind)
    expectations_path = root / "assets/checks/amdgpu-top.expected.json"
    try:
        expectations = vision.load_expectations(expectations_path)
        corpus = workloads.load_corpus(workloads.default_corpus_directory())
        writer = RunWriter(args.output)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return ExitCode.USAGE
    try:
        gpu_address, candidates = (None, []) if args.no_gpu else _find_gpu(args.gpu_pci)
        container = host.resolve_container(args.instance) if args.instance else None
        monitoring = monitor.build_monitoring(
            cgroup=container.cgroup if container else None,
            pid=args.pid,
            gpu_address=gpu_address,
            interval_ms=int(suite.sample_interval_s * 1000),
            top_executable=shutil.which("amdgpu_top"),
        )
    except (host.HostError, SourceError) as error:
        print(f"Preflight failed: {error}", file=sys.stderr)
        return ExitCode.PREFLIGHT_FAILED
    gpu_device = Path("/sys/bus/pci/devices") / gpu_address if gpu_address else None
    meta_extra: dict[str, Any] = {
        "boot": host.boot_state(Path("/proc"), gpu_device),
        "host": {"revision": host.repository_revision(root), **_versions()},
        "workload": {"image": str(args.image or "assets/checks/amdgpu-top.png")},
        "gpu": {"address": gpu_address, "candidates": candidates},
    }
    if container:
        meta_extra["container"] = {
            "id": container.container_id,
            "image": container.image,
            "image_id": container.image_id,
        }
    if recipe is None:
        meta_extra["desktop"] = {"pid": args.pid}
    image = args.image or root / "assets/checks/amdgpu-top.png"
    config = RunConfig(
        recipe=args.recipe,
        kind=kind,
        base_url=_normalize_url(base_url),
        model=args.model,
        context_tokens=context,
        suite=suite,
        corpus=corpus,
        run_id=uuid.uuid4().hex[:8],
        expectations=expectations,
        image=image,
        image_is_default=args.image is None,
        request_extra=extra,
        target=monitoring.target,
        meta_extra=meta_extra,
    )
    sampler = Sampler(monitoring.sources, suite.sample_interval_s, writer.append_sample)
    stop = threading.Event()
    runner = Runner(
        config, writer, sampler, stop=stop, progress=_progress, cleanup=monitoring.cleanup
    )
    if recipe is not None and not args.instance and args.pid is None:
        _progress("No --instance given: container CPU and memory will be unavailable")
    previous = signal.signal(signal.SIGTERM, _terminate)
    try:
        code = runner.run()
    finally:
        signal.signal(signal.SIGTERM, previous)
    try:
        results = render_run(writer.directory, root)
    except ValueError as error:
        print(f"The run was recorded but could not be rendered: {error}", file=sys.stderr)
        return code if code != ExitCode.OK else ExitCode.CHECKS_FAILED
    print(f"Baseline written to {writer.directory} (results: {results.name}, summary.md)")
    return code


def _terminate(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


def _find_gpu(requested: str | None) -> tuple[str | None, list[str]]:
    if requested:
        return requested, [requested]
    try:
        return sources.find_gpu()
    except SourceError as error:
        _progress(f"GPU telemetry disabled: {error}")
        return None, []


def main(
    argv: list[str] | None = None,
    *,
    suite: SuiteConfig | None = None,
    root: Path = ROOT,
    recipes: Path | None = None,
) -> int:
    """Run the command line; ``suite`` and ``recipes`` are overridden by tests."""
    args = _parser().parse_args(argv)
    if args.command == "render":
        try:
            results = render_run(args.run_dir, root)
        except (OSError, ValueError) as error:
            print(f"Cannot render {args.run_dir}: {error}", file=sys.stderr)
            return ExitCode.USAGE
        print(f"Rendered {results} and summary.md")
        return ExitCode.OK
    return _run_command(args, suite or SuiteConfig(), root, recipes or root / "recipes")
