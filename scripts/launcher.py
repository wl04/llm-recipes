"""Recipe discovery, launch plans, and process operations shared by CLI interfaces."""

import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import host_facts
import paths


@dataclass(frozen=True)
class Recipe:
    """A launchable recipe, independent of running instances."""

    name: str
    directory: Path
    runtime: str
    runtime_directory: Path
    adapter: str
    engine: str
    image: str
    port: int
    context: int
    draft: str
    vision: str

    @property
    def data_subpath(self) -> Path:
        """Data folder of this recipe under the models root; mirrors recipes/."""
        return paths.RECIPES_SUBPATH / self.name


@dataclass(frozen=True)
class LaunchOptions:
    """Resolved launch settings supplied by any interface."""

    name: str
    models: Path
    logs: Path
    context: int
    draft: str
    vision: str
    port: int
    detached: bool = False


def instance_name(value: str) -> str:
    """Validate a Docker-compatible name that is also a safe log directory name."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,159}", value):
        raise ValueError("instance must use lowercase letters, digits, dots, dashes or underscores")
    return value


def validate_options(options: LaunchOptions, adapter: str = "tabbyapi") -> None:
    """Validate common options and the selected adapter's capabilities."""
    instance_name(options.name)
    if options.context < 1024 or options.context > 999999999 or options.context % 256:
        raise ValueError("context must be at least 1024 and a multiple of 256 (at most 9 digits)")
    if not 1 <= options.port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    visions = {"tabbyapi": ("on", "off"), "strata": ("cpu", "off")}
    if adapter not in visions:
        raise ValueError(f"Unsupported adapter: {adapter}")
    if options.draft not in ("on", "off") or options.vision not in visions[adapter]:
        raise ValueError(f"{adapter}: draft must be on/off; vision must be {visions[adapter]}")


def resolve_launch_options(
    recipe: Recipe,
    *,
    name: str,
    models: Path,
    logs: Path,
    context: int | None = None,
    draft: str | None = None,
    vision: str | None = None,
    port: int | None = None,
    detached: bool = False,
) -> LaunchOptions:
    """Fill unset launch options from the recipe's manifest defaults."""
    return LaunchOptions(
        name,
        models,
        logs,
        recipe.context if context is None else context,
        recipe.draft if draft is None else draft,
        recipe.vision if vision is None else vision,
        recipe.port if port is None else port,
        detached,
    )


def discover_recipes(directory: Path) -> dict[str, Recipe]:
    """Read recipe-local manifests; reject malformed or unsupported definitions."""
    recipes = {}
    fields = {"runtime", "port", "context", "draft", "vision"}
    for manifest in sorted(directory.glob("*/config/launch.json")):
        try:
            data = json.loads(manifest.read_text())
            if not isinstance(data, dict) or set(data) != fields:
                raise ValueError(f"expected fields: {', '.join(sorted(fields))}")
            for key in fields - {"port", "context"}:
                if not isinstance(data[key], str) or not data[key].strip():
                    raise ValueError(f"{key} must be a nonempty string")
            for key in ("port", "context"):
                if type(data[key]) is not int:
                    raise ValueError(f"{key} must be an integer")
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", data["runtime"]):
                raise ValueError("invalid runtime identifier")
            runtime = (directory.parent / "runtimes" / data["runtime"]).resolve()
            settings = json.loads((runtime / "runtime.json").read_text())
            if not isinstance(settings, dict) or set(settings) != {"adapter", "engine", "image"}:
                raise ValueError("runtime must define adapter, engine, and image")
            if any(not isinstance(value, str) or not value.strip() for value in settings.values()):
                raise ValueError("runtime fields must be nonempty strings")
            if (settings["adapter"], settings["engine"]) not in {
                ("tabbyapi", "exllamav3"),
                ("strata", "strata"),
            }:
                raise ValueError("supported adapter/engine: tabbyapi/exllamav3 or strata/strata")
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_./:@-]*", settings["image"]):
                raise ValueError("invalid image reference")
            if not (runtime / "scripts/serve.py").is_file():
                raise ValueError("runtime serving entry point is missing")
            folder = manifest.parent.parent.resolve()
            recipe = Recipe(folder.name, folder, runtime_directory=runtime, **data, **settings)
            validate_options(
                LaunchOptions(
                    recipe.name,
                    folder,
                    folder,
                    recipe.context,
                    recipe.draft,
                    recipe.vision,
                    recipe.port,
                ),
                recipe.adapter,
            )
            recipes[recipe.name] = recipe
        except (OSError, ValueError, TypeError) as error:
            raise ValueError(f"{manifest}: {error}") from error
    return recipes


def mount(source: Path, destination: str, readonly: bool = False) -> list[str]:
    """Return a bind mount, rejecting Docker CSV delimiters in host paths."""
    if "," in str(source) or "\n" in str(source):
        raise ValueError(f"Mount path contains a comma or newline: {source}")
    suffix = ",readonly" if readonly else ""
    return ["--mount", f"type=bind,src={source},dst={destination}{suffix}"]


