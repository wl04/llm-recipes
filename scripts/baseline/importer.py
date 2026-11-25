"""Create a repository experiment folder from a completed baseline run directory.

Field precedence: run data (``results.json``, ``meta.json``, ``facts.json``) wins over
the static recipe configuration; static configuration only fills fields the run never
observed. Fields no source records stay ``null``, and ``profile.yaml`` is complete
enough that a container baseline needs no manual edits after import.
"""

import hashlib
import json
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import generate_configurations as generator
import paths
import yaml

from baseline import schema, workloads

HARNESS = "llm-recipes baseline suite"
RESULTS_NAME = "results.json"
META_NAME = "meta.json"
FACTS_NAME = "facts.json"

ENGINE_DISPLAY = {"exllamav3": "ExLlamaV3", "strata": "Strata"}
SERVER_DISPLAY = {"tabbyapi": "TabbyAPI", "strata": "Strata"}

# Recipe folder tokens that begin the hardware and format sections of the name
# ``<model>-<format>-<hardware>-<memory>`` documented in docs/authoring.md.
GPU_HEAD_TOKENS = frozenset({"rx", "rtx", "arc", "gtx", "mi"})
FORMAT_HEAD_TOKENS = frozenset({"gguf", "exl3", "exl2", "awq", "mlx", "gptq"})
# Slug tokens whose generated display form is spelled in capitals.
UPPERCASE_TOKENS = frozenset(
    {
        "gb",
        "vram",
        "xt",
        "rx",
        "rtx",
        "arc",
        "gtx",
        "gguf",
        "exl3",
        "exl2",
        "awq",
        "mlx",
        "gptq",
        "ista",
        "ud",
        "iq2",
        "iq3",
        "iq4",
        "iq1",
        "xxs",
        "xs",
        "mtp",
    }
)
MEMORY_TAIL = re.compile(r"^(?P<rest>.+)-(?P<size>\d+)-gb-vram$")
RUN_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
FOLDER_NUMBER = re.compile(r"^(\d{3})-")
SUFFIX_RULE = re.compile(r"[a-z0-9][a-z0-9-]*\Z")

# Run-time option values rendered as settings; TabbyAPI and Strata accept "cpu" vision.
VISION_VALUES = {"on": True, "off": False, "cpu": "cpu"}

TABBY_SERVING: tuple[tuple[tuple[str, ...], str], ...] = (
    (("model", "cache_size"), "cache_capacity"),
    (("model", "cache_mode"), "target_cache"),
    (("draft_model", "draft_cache_mode"), "draft_cache"),
    (("model", "chunk_size"), "chunk_size"),
    (("model", "max_batch_size"), "max_batch_size"),
    (("model", "tensor_parallel"), "tensor_parallel"),
    (("memory", "sysmem_recurrent_cache"), "sysmem_recurrent_cache_mib"),
    (("model", "vision"), "vision"),
)
STRATA_FLAGS = {
    "--expert-cache": "expert_cache",
    "--prefill": "prefill",
    "--spec": "max_draft_tokens",
    "--spec-min-p": "min_draft_probability",
    "--kv": "kv_cache",
    "--kv-resident": "gpu_resident_kv_cells",
    "--vision": "vision",
}
DISCRETE_MARKERS = ("navi", "radeon rx", "radeon pro")
UNIFIED_MARKERS = ("radeon graphics", "radeon 7", "radeon 8")


