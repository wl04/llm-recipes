"""Read-only workstation diagnostics for prepared container recipes."""

import json
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit

from launcher import Recipe


@dataclass(frozen=True)
class Finding:
    """One diagnostic result and an actionable explanation."""

    name: str
    status: str
    detail: str


def read_json(path: Path) -> dict[str, Any]:
    """Read metadata, rejecting non-object documents."""
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Expected an object: {path}")
    return data


def inspect_command(name: str, arguments: list[str], fix: str) -> Finding:
    """Run bounded, noninteractive Docker inspection without starting a container."""
    try:
        result = subprocess.run(
            ["sudo", "-n", "docker", *arguments],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode:
            return Finding(name, "FAIL", f"{result.stderr.strip() or 'Inspection failed'}. {fix}")
        return Finding(name, "PASS", result.stdout.strip())
    except (OSError, subprocess.TimeoutExpired) as error:
        return Finding(name, "FAIL", f"{error}. {fix}")


def require_file(path: Path) -> None:
    """Check that an artifact exists and is nonempty without reading model weights."""
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Missing or empty file: {path}")


STRATA_PACK_FILES = (
    "packs/iq3_xxs/native_experts.txt",
    "packs/iq3_xxs/index.txt",
    "packs/iq3_xxs/dense.bin",
    "packs/iq3_xxs/tokenizer/tokenizer.json",
    "packs/iq3_xxs/tokenizer/chat_template.jinja",
    "packs/iq3_xxs/tokenizer/vocab.json",
)
STRATA_DRAFT_FILES = ("experts.bin", "dense.bin", "dense.txt", "draft_vocab.bin")


def _strata_required_files(draft: bool) -> list[str]:
    """Artifact paths a prepared strata recipe must contain."""
    files: list[str] = list(STRATA_PACK_FILES)
    if draft:
        files.extend(f"mtp/rt/{name}" for name in STRATA_DRAFT_FILES)
    return files


def check_prepared(recipe: Recipe, models: Path) -> Finding:
    """Check locked preparation metadata and artifacts for the recipe's default capabilities."""
    try:
        lock = read_json(recipe.directory / "config/models.lock.json")
        versions = read_json(recipe.runtime_directory / "container/versions.lock.json")
        root = models / recipe.data_subpath
        if recipe.adapter == "strata":
            _check_strata_preparation(lock, versions, root, recipe)
        else:
            _check_gguf_preparation(lock, versions, root, recipe)
        return Finding("Prepared models", "PASS", f"Metadata and required artifacts: {root}")
    except (OSError, ValueError, KeyError, TypeError) as error:
        return Finding(
            "Prepared models", "FAIL", f"{error}. Follow this recipe's setup.md preparation steps."
        )


def _check_strata_preparation(
    lock: dict[str, Any], versions: dict[str, Any], root: Path, recipe: Recipe
) -> None:
    """Verify the strata receipt, the locked weight sizes, and the pack layout."""
    if read_json(root / "prepared.json") != {"models": lock, "image": versions}:
        raise ValueError("Preparation receipt differs from model or runtime lock")
    for item in lock["files"]:
        path = root / "models" / item["path"]
        require_file(path)
        if path.stat().st_size != item["size_bytes"]:
            raise ValueError(f"Size differs from model lock: {path}")
    for filename in _strata_required_files(recipe.draft == "on"):
        require_file(root / filename)


def _check_gguf_preparation(
    lock: dict[str, Any], versions: dict[str, Any], root: Path, recipe: Recipe
) -> None:
    """Verify the preparation receipt and the artifacts of every GGUF folder."""
    entries = [(lock["target"]["directory"], lock["target"], False)]
    if recipe.draft == "on":
        entries.append((lock["conversion"]["directory"], lock["draft"], True))
    for directory, spec, converted in entries:
        folder = root / directory
        receipt = read_json(folder / "prepared.json")
        if receipt.get("source") != spec:
            raise ValueError(f"Model lock differs from preparation receipt: {folder}")
        checksums = receipt.get("sha256")
        if not isinstance(checksums, dict) or not checksums:
            raise ValueError(f"Missing artifact checksums: {folder}")
        if converted:
            _check_conversion_receipt(receipt, lock, versions, checksums, folder)
        elif not set(spec["files"]).issubset(checksums):
            raise ValueError(f"Incomplete target manifest: {folder}")
        require_file(folder / "config.json")
        for filename in checksums:
            require_file(folder / filename)


def _check_conversion_receipt(
    receipt: dict[str, Any],
    lock: dict[str, Any],
    versions: dict[str, Any],
    checksums: dict[str, Any],
    folder: Path,
) -> None:
    """Verify a converted draft folder against the conversion lock."""
    arguments = lock["conversion"]["arguments"]
    if (
        receipt.get("build") != versions
        or receipt.get("arguments", [])[-len(arguments) :] != arguments
    ):
        raise ValueError(f"Draft conversion lock differs: {folder}")
    if not any(name.endswith(".safetensors") for name in checksums):
        raise ValueError(f"Missing converted weights: {folder}")


def check_configuration(recipe: Recipe) -> Finding:
    """Compare native port/model paths and Pi metadata with the recipe's locks."""
    try:
        folder = recipe.directory / "config"
        lock = read_json(folder / "models.lock.json")
        root = Path("/models") / recipe.data_subpath
        if recipe.adapter == "strata":
            port, model = _strata_endpoints(folder, lock, root, recipe)
        else:
            try:
                import yaml
            except ImportError:
                return Finding(
                    "Configuration",
                    "WARN",
                    "TabbyAPI YAML check needs PyYAML; use the repository .venv Python "
                    "(see development setup).",
                )
            port, model = _tabby_endpoints(folder, lock, root, recipe, yaml)
        if port != recipe.port:
            raise ValueError("Native port differs from launch.json; align the container ports")
        context_mismatch = _pi_metadata(folder, port, model, recipe)
        if context_mismatch is not None:
            return context_mismatch
        return Finding("Configuration", "PASS", "Model paths, API port, and Pi metadata agree")
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        return Finding("Configuration", "FAIL", f"{error}. Review config/ files and setup.md.")


def _strata_endpoints(
    folder: Path, lock: dict[str, Any], root: Path, recipe: Recipe
) -> tuple[int, str]:
    """Port and model ID strata is configured with, checked against the locked model paths."""
    native = read_json(folder / "strata.json")
    port, model = native["port"], native["model_name"]
    args = native["args"]
    files = {str(root / "models" / item["path"]) for item in lock["files"]}
    for flag in ("--native", "--ple-gguf"):
        if args[args.index(flag) + 1] not in files:
            raise ValueError(f"{flag} is not a locked model path")
    for flag, suffix in (("--pack", "packs/iq3_xxs"), ("--mtp", "mtp/rt")):
        if args[args.index(flag) + 1] != str(root / suffix):
            raise ValueError(f"{flag} differs from the preparation directory")
    if native["tokenizer"] != str(root / "packs/iq3_xxs/tokenizer"):
        raise ValueError("Tokenizer differs from the preparation directory")
    if recipe.vision == "cpu" and native.get("vision", {}).get("mmproj") not in files:
        raise ValueError("Vision projector is not a locked model path")
    return port, model


def _tabby_endpoints(
    folder: Path, lock: dict[str, Any], root: Path, recipe: Recipe, yaml: ModuleType
) -> tuple[int, str]:
    """Port and model ID TabbyAPI is configured with, checked against the locked directories."""
    try:
        native = yaml.safe_load((folder / "tabby.yml").read_text())
    except yaml.YAMLError as error:
        raise ValueError(f"Invalid tabby.yml: {error}") from error
    port, model = native["network"]["port"], native["model"]["model_name"]
    if Path(native["model"]["model_dir"]) / model != root / lock["target"]["directory"]:
        raise ValueError("Target path differs from the preparation directory")
    if recipe.draft == "on":
        draft = native["draft_model"]
        if (
            Path(draft["draft_model_dir"]) / draft["draft_model_name"]
            != root / lock["conversion"]["directory"]
        ):
            raise ValueError("Draft path differs from the preparation directory")
    return port, model


def _pi_metadata(folder: Path, port: int, model: str, recipe: Recipe) -> Finding | None:
    """Require a Pi provider to serve that model on that port; warn when the context differs."""
    providers = read_json(folder / "pi.models.json")["providers"]
    matching = [
        item
        for provider in providers.values()
        if urlsplit(provider["baseUrl"]).port == port
        for item in provider["models"]
        if item["id"] == model
    ]
    if not matching:
        raise ValueError("Pi model ID or API port differs from the server")
    if any(item["contextWindow"] != recipe.context for item in matching):
        return Finding(
            "Configuration",
            "WARN",
            "Pi context differs from launch defaults; match it to your actual --context "
            "(see setup.md).",
        )
    return None


def diagnose(recipe: Recipe, models: Path, *, devices: Path = Path("/dev")) -> list[Finding]:
    """Collect independent host and recipe checks without modifying files or running images."""
    docker = inspect_command(
        "Docker",
        ["version", "--format", "{{.Server.Version}}"],
        "Check Docker installation/service; re-run to refresh sudo credentials if they timed out.",
    )
    findings = [docker]
    if docker.status == "PASS":
        findings.append(
            inspect_command(
                "Image",
                ["image", "inspect", recipe.image, "--format", "{{.Id}}"],
                "Build the image using the runtime guide.",
            )
        )
    else:
        findings.append(Finding("Image", "SKIP", "Docker access is required"))
    try:
        nodes = [devices / "kfd", *sorted((devices / "dri").glob("renderD*"))]
        if len(nodes) < 2 or any(not stat.S_ISCHR(node.stat().st_mode) for node in nodes):
            raise ValueError("AMD character devices /dev/kfd and /dev/dri/renderD* are required")
        findings.append(
            Finding(
                "AMD devices", "PASS", "Device nodes present; launcher supplies their group IDs"
            )
        )
    except (OSError, ValueError) as error:
        findings.append(
            Finding("AMD devices", "FAIL", f"{error}. Check the host AMD driver and device nodes.")
        )
    findings.extend([check_configuration(recipe), check_prepared(recipe, models)])
    return findings
