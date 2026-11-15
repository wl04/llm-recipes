"""Command line for the baseline runner: ``run`` a suite against a recipe, or ``render`` a run.

Container recipes are started and stopped by the runner. Desktop recipes need the app to
be running; without ``--base-url``/``--context`` the run is set up by the guided interview.
"""

import argparse
import json
import platform
import shutil
import signal
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import generate_configurations as generator
import host_facts
import paths
import yaml
from launcher import (
    Recipe,
    discover_recipes,
    record_start_facts,
    refresh_sudo_ticket,
    resolve_launch_options,
)

from baseline import (
    aggregate,
    api,
    guided,
    host,
    importer,
    lifecycle,
    monitor,
    report,
    schema,
    session,
    sources,
    vision,
    workloads,
)
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
DEFAULT_MODELS = paths.data_home()


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
    desktop.add_argument(
        "--yes",
        action="store_true",
        help="with a guided setup, accept every determinable default",
    )
    render = commands.add_parser("render", help="Render results.json and summary.md for a run")
    render.add_argument("run_dir", type=Path)
    import_command = commands.add_parser(
        "import",
        help="Create a repository experiment folder from a completed run directory",
    )
    import_command.add_argument("run_dir", type=Path)
    import_command.add_argument(
        "--suffix",
        help="Append a lowercase-hyphen slug to the experiment folder name",
    )
    session_command = commands.add_parser(
        "session",
        help="Aggregate a coding session from an instance's server logs",
    )
    target = session_command.add_mutually_exclusive_group()
    target.add_argument("instance", nargs="?", help="Instance name (launcher log directory)")
    target.add_argument("--logs", type=Path, help="Directory of engine .log files to read")
    session_command.add_argument("--since", help="ISO timestamp lower bound (timestamped logs)")
    session_command.add_argument("--until", help="ISO timestamp upper bound (timestamped logs)")
    session_command.add_argument(
        "--experiment",
        type=Path,
        help="Experiment folder to update: session-results.json, summary block, profile.yaml",
    )
    session_command.add_argument(
        "--create",
        metavar="DESCRIPTION",
        help="Create the next numbered experiment folder NNN-DATE-DESCRIPTION for the "
        "instance's recipe from the templates, then fill it (requires an instance)",
    )
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
    path, _, rendered = generator.update_results_block(directory)
    generator.write_atomic(path, rendered)
    return directory / "results.json"


def create_session_folder(
    root: Path, recipe: str, description: str, log_dir: Path, now: datetime | None = None
) -> Path:
    """Create a session experiment folder from the recipe templates; return its path.

    The folder is the recipe's next free ``NNN-date-description``; the date comes
    from the instance's ``facts.json`` when readable, else from ``now``. ``summary.md``
    is the session scaffold with its title line already set, and ``configuration.md``
    is the generic template; ``profile.yaml`` is deliberately left uncreated so that
    the session command seeds it from the run.

    Raises:
        ValueError: the description is not a lowercase-hyphen slug, or the recipe
            folder does not exist in the repository.
    """
    if not importer.SUFFIX_RULE.fullmatch(description):
        raise ValueError(f"{description}: use a lowercase-hyphen slug, like coding-session")
    recipe_dir = root / "recipes" / recipe
    if not recipe_dir.is_dir():
        raise ValueError(f"{recipe}: not a recipe folder under {root / 'recipes'}")
    facts_path = log_dir / "facts.json"
    date = ""
    if facts_path.is_file():
        started = importer.read_json(facts_path).get("started_at")
        date = started[:10] if isinstance(started, str) else ""
    date = date or (now or datetime.now()).strftime("%Y-%m-%d")
    numbers = [
        int(match[1])
        for child in recipe_dir.iterdir()
        if child.is_dir() and (match := importer.FOLDER_NUMBER.match(child.name))
    ]
    number = max(numbers) + 1 if numbers else 1
    while (experiment := recipe_dir / f"{number:03d}-{date}-{description}").exists():
        number += 1
    template = root / "templates/recipe"
    experiment.mkdir()
    summary_lines = (template / "session-summary.md").read_text().splitlines()
    summary_lines[0] = generator.expected_title(experiment, {})
    (experiment / "summary.md").write_text("\n".join(summary_lines) + "\n")
    shutil.copyfile(
        template / "NNN-YYYY-MM-DD-description/configuration.md",
        experiment / "configuration.md",
    )
    return experiment