def read_json(path: Path) -> dict[str, Any]:
    """Read a required JSON object; name the file in every failure message."""
    try:
        document = json.loads(path.read_text())
    except FileNotFoundError as error:
        raise ValueError(f"{path} is missing") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: not valid JSON ({error})") from error
    if not isinstance(document, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return document


def _read_optional(path: Path) -> dict[str, Any]:
    """Read a JSON object when the file exists; recipes may omit optional files."""
    return read_json(path) if path.is_file() else {}


def _obj(value: object) -> Mapping[str, Any]:
    """Return the value when it is a mapping, else an empty mapping."""
    return value if isinstance(value, Mapping) else {}


def _seq(value: object) -> list[Any]:
    """Return the value when it is a list, else an empty list."""
    return value if isinstance(value, list) else []


def _dig(mapping: Mapping[str, Any] | None, *keys: str) -> Any:  # noqa: ANN401 - JSON field
    current: Any = mapping
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _first(*values: Any) -> Any:  # noqa: ANN401 - JSON field
    for value in values:
        if value is not None:
            return value
    return None


def _display_token(token: str) -> str:
    if token in UPPERCASE_TOKENS or re.fullmatch(r"\d+b", token):
        return token.upper()
    return token[:1].upper() + token[1:]


def recipe_identity(recipe_dir: Path) -> str:
    """Profile id shared by all experiments of one recipe.

    Reuses the id of the recipe's earliest existing experiment so the identity
    never splits over wording drift; folder-derived parts serve only the first
    experiment of a recipe.
    """
    for profile in sorted(recipe_dir.glob("*/profile.yaml")):
        try:
            existing = yaml.safe_load(profile.read_text(encoding="utf-8"))
        except OSError, yaml.YAMLError:
            continue
        identifier = existing.get("id") if isinstance(existing, dict) else None
        if isinstance(identifier, str) and identifier.strip():
            return identifier.strip()
    model, format_part, hardware, memory = experiment_identity(recipe_dir.name)
    return f"{model} / {format_part} / {hardware} / {memory}"


def experiment_identity(recipe_name: str) -> tuple[str, str, str, str]:
    """Split ``<model>-<format>-<hardware>-<memory>`` into the four profile id parts.

    The generated parts re-slug to the recipe folder name, so the generator accepts
    the profile without a custom ``id``. Raises ValueError when the folder name does
    not follow the documented naming rule.
    """
    memory = MEMORY_TAIL.fullmatch(recipe_name)
    if memory is None:
        raise ValueError(
            f"{recipe_name}: the folder name must end with a memory part, "
            "such as 16-gb-vram (see the naming rule in docs/authoring.md)"
        )
    head = memory["rest"].split("-")
    memory_part = f"{memory['size']} GB VRAM"
    gpu_at = next(
        (i for i, token in enumerate(head) if token in GPU_HEAD_TOKENS),
        None,
    )
    if gpu_at is None or gpu_at == 0:
        raise ValueError(
            f"{recipe_name}: no hardware part such as rx-9070-xt before the memory part"
        )
    hardware = " ".join(_display_token(token) for token in head[gpu_at:])
    model_and_format = head[:gpu_at]
    format_at = next(
        (i for i, token in enumerate(model_and_format) if token in FORMAT_HEAD_TOKENS),
        None,
    )
    if format_at is None:
        format_at = len(model_and_format) - 1
    if format_at == 0:
        raise ValueError(f"{recipe_name}: no model part before the format part")
    model = "-".join(_display_token(token) for token in model_and_format[:format_at])
    format_part = " ".join(_display_token(token) for token in model_and_format[format_at:])
    return model, format_part, hardware, memory_part


def _gpu_sku(description: str) -> str:
    bracketed: list[str] = re.findall(r"\[([^\]]+)\]", description)
    if bracketed:
        return bracketed[-1]
    return re.sub(r"\s*\(rev [0-9a-f]+\)\s*$", "", description).strip()


def _memory_architecture(description: str | None) -> str | None:
    """Classify discrete and unified memory from reviewed GPU description markers."""
    if not description:
        return None
    text = description.lower()
    if any(marker in text for marker in UNIFIED_MARKERS):
        return "unified"
    if any(marker in text for marker in DISCRETE_MARKERS):
        return "discrete"
    return None


def _rounded_gib(value: Any) -> int | None:  # noqa: ANN401 - JSON field
    return round(value) if isinstance(value, (int, float)) else None


def hardware_block(system: Mapping[str, Any] | None) -> dict[str, Any]:
    gpu = _obj(_dig(system, "gpu"))
    description = gpu.get("model") if isinstance(gpu.get("model"), str) else None
    gfx = gpu.get("gfx_arch") if isinstance(gpu.get("gfx_arch"), str) else None
    gpu_text: str | None = None
    if description:
        sku = _gpu_sku(description)
        gpu_text = f"{sku} ({gfx})" if gfx else sku
    memory = _dig(system, "memory")
    return {
        "gpu": gpu_text,
        "cpu": _dig(system, "cpu", "model"),
        "memory": {
            "architecture": _memory_architecture(description),
            "dedicated_vram_gib": _rounded_gib(gpu.get("vram_total_gib")),
            "system_ram_gib": _rounded_gib(_dig(memory, "total_gib")),
            "unified_memory_gib": None,
        },
    }


def os_block(system: Mapping[str, Any] | None, meta: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": _dig(system, "os", "name"),
        "version": _dig(system, "os", "version"),
        "kernel": _dig(system, "kernel") or _dig(meta, "host", "kernel"),
        "kernel_driver": _dig(system, "gpu", "driver"),
    }


def _repository_url(root: Path) -> str | None:
    """HTTPS base URL of the repository origin, or None outside a git checkout."""
    listing = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        check=False,
        capture_output=True,
        text=True,
    )
    remote = listing.stdout.strip()
    if listing.returncode or not remote:
        return None
    ssh = re.fullmatch(r"(?:ssh://)?git@([^:]+):(.+)", remote)
    if ssh:
        return f"https://{ssh[1]}/{ssh[2].removesuffix('.git')}"
    if remote.startswith(("https://", "http://")):
        return remote.removesuffix(".git")
    return None


