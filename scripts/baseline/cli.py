"""Command line for the baseline runner: ``run`` a suite against a recipe, or ``render`` a run.

Container recipes are started and stopped by the runner. Desktop recipes still need the app to be
running; their guided mode is not available yet.
"""

import argparse
import json
import platform
import signal
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import generate_configurations as generator
from launcher import Recipe, discover_recipes, resolve_launch_options

from baseline import aggregate, host, lifecycle, monitor, schema, sources, vision, workloads
from baseline.lifecycle import ContainerControl
from baseline.rawlog import RunWriter, read_run
from baseline.runner import RunConfig, Runner, ServerControl
from baseline.sampler import Sampler
from baseline.schema import ExitCode
from baseline.sources import SourceError
from baseline.workloads import SuiteConfig

ROOT = Path(__file__).resolve().parents[2]
SERVER_KINDS = schema.SERVER_KINDS
GIB = 1024**3
DEFAULT_MODELS = Path.home() / "Models/llm-recipes"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Record one baseline for a recipe")
    run.add_argument("recipe", help="Recipe folder name")
    run.add_argument(
        "--output",
        type=Path,
        help="New directory outside the repository (default: <models>/baselines/<recipe>/<time>)",
    )
    run.add_argument("--models", type=Path, default=DEFAULT_MODELS, help="Model directory")
    run.add_argument("--context", type=int, help="Context length (default: the recipe's)")
    run.add_argument("--draft", choices=("on", "off"), help="Drafting (default: the recipe's)")
    run.add_argument(
        "--vision", choices=("on", "off", "cpu"), help="Vision (default: the recipe's)"
    )
    run.add_argument("--port", type=int, help="Host port (default: the recipe's)")
    run.add_argument(
        "--keep-running", action="store_true", help="Do not stop the server afterwards"
    )
    run.add_argument("--model", help="Served model ID (default: the only served model)")
    run.add_argument("--gpu-pci", help="GPU PCI address (default: the AMD GPU with most VRAM)")
    run.add_argument("--no-gpu", action="store_true", help="Skip GPU telemetry")
    run.add_argument("--image", type=Path, help="Vision image to use instead of the shared one")
    run.add_argument("--request-extra", help="JSON object merged into every request body")
    desktop = run.add_argument_group("desktop recipes (the app must already be running)")
    desktop.add_argument("--base-url", help="Server URL, with or without /v1")
    desktop.add_argument("--pid", type=int, help="Any process ID of the app")
    desktop.add_argument(
        "--server-kind", choices=SERVER_KINDS, help="API server (default: lmstudio)"
    )
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


def default_output(models: Path, recipe: str, now: datetime | None = None) -> Path:
    """Where a run is written when ``--output`` is not given."""
    stamp = (now or datetime.now()).strftime("%Y-%m-%d-%H%M")
    return models.expanduser() / "baselines" / recipe / stamp


def _normalize_url(url: str) -> str:
    return url.rstrip("/").removesuffix("/v1").rstrip("/")


@dataclass
class Plan:
    """What a run needs from its recipe: where the server is and how it is controlled."""

    kind: str
    base_url: str
    context: int
    control: ServerControl | None
    monitoring: monitor.Monitoring
    meta_extra: dict[str, Any] = field(default_factory=dict)


def _find_gpu(requested: str | None) -> tuple[str | None, list[str]]:
    if requested:
        return requested, [requested]
    try:
        return sources.find_gpu()
    except SourceError as error:
        _progress(f"GPU telemetry disabled: {error}")
        return None, []


def _check_scope(cgroup: Path) -> None:
    """Say what a desktop app's cgroup contains, so shared scopes are noticed."""
    names = sorted({_comm(pid) for pid in sources.cgroup_pids(cgroup)})
    _progress(f"Measuring cgroup {cgroup.name}: {', '.join(names) or 'no readable processes'}")
    if not cgroup.name.startswith(("app-", "docker-")):
        _progress(
            "Warning: the server is not in its own application scope; CPU and memory "
            "include everything in that cgroup"
        )


def _comm(pid: int) -> str:
    try:
        return (Path("/proc") / str(pid) / "comm").read_text().strip()
    except OSError:
        return str(pid)


def _gpu_vram_gib(gpu_address: str | None) -> float | None:
    if gpu_address is None:
        return None
    used = sources.read_gpu(Path("/sys/bus/pci/devices") / gpu_address).values.get("vram_bytes")
    return None if used is None else used / GIB


