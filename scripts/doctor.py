"""Read-only workstation diagnostics for prepared container recipes."""

import json
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
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


def check_prepared(recipe: Recipe, models: Path) -> Finding:
    """Check locked preparation metadata and artifacts for the recipe's default capabilities."""
    try:
        lock = read_json(recipe.directory / "config/models.lock.json")
        versions = read_json(recipe.runtime_directory / "container/versions.lock.json")
        root = models / recipe.data_directory
        if recipe.adapter == "strata":
            if read_json(root / "prepared.json") != {"models": lock, "image": versions}:
                raise ValueError("Preparation receipt differs from model or runtime lock")
            for item in lock["files"]:
                path = root / "models" / item["path"]
                require_file(path)
                if path.stat().st_size != item["size_bytes"]:
                    raise ValueError(f"Size differs from model lock: {path}")
            files = [
                "packs/iq3_xxs/native_experts.txt",
                "packs/iq3_xxs/index.txt",
                "packs/iq3_xxs/dense.bin",
                "packs/iq3_xxs/tokenizer/tokenizer.json",
                "packs/iq3_xxs/tokenizer/chat_template.jinja",
                "packs/iq3_xxs/tokenizer/vocab.json",
            ]
            if recipe.draft == "on":
                files += [
                    f"mtp/rt/{name}"
                    for name in ("experts.bin", "dense.bin", "dense.txt", "draft_vocab.bin")
                ]
            for filename in files:
                require_file(root / filename)
        else:
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
                    arguments = lock["conversion"]["arguments"]
                    if (
                        receipt.get("build") != versions
                        or receipt.get("arguments", [])[-len(arguments) :] != arguments
                    ):
                        raise ValueError(f"Draft conversion lock differs: {folder}")
                    if not any(name.endswith(".safetensors") for name in checksums):
                        raise ValueError(f"Missing converted weights: {folder}")
                elif not set(spec["files"]).issubset(checksums):
                    raise ValueError(f"Incomplete target manifest: {folder}")
                require_file(folder / "config.json")
                for filename in checksums:
                    require_file(folder / filename)
        return Finding("Prepared models", "PASS", f"Metadata and required artifacts: {root}")
    except (OSError, ValueError, KeyError, TypeError) as error:
        return Finding(
            "Prepared models", "FAIL", f"{error}. Follow this recipe's setup.md preparation steps."
        )


def check_configuration(recipe: Recipe) -> Finding:
    """Compare native port/model paths and Pi metadata with the recipe's locks."""
    try:
        folder = recipe.directory / "config"
        lock = read_json(folder / "models.lock.json")
        root = Path("/models") / recipe.data_directory
        if recipe.adapter == "strata":
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
        if port != recipe.port:
            raise ValueError("Native port differs from launch.json; align the container ports")
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
        return Finding("Configuration", "PASS", "Model paths, API port, and Pi metadata agree")
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        return Finding("Configuration", "FAIL", f"{error}. Review config/ files and setup.md.")


def diagnose(recipe: Recipe, models: Path, *, devices: Path = Path("/dev")) -> list[Finding]:
    """Collect independent host and recipe checks without modifying files or running images."""
    docker = inspect_command(
        "Docker",
        ["version", "--format", "{{.Server.Version}}"],
        "Check Docker installation/service; run sudo -v if authentication expired, then retry.",
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
