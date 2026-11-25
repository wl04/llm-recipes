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
    select_image,
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
    run.add_argument("--models", type=Path, help="Model directory (default: the data home)")
    run.add_argument("--runtime-image", help="Use a local image with the selected runtime lock")
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


def session_destination(
    root: Path, recipe: str, description: str, log_dir: Path, now: datetime | None = None
) -> Path:
    """Choose the next session destination without creating it."""
    if not importer.SUFFIX_RULE.fullmatch(description):
        raise ValueError(f"{description}: use a lowercase-hyphen slug, like coding-session")
    recipe_dir = importer.recipe_directory(root / "recipes", recipe)
    facts_path = log_dir / "facts.json"
    date = ""
    if facts_path.is_file():
        started = importer.read_json(facts_path).get("started_at")
        date = started[:10] if isinstance(started, str) else ""
    date = date or (now or datetime.now()).strftime("%Y-%m-%d")
    datetime.strptime(date, "%Y-%m-%d")
    numbers = [
        int(match[1])
        for child in recipe_dir.iterdir()
        if child.is_dir() and (match := importer.FOLDER_NUMBER.match(child.name))
    ]
    number = max(numbers) + 1 if numbers else 1
    while (experiment := recipe_dir / f"{number:03d}-{date}-{description}").exists():
        number += 1
    return experiment


def _session_run(
    log_dir: Path,
    root: Path,
    *,
    since: str | None = None,
    until: str | None = None,
    experiment: Path | None = None,
    recipe_dir: Path | None = None,
) -> dict[str, Any]:
    """Aggregate logs and populate staging files, preserving an existing profile."""
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
    recipe_dir = recipe_dir or experiment.parent
    summary = experiment / "summary.md"
    if not summary.is_file():
        raise ValueError(f"{experiment} has no summary.md to update")
    generator.write_atomic(
        experiment / "session-results.json", json.dumps(document, indent=2) + "\n"
    )
    report.write_session_block(summary, report.render_session(document))
    profile = experiment / "profile.yaml"
    if profile.exists():
        importer.validate_launch_facts(facts, recipe_dir)
    else:
        if not facts and engine != "lm-studio":
            raise ValueError(f"{log_dir} has no facts.json; cannot seed {profile}")
        profile.write_text(
            yaml.safe_dump(
                importer.session_profile(facts, recipe_dir, root, sampling),
                sort_keys=False,
                allow_unicode=True,
            )
        )
    return document


def session_run(
    log_dir: Path,
    root: Path,
    *,
    since: str | None = None,
    until: str | None = None,
    experiment: Path | None = None,
) -> dict[str, Any]:
    """Validate all report replacements in staging before updating an existing experiment."""
    if experiment is None:
        return _session_run(log_dir, root, since=since, until=until)
    experiment = experiment.absolute()
    recipe = importer.recipe_directory(root / "recipes", experiment.parent.name)
    if experiment.is_symlink() or experiment.resolve().parent != recipe.resolve():
        raise ValueError(f"{experiment}: not a repository experiment folder")
    if (experiment / "results.json").exists():
        raise ValueError(f"{experiment}: cannot contain both results.json and session-results.json")
    with importer.staged_experiment(experiment) as staged:
        for name in ("summary.md", "profile.yaml", "configuration.md"):
            source = experiment / name
            if source.is_symlink():
                raise ValueError(f"{source}: report files must not be symlinks")
            if source.is_file():
                shutil.copyfile(source, staged / name)
        document = _session_run(
            log_dir, root, since=since, until=until, experiment=staged, recipe_dir=recipe
        )
        if (staged / "configuration.md").is_file():
            path, _, rendered = generator.update(staged)
            generator.write_atomic(path, rendered)
        else:
            generator.render(staged)
        for source in staged.iterdir():
            destination = experiment / source.name
            content = source.read_text()
            if not destination.is_file() or destination.read_text() != content:
                generator.write_atomic(destination, content)
    return document