def software_block(
    meta: Mapping[str, Any],
    facts: Mapping[str, Any] | None,
    runtime: Mapping[str, Any],
    lock: Mapping[str, Any],
    system: Mapping[str, Any] | None,
    root: Path,
) -> dict[str, Any]:
    revision = _obj(_dig(meta, "host", "revision"))
    commit = revision.get("commit")
    base_url = _repository_url(root) if commit else None
    harness_version = None
    if commit and base_url:
        harness_version = f"{base_url}/commit/{commit}"
        if revision.get("dirty"):
            harness_version += " (dirty)"
        elif "dirty" in revision and revision["dirty"] is None:
            harness_version += " (dirty state unknown)"
    engine_value = runtime.get("engine")
    adapter_value = runtime.get("adapter")
    engine = engine_value if isinstance(engine_value, str) else None
    adapter = adapter_value if isinstance(adapter_value, str) else None
    sources = _obj(lock.get("sources"))

    def source_url(key: str | None) -> str | None:
        if not key:
            return None
        source = _obj(sources.get(key))
        if not source:
            return None
        repository = source.get("repository")
        revision = source.get("revision")
        if not isinstance(repository, str) or not isinstance(revision, str):
            return None
        if not repository.startswith(("https://", "http://")):
            repository = f"https://github.com/{repository}"
        return f"{repository.rstrip('/')}/commit/{revision}"

    engine_revision = source_url(engine)
    image = _obj(facts.get("image") if facts else None)
    base_image_digest = lock.get("base_image")
    base_tag = lock.get("base_tag")
    base_image_url = None
    if isinstance(base_image_digest, str) and "@" in base_image_digest:
        reference = base_image_digest.split("@", 1)[0].removeprefix("docker.io/")
        image_repository, separator, embedded_tag = reference.rpartition(":")
        if separator and "/" not in embedded_tag:
            reference = image_repository
            base_tag = base_tag or embedded_tag
        if reference.startswith("rocm/"):
            base_image_url = f"https://hub.docker.com/r/{reference}/tags"
            if isinstance(base_tag, str) and re.fullmatch(r"[\w][\w.-]{0,127}", base_tag):
                base_image_url += f"?name={base_tag}"
    rocm = generator.rocm_version(lock.get("torch_version"), base_tag)
    return {
        "harness": HARNESS,
        "harness_version": harness_version,
        "engine": ENGINE_DISPLAY.get(engine or "", engine and engine.title()),
        "engine_version": runtime.get("engine_version"),
        "engine_source_version": runtime.get("engine_source_version"),
        "revision": engine_revision,
        "rocm_version": rocm,
        "backend": "ROCm / HIP" if rocm else None,
        "backend_api_version": None,
        "gpu_driver": _dig(system, "gpu", "driver"),
        "gpu_driver_version": None,
        "pytorch": lock.get("torch_version"),
        "python": lock.get("python_version"),
        "base_image_tag": base_image_url,
        "base_image": base_image_digest,
        "server": SERVER_DISPLAY.get(adapter or "", adapter and adapter.title()),
        "server_version": source_url("tabbyAPI") if adapter == "tabbyapi" else engine_revision,
        "host_python": _dig(meta, "host", "python"),
        "running_image_id": image.get("image_id") or _dig(meta, "container", "image_id"),
    }