def session_run(
    log_dir: Path,
    root: Path,
    *,
    since: str | None = None,
    until: str | None = None,
    experiment: Path | None = None,
) -> dict[str, Any]:
    """Build and optionally persist a session report; return the results document.

    With ``--experiment``: writes ``session-results.json``, replaces the generated
    session block in ``summary.md``, and seeds ``profile.yaml`` from the instance
    ``facts.json`` plus the log's sampler echo when the experiment has none; an LM
    Studio log has no ``facts.json``, so its profile is seeded from the recipe name
    and the log alone. An existing profile is never overwritten.

    Raises:
        ValueError: logs are unreadable, filters are unusable, or the experiment path
            is not a repository experiment folder.
    """
    facts_path = log_dir / "facts.json"
    facts = importer.read_json(facts_path) if facts_path.is_file() else {}
    engine_hint = facts.get("adapter") if isinstance(facts.get("adapter"), str) else None
    engine, entries, unclosed, names, sampling = session.read_engine_logs(log_dir, engine_hint)
    window = {"since": since, "until": until}
    bounds = {
        key: datetime.fromisoformat(value) if value else None for key, value in window.items()
    }
    kept = session.filter_window(entries, bounds["since"], bounds["until"])
    document = session.session_stats(
        kept,
        engine=engine,
        since=bounds["since"],
        until=bounds["until"],
        unclosed=unclosed,
        log_files=names,
    )
    schema.validate_session(document)
    if experiment is None:
        return document
    recipe_dir = experiment.parent
    summary = experiment / "summary.md"
    if not summary.is_file():
        raise ValueError(f"{experiment} has no summary.md to update")
    generator.write_atomic(
        experiment / "session-results.json", json.dumps(document, indent=2) + "\n"
    )
    report.write_session_block(summary, report.render_session(document))
    profile = experiment / "profile.yaml"
    if not profile.exists():
        if not facts and engine != "lm-studio":
            raise ValueError(f"{log_dir} has no facts.json; cannot seed {profile}")
        profile.write_text(
            yaml.safe_dump(
                importer.session_profile(facts, recipe_dir, root, sampling),
                sort_keys=False,
                allow_unicode=True,
            )
        )
        if (experiment / "configuration.md").is_file():
            path, _, rendered = generator.update(experiment)
            generator.write_atomic(path, rendered)
    return document


def default_output(models: Path, recipe: str, now: datetime | None = None) -> Path:
    """Where a run is written when ``--output`` is not given."""
    stamp = (now or datetime.now()).strftime("%Y-%m-%d-%H%M")
    return models.expanduser() / "baselines" / recipe / stamp


def _normalize_url(url: str) -> str:
    return url.rstrip("/").removesuffix("/v1").rstrip("/")


def _ask(question: str, default: str | None) -> str:
    """One interactive answer; empty input means the default."""
    suffix = f" [{default}]" if default is not None else " (Enter to skip)"
    try:
        return input(f"[baseline] {question}{suffix}: ").strip()
    except (EOFError, OSError) as error:
        raise guided.GuidedAborted("input closed before an answer") from error


def _served_model_ids(base_url: str) -> list[str]:
    data = api.post_json(base_url, "/v1/models", None, timeout=10)
    return [m["id"] for m in data.get("data", []) if isinstance(m, dict) and "id" in m]