def engine_command(recipe: Recipe, context: int, draft: str, vision: str) -> list[str]:
    """Translate launch options into the recipe's native entry point."""
    if recipe.adapter not in ("tabbyapi", "strata"):
        raise ValueError(f"No serving adapter for {recipe.name}")
    return [
        "python3",
        "/runtime/scripts/serve.py",
        "--draft",
        draft,
        "--vision",
        vision,
        "--context",
        str(context),
        "--recipe",
        f"/recipes/{recipe.name}",
    ]


def start_command(
    recipe: Recipe,
    options: LaunchOptions,
    *,
    groups: list[int],
    uid: int,
    gid: int,
) -> list[str]:
    """Validate options and build Docker argv without side effects."""
    validate_options(options, recipe.adapter)
    models, logs = options.models, options.logs
    context, draft, vision = options.context, options.draft, options.vision
    port, detached = options.port, options.detached
    command = [
        "sudo",
        "docker",
        "run",
        "--rm",
        "--init",
        "--name",
        "llm-recipes-" + instance_name(options.name),
    ]
    for key, value in {
        "managed": "true",
        "recipe": recipe.name,
        "runtime": recipe.runtime,
        "adapter": recipe.adapter,
        "engine": recipe.engine,
        "instance": options.name,
    }.items():
        command += ["--label", f"io.llm-recipes.{key}={value}"]
    if detached:
        command.append("--detach")
    if recipe.adapter == "strata":
        command += [
            "--ulimit",
            "memlock=-1:-1",
            # Docker reads suffixed units such as "2g" as decimal; pass exact bytes.
            "--shm-size",
            str(2 * 1024**3),
            "--stop-timeout",
            "120",
        ]
    command += ["--user", f"{uid}:{gid}"]
    command += gpu_access_args(groups)
    command += [
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
    command += mount(recipe.directory, f"/recipes/{recipe.name}", readonly=True)
    command += mount(recipe.runtime_directory, "/runtime", readonly=True)
    command += mount(models, "/models", readonly=True)
    command += mount(models / ".cache", "/cache")
    command += mount(logs, "/logs")
    return [*command, recipe.image, *engine_command(recipe, context, draft, vision)]


def gpu_access_args(groups: list[int]) -> list[str]:
    """Container arguments granting AMD compute and render access for the given groups."""
    group_arguments: list[str] = []
    for group in sorted(set(groups)):
        group_arguments += ["--group-add", str(group)]
    return [*group_arguments, "--device=/dev/kfd", "--device=/dev/dri"]


def gpu_groups() -> list[int]:
    """Read AMD device group IDs; fail before launch when devices are absent."""
    kfd = Path("/dev/kfd")
    renders = sorted(Path("/dev/dri").glob("renderD*"))
    if not kfd.exists() or not renders:
        raise ValueError("AMD devices missing: /dev/kfd and /dev/dri/renderD* are required")
    return [node.stat().st_gid for node in [kfd, *renders]]


def prepare_start(recipe: Recipe, options: LaunchOptions) -> None:
    """Validate writable mount inputs and create runtime directories on the host."""
    validate_options(options, recipe.adapter)
    if not options.models.is_dir():
        raise ValueError(f"Model directory does not exist: {options.models}")
    if not (recipe.runtime_directory / "scripts/serve.py").is_file():
        raise ValueError(f"Missing serving entry point in {recipe.directory}")
    (options.models / ".cache").mkdir(exist_ok=True)
    options.logs.mkdir(parents=True, exist_ok=True)


def lifecycle_command(action: str, name: str, follow: bool = False) -> list[str]:
    """Build commands addressing a named instance without recipe lookup."""
    container = "llm-recipes-" + instance_name(name)
    if action == "status":
        return ["sudo", "docker", "inspect", "--format", "{{.State.Status}}", container]
    if action == "logs":
        return ["sudo", "docker", "logs", *(["--follow"] if follow else []), container]
    if action == "stop":
        return ["sudo", "docker", "stop", container]
    raise ValueError(f"Unsupported lifecycle operation: {action}")


def running_command() -> list[str]:
    """List running instances using Docker labels rather than local state files."""
    return [
        "sudo",
        "docker",
        "ps",
        "--filter",
        "label=io.llm-recipes.managed=true",
        "--format",
        'table {{.Label "io.llm-recipes.instance"}}\t'
        '{{.Label "io.llm-recipes.recipe"}}\t{{.Status}}\t{{.Ports}}',
    ]


INSTANCE_FIELDS = ("instance", "recipe", "status", "ports")


def instances_command() -> list[str]:
    """Build a tab-separated listing of managed instances for machine consumers."""
    return [
        "sudo",
        "docker",
        "ps",
        "--filter",
        "label=io.llm-recipes.managed=true",
        "--format",
        '{{.Label "io.llm-recipes.instance"}}\t{{.Label "io.llm-recipes.recipe"}}'
        "\t{{.Status}}\t{{.Ports}}",
    ]


def parse_instances(output: str) -> list[dict[str, str]]:
    """Parse ``instances_command`` output into one record per non-empty line."""
    records: list[dict[str, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        values = line.rstrip("\n").split("\t", len(INSTANCE_FIELDS) - 1)
        if len(values) != len(INSTANCE_FIELDS):
            raise ValueError(f"unexpected instance listing line: {line!r}")
        records.append(dict(zip(INSTANCE_FIELDS, values, strict=True)))
    return records


def run_command(command: list[str]) -> int:
    """Run a foreground command with inherited streams and return its exit status.

    Detached Docker starts return immediately. Interactive frontends may provide
    their own process runner without changing recipe discovery or command planning.
    """
    return subprocess.run(command, check=False).returncode


def refresh_sudo_ticket() -> None:
    """Ask sudo for credentials once, up front, so later ``sudo -n`` calls never prompt.

    Raises:
        ValueError: elevation could not be obtained; the caller should abort.
    """
    print("Docker commands need sudo; entering credentials once...", file=sys.stderr)
    if subprocess.run(["sudo", "-v"], check=False).returncode != 0:
        raise ValueError("sudo credentials were not accepted; cannot manage containers")


FACTS_NAME = "facts.json"


def image_inspect_command(image: str) -> list[str]:
    """Non-interactive Docker inspection of an image reference for its digests."""
    return ["sudo", "-n", "docker", "image", "inspect", "--format", "{{json .}}", image]


def parse_image_inspect(text: str) -> dict[str, object]:
    """Extract the image ID and repository digests from ``image_inspect_command`` output.

    Raises:
        ValueError: the output is not one Docker image object.
    """
    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError as error:
        raise ValueError(f"unexpected image inspection output: {text[:80]!r}") from error
    if not isinstance(data, dict):
        raise ValueError("image inspection did not return one object")
    digests = data.get("RepoDigests")
    return {
        "image_id": data.get("Id"),
        "image_digests": digests if isinstance(digests, list) else [],
    }


def file_sha256(path: Path) -> str:
    """Hex SHA-256 of a file's contents."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def recipe_config_files(recipe: Recipe) -> list[Path]:
    """Recipe configuration files that pin the served behaviour, in stable order."""
    engine_file = "tabby.yml" if recipe.adapter == "tabbyapi" else "strata.json"
    names = ("launch.json", engine_file, "models.lock.json")
    return [recipe.directory / "config" / name for name in names]


def start_facts(
    recipe: Recipe,
    options: LaunchOptions,
    *,
    host: dict[str, object],
    image: dict[str, object],
    started_at: str,
) -> dict[str, object]:
    """Assemble the instance ``facts.json`` document: what this start actually ran."""
    config_hashes: dict[str, str] = {}
    for config in recipe_config_files(recipe):
        if config.is_file():
            config_hashes[config.name] = file_sha256(config)
    return {
        "started_at": started_at,
        "instance": options.name,
        "recipe": recipe.name,
        "runtime": recipe.runtime,
        "adapter": recipe.adapter,
        "engine": recipe.engine,
        "image": {"reference": recipe.image, **image},
        "options": {
            "port": options.port,
            "context": options.context,
            "draft": options.draft,
            "vision": options.vision,
            "detached": options.detached,
        },
        "mounts": {
            "recipe": str(recipe.directory),
            "runtime": str(recipe.runtime_directory),
            "models": str(options.models),
            "cache": str(options.models / ".cache"),
            "logs": str(options.logs),
        },
        "config_sha256": config_hashes,
        "host": host,
    }


def write_json_atomic(path: Path, data: object) -> None:
    """Write JSON through a temporary file and rename, so readers never see partial data."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(temporary, path)


def _capture_quiet(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True)


def record_start_facts(
    recipe: Recipe,
    options: LaunchOptions,
    *,
    run: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
    host: Callable[[], dict[str, object]] | None = None,
    started_at: Callable[[], str] = lambda: datetime.now(UTC).isoformat(timespec="seconds"),
) -> dict[str, object]:
    """Collect image identity and host facts, and atomically write the instance facts file.

    Returns the written document. The image must already be present locally; a missing
    image or an unwritable log directory raises, so a start never proceeds silently
    without its record.
    """
    inspect = run if run is not None else _capture_quiet
    collect = host if host is not None else host_facts.collect
    inspection = inspect(image_inspect_command(recipe.image))
    if inspection.returncode:
        raise ValueError((inspection.stderr.strip() or "docker image inspect failed")[:200])
    facts = start_facts(
        recipe,
        options,
        host=collect(),
        image=parse_image_inspect(inspection.stdout),
        started_at=started_at(),
    )
    write_json_atomic(options.logs / FACTS_NAME, facts)
    return facts
