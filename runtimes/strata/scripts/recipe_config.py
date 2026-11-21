"""Resolve the model data directory of a Strata recipe from its folder name."""

import json
import re
from pathlib import Path


def recipe_paths(recipe: Path) -> tuple[Path, Path]:
    """Validate the runtime selection and return configuration and data subpath.

    The data subpath mirrors the repository tree: ``recipes/<recipe-id>``,
    relative to the models root (host) or the ``/models`` mount (container).
    """
    config = recipe / "config"
    release_key(config)
    if not recipe.name or recipe.name != recipe.name.strip("/"):
        raise ValueError("recipe folder name must match the recipe identifier")
    return config, Path("recipes") / recipe.name


def release_key(config: Path) -> str:
    manifest_path = config / "launch.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{manifest_path}: invalid JSON at line {error.lineno}: {error.msg}"
        ) from error
    if not isinstance(manifest, dict):
        raise ValueError(f"{manifest_path} must contain a JSON object")
    runtime = manifest.get("runtime")
    if runtime == "strata":
        return ""
    if not isinstance(runtime, str) or not re.fullmatch(
        r"strata/releases/(v[0-9][A-Za-z0-9.-]*)", runtime
    ):
        raise ValueError("Preparation and serving require a Strata recipe")
    return runtime.split("/")[-1]