def create_session_report(
    root: Path,
    recipe: str,
    description: str,
    log_dir: Path,
    *,
    since: str | None = None,
    until: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Publish a new session experiment only after its complete report renders."""
    destination = session_destination(root, recipe, description, log_dir)
    with importer.staged_experiment(destination) as staged:
        template = root / "templates/recipe"
        shutil.copyfile(template / "session-summary.md", staged / "summary.md")
        shutil.copyfile(
            template / "NNN-YYYY-MM-DD-description/configuration.md",
            staged / "configuration.md",
        )
        document = _session_run(
            log_dir,
            root,
            since=since,
            until=until,
            experiment=staged,
            recipe_dir=destination.parent,
        )
        for path, _, rendered in (generator.update(staged), generator.update_summary(staged)):
            generator.write_atomic(path, rendered)
        importer.publish_experiment(staged, destination)
    return destination, document


def models_dir(models: Path | None) -> Path:
    """The models a run reads from: the requested directory, or the data home."""
    return paths.data_home() if models is None else models


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
    model: str | None = None


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
    args: argparse.Namespace,
    models_root: Path,
    recipe: Recipe,
    writer: RunWriter,
    gpu_address: str | None,
) -> Plan:
    """A container recipe: the runner starts the server through the launcher and stops it."""
    models = models_root.expanduser().resolve()
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
    model = args.model
    if model is None and recipe.adapter == "tabbyapi":
        path = recipe.directory / "config/tabby.yml"
        try:
            model = yaml.safe_load(path.read_text())["model"]["model_name"]
        except (OSError, yaml.YAMLError, TypeError, KeyError) as error:
            raise ValueError(f"{path}: missing or invalid model.model_name") from error
        if not isinstance(model, str) or not model.strip():
            raise ValueError(f"{path}: model.model_name must be a nonempty string")
    control = ContainerControl(
        recipe,
        options,
        gpu_vram_gib=lambda: _gpu_vram_gib(gpu_address),
        record_facts=lambda info: record_start_facts(
            recipe, options, container_id=info.container_id, image_id=info.image_id
        ),
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
        model=model,
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


def _argument_refusal(args: argparse.Namespace, recipe: Recipe | None, recipes: Path) -> int | None:
    """Refuse combinations of arguments that belong to another kind of recipe."""
    if recipe is None and not (recipes / args.recipe).is_dir():
        return _usage(f"Unknown recipe: {args.recipe}")
    if recipe is not None and (args.pid is not None or args.base_url):
        return _usage(
            "Container recipes are started by the runner; --pid and --base-url are for desktop "
            "recipes"
        )
    if recipe is None and args.runtime_image is not None:
        return _usage("--runtime-image belongs to container recipes")
    if recipe is not None and args.yes:
        return _usage("--yes belongs to the guided desktop setup")
    return None


def _usage(message: str) -> int:
    """Report an unusable command line."""
    print(message, file=sys.stderr)
    return ExitCode.USAGE


def _request_extra(args: argparse.Namespace) -> dict[str, Any] | None:
    """Parse ``--request-extra``; None when the value is not a non-empty JSON object."""
    if not args.request_extra:
        return {}
    try:
        parsed: object = json.loads(args.request_extra)
    except json.JSONDecodeError:
        parsed = None
    if not isinstance(parsed, dict) or not parsed:
        _usage("--request-extra must be a non-empty JSON object")
        return None
    return {str(key): value for key, value in parsed.items()}


def _desktop_setup(args: argparse.Namespace) -> int | None:
    """Complete a desktop run through the guided interview; None when it proceeded."""
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
        return _usage(f"Guided setup stopped: {error}")
    args.base_url, args.model = setup.base_url, setup.model
    args.context, args.pid = setup.context, setup.pid
    return None


def _run_config(
    args: argparse.Namespace,
    plan: Plan,
    suite: SuiteConfig,
    root: Path,
    corpus: list[workloads.Document],
    expectations: vision.Expectations,
    extra: dict[str, Any],
    gpu_address: str | None,
    candidates: list[str],
) -> RunConfig:
    """Assemble the run record inputs from the validated command line and the plan."""
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
    return RunConfig(
        recipe=args.recipe,
        kind=plan.kind,
        base_url=plan.base_url,
        model=plan.model or args.model,
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


def _report_run(code: int, writer: RunWriter, root: Path) -> int:
    """Render the recorded run and report its outcome."""
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


def _run_command(args: argparse.Namespace, suite: SuiteConfig, root: Path, recipes: Path) -> int:
    try:
        found = discover_recipes(recipes)
    except ValueError as error:
        print(f"Recipe discovery failed: {error}", file=sys.stderr)
        return ExitCode.USAGE
    recipe = found.get(args.recipe)
    refusal = _argument_refusal(args, recipe, recipes)
    if refusal is not None:
        return refusal
    if recipe is not None:
        try:
            recipe = select_image(recipe, args.runtime_image)
        except ValueError as error:
            return _usage(str(error))
    models = models_dir(args.models)
    output = args.output or default_output(models, args.recipe)
    if output.resolve().is_relative_to(root.resolve()):
        return _usage("--output must be outside the repository")
    extra = _request_extra(args)
    if extra is None:
        return ExitCode.USAGE
    if recipe is None and (args.yes or args.base_url is None or args.context is None):
        aborted = _desktop_setup(args)
        if aborted is not None:
            return aborted
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
            _managed_plan(args, models, recipe, writer, gpu_address)
            if recipe is not None
            else _attached_plan(args, recipe, gpu_address)
        )
    except (host.HostError, SourceError, ValueError) as error:
        print(f"Preflight failed: {error}", file=sys.stderr)
        return ExitCode.PREFLIGHT_FAILED if not isinstance(error, ValueError) else ExitCode.USAGE
    config = _run_config(
        args, plan, suite, root, corpus, expectations, extra, gpu_address, candidates
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
    return _report_run(code, writer, root)


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
        if args.create and (args.logs is not None or args.instance is None):
            print(
                "session --create needs the instance name; it also selects the recipe",
                file=sys.stderr,
            )
            return ExitCode.USAGE
        try:
            if args.create:
                experiment, document = create_session_report(
                    root, args.instance, args.create, log_dir, since=args.since, until=args.until
                )
            else:
                document = session_run(
                    log_dir, root, since=args.since, until=args.until, experiment=experiment
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
