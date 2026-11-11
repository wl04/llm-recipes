"""Recipe discovery, launch plans, and process operations shared by CLI interfaces."""

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Recipe:
    """A launchable recipe, independent of running instances."""

    name: str
    directory: Path
    adapter: str
    engine: str
    image: str
    port: int
    context: int
    draft: str
    vision: str


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


def validate_options(options: LaunchOptions) -> None:
    """Validate the current TabbyAPI adapter's launch capabilities."""
    instance_name(options.name)
    if options.context < 1024 or options.context > 999999999 or options.context % 256:
        raise ValueError("context must be at least 1024 and a multiple of 256 (at most 9 digits)")
    if not 1 <= options.port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    if options.draft not in ("on", "off") or options.vision not in ("on", "off"):
        raise ValueError("tabbyapi draft and vision must be on or off")


def discover_recipes(directory: Path) -> dict[str, Recipe]:
    """Read recipe-local manifests; reject malformed or unsupported definitions."""
    recipes = {}
    fields = {"adapter", "engine", "image", "port", "context", "draft", "vision"}
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
            if data["adapter"] != "tabbyapi" or data["engine"] != "exllamav3":
                raise ValueError("supported adapter/engine combination: tabbyapi/exllamav3")
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_./:@-]*", data["image"]):
                raise ValueError("invalid image reference")
            folder = manifest.parent.parent.resolve()
            recipe = Recipe(folder.name, folder, **data)
            validate_options(
                LaunchOptions(
                    recipe.name,
                    folder,
                    folder,
                    recipe.context,
                    recipe.draft,
                    recipe.vision,
                    recipe.port,
                )
            )
            recipes[recipe.name] = recipe
        except (ValueError, TypeError) as error:
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
    if recipe.adapter != "tabbyapi":
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
    options: LaunchOptions,
    *,
    groups: list[int],
    uid: int,
    gid: int,
) -> list[str]:
    """Validate options and build Docker argv without side effects."""
    validate_options(options)
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
        "adapter": recipe.adapter,
        "engine": recipe.engine,
        "instance": options.name,
    }.items():
        command += ["--label", f"io.llm-recipes.{key}={value}"]
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


def prepare_start(recipe: Recipe, options: LaunchOptions) -> None:
    """Validate writable mount inputs and create runtime directories on the host."""
    validate_options(options)
    if not options.models.is_dir():
        raise ValueError(f"Model directory does not exist: {options.models}")
    if not (recipe.directory / "scripts/serve.py").is_file():
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


def run_command(command: list[str]) -> int:
    """Run a foreground command with inherited streams and return its exit status.

    Detached Docker starts return immediately. Interactive frontends may provide
    their own process runner without changing recipe discovery or command planning.
    """
    return subprocess.run(command, check=False).returncode