@dataclass
class Plan:
    """What a run needs from its recipe: where the server is and how it is controlled."""

    kind: str
    base_url: str
    context: int
    control: ServerControl | None
    monitoring: monitor.Monitoring
    meta_extra: dict[str, Any] = field(default_factory=dict)


def _system_facts() -> dict[str, object] | None:
    """Host facts for ``meta.json``; a missing fact degrades to null instead of failing the run."""
    try:
        return host_facts.collect()
    except OSError as error:
        _progress(f"Host facts unavailable: {error}")
        return None


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
    control = ContainerControl(
        recipe,
        options,
        gpu_vram_gib=lambda: _gpu_vram_gib(gpu_address),
        record_facts=lambda: record_start_facts(recipe, options),
    )
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
    if recipe is not None and args.yes:
        print("--yes belongs to the guided desktop setup", file=sys.stderr)
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
    if recipe is None and (args.yes or args.base_url is None or args.context is None):
        try:
            setup = guided.guide(
                _served_model_ids,
                guided.find_app_pids,
                _ask,
                _progress,
                yes=args.yes,
                base_url=args.base_url,
                model=args.model,
                context=args.context,
                pid=args.pid,
            )
        except guided.GuidedAborted as error:
            print(f"Guided setup stopped: {error}", file=sys.stderr)
            return ExitCode.USAGE
        args.base_url, args.model = setup.base_url, setup.model
        args.context, args.pid = setup.context, setup.pid
    try:
        expectations = vision.load_expectations(root / "assets/checks/amdgpu-top.expected.json")
        corpus = workloads.load_corpus(workloads.default_corpus_directory())
        writer = RunWriter(output)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return ExitCode.USAGE
    try:
        gpu_address, candidates = (None, []) if args.no_gpu else _find_gpu(args.gpu_pci)
        if recipe is not None:
            try:
                refresh_sudo_ticket()
            except ValueError as error:
                print(f"Preflight failed: {error}", file=sys.stderr)
                return ExitCode.PREFLIGHT_FAILED
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
            "system": _system_facts(),
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
    if args.command == "import":
        try:
            folder = importer.import_run(args.run_dir, root, recipes=recipes, suffix=args.suffix)
        except (OSError, ValueError, yaml.YAMLError) as error:
            print(f"Cannot import {args.run_dir}: {error}", file=sys.stderr)
            return ExitCode.USAGE
        print(f"Imported experiment {folder}")
        return ExitCode.OK
    if args.command == "session":
        if args.logs is None and args.instance is None:
            print("session requires an instance name or --logs DIR", file=sys.stderr)
            return ExitCode.USAGE
        log_dir = (
            args.logs.expanduser().resolve()
            if args.logs is not None
            else paths.logs_dir(paths.data_home(), args.instance)
        )
        experiment = args.experiment
        if args.create:
            if args.logs is not None or args.instance is None:
                print(
                    "session --create needs the instance name; it also selects the recipe",
                    file=sys.stderr,
                )
                return ExitCode.USAGE
            try:
                experiment = create_session_folder(root, args.instance, args.create, log_dir)
            except (OSError, ValueError) as error:
                print(f"Cannot create session experiment: {error}", file=sys.stderr)
                return ExitCode.USAGE
        try:
            document = session_run(
                log_dir,
                root,
                since=args.since,
                until=args.until,
                experiment=experiment,
            )
        except (OSError, ValueError, yaml.YAMLError) as error:
            print(f"Cannot report session in {log_dir}: {error}", file=sys.stderr)
            return ExitCode.USAGE
        if experiment is None:
            print(json.dumps(document, indent=2))
        else:
            totals = document["totals"]
            print(
                f"Session in {experiment}: {totals['requests']} completions, "
                f"{totals['generated_tokens']:,} tokens generated"
            )
        return ExitCode.OK
    return _run_command(args, suite or SuiteConfig(), root, recipes or root / "recipes")