def model_block(recipe_dir: Path, format_part: str) -> dict[str, Any]:
    lock = _read_optional(recipe_dir / "config" / "models.lock.json")
    target = _obj(lock.get("target"))
    draft = _obj(lock.get("draft"))
    providers = _obj(_read_optional(recipe_dir / "config" / "pi.models.json").get("providers"))
    names = [
        model["name"]
        for provider in providers.values()
        if isinstance(provider, Mapping)
        for model in _seq(provider.get("models"))
        if isinstance(model, Mapping) and isinstance(model.get("name"), str)
    ]
    model: dict[str, Any] = {
        "name": names[0] if names else None,
        "format": format_part,
        "quantization": None,
        "repository": f"https://huggingface.co/{target['repo_id']}"
        if isinstance(target.get("repo_id"), str)
        else None,
        "artifacts": [
            name
            for name in _seq(target.get("files"))
            if isinstance(name, str) and name.endswith(".gguf")
        ],
        "revision": f"https://huggingface.co/{target['repo_id']}/commit/{target['revision']}"
        if isinstance(target.get("repo_id"), str) and isinstance(target.get("revision"), str)
        else None,
    }
    if isinstance(lock.get("repository"), str):
        repository = f"https://huggingface.co/{lock['repository']}"
        model["repository"] = repository
        if isinstance(lock.get("revision"), str):
            model["revision"] = f"{repository}/commit/{lock['revision']}"
        model["artifacts"] = [
            item["path"]
            for item in _seq(lock.get("files"))
            if isinstance(item, Mapping) and isinstance(item.get("path"), str)
        ]
        projector = _obj(lock.get("projector"))
        if isinstance(projector.get("path"), str):
            model["artifacts"] = [
                name for name in model["artifacts"] if name != projector.get("source")
            ] + [projector["path"]]
        for artifact in model["artifacts"]:
            path = Path(artifact)
            if len(path.parts) > 1 and re.search(r"-00001-of-\d{5}\.gguf$", path.name):
                model["quantization"] = path.parent.name
                break
        mtp = _obj(lock.get("mtp"))
        if isinstance(mtp.get("repository"), str):
            model["draft_repository"] = f"https://huggingface.co/{mtp['repository']}"
            if isinstance(mtp.get("revision"), str):
                model["draft_revision"] = f"{model['draft_repository']}/commit/{mtp['revision']}"
        model["draft_quantization"] = mtp.get("expert_quantization")
    if draft:
        model["draft_repository"] = (
            f"https://huggingface.co/{draft['repo_id']}"
            if isinstance(draft.get("repo_id"), str)
            else None
        )
        model["draft_revision"] = (
            f"https://huggingface.co/{draft['repo_id']}/commit/{draft['revision']}"
            if isinstance(draft.get("repo_id"), str) and isinstance(draft.get("revision"), str)
            else None
        )
        arguments = _seq(_dig(lock, "conversion", "arguments"))
        model["draft_quantization"] = (
            shlex.join(str(argument) for argument in arguments) if arguments else None
        )
        model["draft_size"] = None
    return model