def _managed_plan(
    args: argparse.Namespace, recipe: Recipe, writer: RunWriter, gpu_address: str | None
) -> Plan:
    """A container recipe: the runner starts the server through the launcher and stops it."""
    models = args.models.expanduser().resolve()
    options = resolve_launch_options(
        recipe,
        name=lifecycle.INSTANCE,
        models=models,
        logs=writer.directory / "server-logs",
        context=args.context,
        draft=args.draft,
        vision=args.vision,
        port=args.port,
        detached=True,
    )
    control = ContainerControl(recipe, options, gpu_vram_gib=lambda: _gpu_vram_gib(gpu_address))
    launch = {
        "context": options.context,
        "draft": options.draft,
        "vision": options.vision,
        "port": options.port,
        "models": str(models),
    }
    return Plan(
        kind=recipe.adapter,
        base_url=f"http://127.0.0.1:{options.port}",
        context=options.context,
        control=control,
        monitoring=monitor.build_monitoring(cgroup=None, gpu_address=gpu_address),
        meta_extra={"launch": launch},
    )


def _attached_plan(
    args: argparse.Namespace, recipe: Recipe | None, gpu_address: str | None
) -> Plan:
    """A desktop recipe: the app is already running with its model loaded and server started."""
    if args.base_url is None or args.context is None:
        raise ValueError("A desktop recipe needs --base-url and --context")
    cgroup = None
    if args.pid is not None:
        cgroup = host.cgroup_path_of(args.pid)
        _check_scope(cgroup)
    monitoring = monitor.build_monitoring(cgroup=cgroup, gpu_address=gpu_address)
    return Plan(
        kind=args.server_kind or "lmstudio",
        base_url=_normalize_url(args.base_url),
        context=args.context,
        control=None,
        monitoring=monitoring,
        meta_extra={"desktop": {"pid": args.pid}},
    )


def _run_command(args: argparse.Namespace, suite: SuiteConfig, root: Path, recipes: Path) -> int:
    try:
        found = discover_recipes(recipes)
    except ValueError as error:
        print(f"Recipe discovery failed: {error}", file=sys.stderr)
        return ExitCode.USAGE
    recipe = found.get(args.recipe)
    if recipe is None and not (recipes / args.recipe).is_dir():
        print(f"Unknown recipe: {args.recipe}", file=sys.stderr)
        return ExitCode.USAGE
    if recipe is not None and (args.pid is not None or args.base_url):
        print(
            "Container recipes are started by the runner; --pid and --base-url are for desktop "
            "recipes",
            file=sys.stderr,
        )
        return ExitCode.USAGE
    output = args.output or default_output(args.models, args.recipe)
    if output.resolve().is_relative_to(root.resolve()):
        print("--output must be outside the repository", file=sys.stderr)
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
    try:
        expectations = vision.load_expectations(root / "assets/checks/amdgpu-top.expected.json")
        corpus = workloads.load_corpus(workloads.default_corpus_directory())
        writer = RunWriter(output)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return ExitCode.USAGE
    try:
        gpu_address, candidates = (None, []) if args.no_gpu else _find_gpu(args.gpu_pci)
        plan = (
            _managed_plan(args, recipe, writer, gpu_address)
            if recipe is not None
            else _attached_plan(args, recipe, gpu_address)
        )
    except (host.HostError, SourceError, ValueError) as error:
        print(f"Preflight failed: {error}", file=sys.stderr)
        return ExitCode.PREFLIGHT_FAILED if not isinstance(error, ValueError) else ExitCode.USAGE
    gpu_device = Path("/sys/bus/pci/devices") / gpu_address if gpu_address else None
    meta_extra: dict[str, Any] = {
        "boot": host.boot_state(Path("/proc"), gpu_device),
        "host": {
            "revision": host.repository_revision(root),
            "python": platform.python_version(),
            "kernel": platform.release(),
        },
        "workload": {"image": str(args.image or "assets/checks/amdgpu-top.png")},
        "gpu": {"address": gpu_address, "candidates": candidates},
        **plan.meta_extra,
    }
    config = RunConfig(
        recipe=args.recipe,
        kind=plan.kind,
        base_url=plan.base_url,
        model=args.model,
        context_tokens=plan.context,
        suite=suite,
        corpus=corpus,
        run_id=uuid.uuid4().hex[:8],
        expectations=expectations,
        image=args.image or root / "assets/checks/amdgpu-top.png",
        image_is_default=args.image is None,
        request_extra=extra,
        target=plan.monitoring.target,
        meta_extra=meta_extra,
        gpu_address=gpu_address,
        keep_running=args.keep_running,
    )
    sampler = Sampler(plan.monitoring.sources, suite.sample_interval_s, writer.append_sample)
    runner = Runner(
        config,
        writer,
        sampler,
        stop=threading.Event(),
        progress=_progress,
        control=plan.control,
    )
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
    outcome = read_run(writer.directory).meta
    status = outcome["run"]["status"]
    for problem in [outcome["run"].get("error"), *outcome.get("problems", [])]:
        if problem:
            _progress(f"Problem: {problem}")
    if status == "complete":
        print(f"Baseline written to {writer.directory} (results: {results.name}, summary.md)")
    else:
        print(f"Baseline {status}; partial output in {writer.directory}")
    return code


def _terminate(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


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