def _flatten(policy: Mapping[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in policy.items():
        if isinstance(value, Mapping):
            flat.update({f"{key}.{inner}": inner_value for inner, inner_value in value.items()})
        else:
            flat[key] = value
    return flat


def thinking_block(results: Mapping[str, Any]) -> dict[str, Any]:
    policy = _obj(_dig(results, "policy", "thinking_request"))
    if not policy:
        return {"enabled": None, "control": None}
    flat = _flatten(policy)
    enabled: bool | None = None
    if isinstance(flat.get("chat_template_kwargs.enable_thinking"), bool):
        enabled = flat["chat_template_kwargs.enable_thinking"]
    elif isinstance(flat.get("reasoning_effort"), str):
        enabled = flat["reasoning_effort"] != "none"
    control = "; ".join(
        f"{key}={str(value).lower() if isinstance(value, bool) else value}"
        for key, value in flat.items()
    )
    return {"enabled": enabled, "control": control or None}


def _native_serving(recipe_dir: Path) -> dict[str, Any]:
    """Static serving rows from the recipe's native server settings file."""
    rows: dict[str, Any] = {}
    tabby = recipe_dir / "config" / "tabby.yml"
    if tabby.is_file():
        settings = yaml.safe_load(tabby.read_text())
        if not isinstance(settings, Mapping):
            raise ValueError(f"{tabby}: expected a YAML mapping")
        for keys, row in TABBY_SERVING:
            value = _dig(settings, *keys)
            if value is not None:
                rows[row] = bool(value) if isinstance(value, bool) else value
    else:
        native = recipe_dir / "config" / "strata.json"
        if not native.is_file():
            return rows
        try:
            settings = json.loads(native.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"{native}: unreadable JSON settings") from error
        if not isinstance(settings, Mapping):
            raise ValueError(f"{native}: expected a JSON object")
        args = _seq(settings.get("args"))
        for index, token in enumerate(args):
            setting_row = STRATA_FLAGS.get(str(token))
            if setting_row is None:
                continue
            if index + 1 < len(args) and not str(args[index + 1]).startswith("--"):
                rows[setting_row] = args[index + 1]
            else:
                rows[setting_row] = True
        vision_settings = _obj(settings.get("vision"))
        if isinstance(vision_settings.get("min_tokens"), int):
            rows["vision_min_image_tokens"] = vision_settings["min_tokens"]
        if isinstance(vision_settings.get("max_tokens"), int):
            rows["vision_max_image_tokens"] = vision_settings["max_tokens"]
    return rows


def _effective_serving(
    serving: dict[str, Any], adapter: str | None, context: object, draft: object, vision: object
) -> None:
    """Apply the serving adapters' launch overrides to profile rows."""
    if type(context) is int:
        serving["context_length_tokens"] = context
        if adapter == "tabbyapi":
            serving["cache_capacity"] = context
        elif adapter == "strata":
            serving["gpu_resident_kv_cells"] = min(context, 32768)
    if isinstance(draft, str):
        serving["speculative_decoding"] = draft == "on"
        if draft == "on" and adapter == "strata":
            serving["draft_method"] = "MTP"
        if adapter == "strata" and draft == "off":
            serving["max_draft_tokens"] = 0
    if isinstance(vision, str):
        serving["vision"] = VISION_VALUES.get(vision, vision)
        if vision == "off":
            serving.pop("vision_min_image_tokens", None)
            serving.pop("vision_max_image_tokens", None)


def validate_launch_facts(facts: Mapping[str, Any] | None, recipe_dir: Path) -> None:
    """Reject mismatched identities or recorded files that have changed."""
    if not facts:
        return
    identity = facts.get("recipe")
    if identity is not None and identity != recipe_dir.name:
        raise ValueError(f"Facts describe recipe {identity!r}, expected {recipe_dir.name!r}")
    files = {
        name: recipe_dir / "config" / name
        for name in ("launch.json", "models.lock.json", "tabby.yml", "strata.json")
    }
    runtime = facts.get("runtime")
    if isinstance(runtime, str):
        runtime_dir = recipe_dir.parents[1] / "runtimes" / runtime
        files.update(
            {
                "runtime.json": runtime_dir / "runtime.json",
                "versions.lock.json": runtime_dir / "container/versions.lock.json",
            }
        )
    changed = []
    for name, digest in _obj(facts.get("config_sha256")).items():
        path = files.get(name)
        if path is None:
            raise ValueError(f"Unknown recorded configuration file: {name}")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            changed.append(name)
    if changed:
        raise ValueError(
            "Recorded configuration differs: "
            + ", ".join(changed)
            + ". Review the run with its matching recipe/runtime files before importing."
        )


def settings_block(
    meta: Mapping[str, Any],
    results: Mapping[str, Any],
    facts: Mapping[str, Any] | None,
    recipe_dir: Path,
    adapter: str | None,
) -> dict[str, Any]:
    launch = _obj(meta.get("launch"))
    static_launch = _read_optional(recipe_dir / "config" / "launch.json")
    served = _dig(results, "server", "model")
    serving: dict[str, Any] = {}
    if isinstance(served, str) and served != "unknown":
        serving["served_model_id"] = served
    if adapter is not None:
        # Static native rows describe the container server; a desktop run does not use them.
        for row, value in _native_serving(recipe_dir).items():
            serving[row] = value
    context = _first(
        _dig(results, "server", "context_tokens"),
        _dig(facts, "options", "context"),
        launch.get("context"),
        static_launch.get("context"),
    )
    _effective_serving(
        serving,
        adapter,
        context,
        _first(launch.get("draft"), _dig(facts, "options", "draft"), static_launch.get("draft")),
        _first(launch.get("vision"), _dig(facts, "options", "vision"), static_launch.get("vision")),
    )
    kind = _dig(results, "server", "kind")
    token_counting = workloads.TOKEN_COUNT_ROUTE.get(kind) if isinstance(kind, str) else None
    return {
        "serving": serving,
        "sampling": None,
        "thinking": thinking_block(results),
        "requests": {
            "endpoint": "/v1/chat/completions",
            "token_counting": token_counting,
            "streaming": "Performance requests streamed",
            "concurrency": 1,
        },
        "notes": None,
    }


def _facts(meta: Mapping[str, Any], run_dir: Path) -> dict[str, Any] | None:
    recorded = meta.get("launch_facts")
    if isinstance(recorded, Mapping) and recorded:
        return dict(recorded)
    logs = _dig(meta, "container", "logs")
    candidates = [
        run_dir / "server-logs" / FACTS_NAME,
        Path(logs) / FACTS_NAME if isinstance(logs, str) else None,
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return read_json(candidate)
    return None


def _run_date(run_dir: Path) -> str:
    match = RUN_DATE.match(run_dir.name)
    if match:
        return match[1]
    stamp = (run_dir / META_NAME).stat().st_mtime
    return datetime.fromtimestamp(stamp, UTC).date().isoformat()


def experiment_name(recipes_dir: Path, recipe: str, date: str, suffix: str | None) -> str:
    """Next free ``NNN-date-baseline[-suffix]`` folder name for the recipe."""
    existing = recipes_dir / recipe
    taken = (
        {child.name for child in existing.iterdir() if child.is_dir()}
        if existing.is_dir()
        else set()
    )
    numbers = [int(match[1]) for name in taken if (match := FOLDER_NUMBER.match(name))]
    number = (max(numbers) + 1) if numbers else 1
    while True:
        name = f"{number:03d}-{date}-baseline"
        name = f"{name}-{suffix}" if suffix else name
        if name not in taken:
            return name
        number += 1


def build_profile(
    run_dir: Path,
    results: Mapping[str, Any],
    meta: Mapping[str, Any],
    recipe_dir: Path,
) -> dict[str, Any]:
    """Compose a schema-v2 ``profile.yaml`` document from the run and recipe sources."""
    facts = _facts(meta, run_dir)
    validate_launch_facts(facts, recipe_dir)
    system = facts.get("host") if isinstance(facts, Mapping) else None
    if not isinstance(system, Mapping):
        recorded = _dig(meta, "host", "system")
        system = recorded if isinstance(recorded, Mapping) else None
    launch_json = recipe_dir / "config" / "launch.json"
    runtime_name = _first(_dig(facts, "runtime"), _dig(_read_optional(launch_json), "runtime"))
    runtime_dir = recipe_dir.parents[1] / "runtimes" / str(runtime_name) if runtime_name else None
    runtime: Mapping[str, Any] = (
        read_json(runtime_dir / "runtime.json")
        if runtime_dir is not None and (runtime_dir / "runtime.json").is_file()
        else {}
    )
    adapter = _first(_dig(facts, "adapter"), runtime.get("adapter"))
    lock_path = runtime_dir / "container" / "versions.lock.json" if runtime_dir else None
    lock: Mapping[str, Any] = (
        read_json(lock_path) if lock_path is not None and lock_path.is_file() else {}
    )
    runtime = _obj(_dig(facts, "runtime_inputs", "descriptor")) or runtime
    lock = _obj(_dig(facts, "runtime_inputs", "versions")) or lock
    _, format_part, _, _ = experiment_identity(recipe_dir.name)
    return {
        "id": recipe_identity(recipe_dir),
        "hardware": hardware_block(system),
        "os": os_block(system, meta),
        "software": software_block(meta, facts, runtime, lock, system, recipe_dir.parents[1]),
        "model": model_block(recipe_dir, format_part),
        "settings": settings_block(meta, results, facts, recipe_dir, adapter),
    }


def git_revision(root: Path) -> dict[str, Any]:
    """Current checkout revision of the harness, mirroring the baseline meta shape."""
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], check=False, capture_output=True, text=True
    )
    if commit.returncode:
        stamp = paths.version_stamp(root)
        if stamp is not None:
            return {"commit": stamp["commit"], "dirty": stamp["dirty"]}
        return {"commit": None, "dirty": False}
    dirty = (
        subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
        != ""
    )
    return {"commit": commit.stdout.strip(), "dirty": dirty}


def session_profile(
    facts: Mapping[str, Any],
    recipe_dir: Path,
    root: Path,
    sampling: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose a schema-v2 ``profile.yaml`` document from an instance ``facts.json``.

    ``facts`` is the launcher's instance document; ``sampling`` comes from the engine
    log. Fields no source records stay ``null``.
    """
    validate_launch_facts(facts, recipe_dir)
    system_value = facts.get("host")
    system = system_value if isinstance(system_value, Mapping) else None
    meta: dict[str, Any] = {
        "host": {
            "revision": git_revision(root),
            "python": platform.python_version(),
            "kernel": _dig(system, "kernel"),
        }
    }
    runtime_name = facts.get("runtime")
    runtime_dir = recipe_dir.parents[1] / "runtimes" / str(runtime_name) if runtime_name else None
    runtime: Mapping[str, Any] = (
        read_json(runtime_dir / "runtime.json")
        if runtime_dir is not None and (runtime_dir / "runtime.json").is_file()
        else {}
    )
    adapter_value = facts.get("adapter")
    adapter = adapter_value if isinstance(adapter_value, str) else runtime.get("adapter")
    lock_path = runtime_dir / "container" / "versions.lock.json" if runtime_dir else None
    lock: Mapping[str, Any] = (
        read_json(lock_path) if lock_path is not None and lock_path.is_file() else {}
    )
    runtime = _obj(_dig(facts, "runtime_inputs", "descriptor")) or runtime
    lock = _obj(_dig(facts, "runtime_inputs", "versions")) or lock
    _, format_part, _, _ = experiment_identity(recipe_dir.name)
    options = _obj(facts.get("options"))
    serving: dict[str, Any] = {}
    if isinstance(adapter, str):
        for row, value in _native_serving(recipe_dir).items():
            serving[row] = value
    _effective_serving(
        serving, adapter, options.get("context"), options.get("draft"), options.get("vision")
    )
    image = _obj(facts.get("image"))
    if image.get("image_digests"):
        serving["image_digest"] = image["image_digests"][0]
    return {
        "id": recipe_identity(recipe_dir),
        "hardware": hardware_block(system),
        "os": os_block(system, meta),
        "software": software_block(meta, facts, runtime, lock, system, root),
        "model": model_block(recipe_dir, format_part),
        "settings": {
            "serving": serving,
            "sampling": dict(sampling) if sampling else None,
            "thinking": None,
            "requests": {"endpoint": "/v1/chat/completions"},
            "notes": None,
        },
    }


def recipe_directory(recipes: Path, name: str) -> Path:
    """Resolve one recipe identifier without escaping the recipes directory."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9.]*(?:-[a-z0-9.]+)*", name):
        raise ValueError(f"{name!r}: invalid recipe identifier")
    directory = recipes / name
    if directory.resolve().parent != recipes.resolve() or directory.is_symlink():
        raise ValueError(f"{name!r}: recipe identifier escapes the recipes directory")
    if not directory.is_dir():
        raise ValueError(f"recipe {name} has no folder under {recipes}")
    return directory


@contextmanager
def staged_experiment(destination: Path) -> Iterator[Path]:
    """Stage on the destination filesystem while preserving generator path identities."""
    with tempfile.TemporaryDirectory(prefix=".report-", dir=destination.parent) as temporary:
        recipe = Path(temporary) / destination.parent.name
        staged = recipe / destination.name
        staged.mkdir(parents=True)
        if (destination.parent / "setup.md").is_file():
            (recipe / "setup.md").touch()
        yield staged


def publish_experiment(staged: Path, destination: Path) -> None:
    """Publish a complete new experiment without replacing an existing destination."""
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"{destination}: experiment already exists")
    staged.rename(destination)


def import_run(
    run_dir: Path,
    root: Path,
    *,
    recipes: Path | None = None,
    suffix: str | None = None,
) -> Path:
    """Create the experiment folder for one completed run; return its path.

    Copies ``results.json``, seeds ``summary.md`` and ``configuration.md`` from the
    repository templates, writes a complete ``profile.yaml``, and runs the generator
    over the new folder, its recipe index, and the new summary title.
    """
    if suffix is not None and not SUFFIX_RULE.fullmatch(suffix):
        raise ValueError(f"suffix {suffix!r} must be lowercase words separated by hyphens")
    results = read_json(run_dir / RESULTS_NAME)
    meta = read_json(run_dir / META_NAME)
    status = _dig(results, "run", "status")
    if status != "complete":
        raise ValueError(f"{run_dir / RESULTS_NAME}: run status is {status!r}, not complete")
    if meta.get("problems") or _dig(meta, "run", "status") in {"failed", "interrupted"}:
        raise ValueError(f"{run_dir / META_NAME}: run has failures or was interrupted")
    schema.validate_results(results)
    recipe = results.get("recipe")
    if not isinstance(recipe, str) or not recipe:
        raise ValueError(f"{run_dir / RESULTS_NAME}: recipe name is missing")
    recipes_dir = recipes or root / "recipes"
    recipe_dir = recipe_directory(recipes_dir, recipe)
    date = _run_date(run_dir)
    name = experiment_name(recipes_dir, recipe, date, suffix)
    destination = recipe_dir / name
    profile = build_profile(run_dir, results, meta, recipe_dir)
    generator.profile_identity(profile)

    with staged_experiment(destination) as staged:
        shutil.copyfile(run_dir / RESULTS_NAME, staged / RESULTS_NAME)
        summary = (root / "templates/recipe/baseline-summary.md").read_text()
        if (recipe_dir / "setup.md").is_file():
            profile_link = " · [Profile YAML](profile.yaml)"
            summary = summary.replace(
                profile_link, " · [Build and run](../setup.md)" + profile_link, 1
            )
        (staged / "summary.md").write_text(summary)
        shutil.copyfile(
            root / "templates/recipe/NNN-YYYY-MM-DD-description/configuration.md",
            staged / "configuration.md",
        )
        (staged / "profile.yaml").write_text(
            yaml.safe_dump(profile, sort_keys=False, allow_unicode=True)
        )
        changes = [generator.update(staged), generator.update_summary(staged)]
        summaries = {path: new for path, _, new in changes if path.name == "summary.md"}
        index, _, rendered_index = generator.update_index(recipe_dir, summaries, additional=staged)
        for path, _, new in changes:
            generator.write_atomic(path, new)
        publish_experiment(staged, destination)
        try:
            generator.write_atomic(index, rendered_index)
        except OSError:
            shutil.rmtree(destination)
            raise
    return destination
