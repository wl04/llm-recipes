"""Resolve the model data directory declared by a Strata recipe."""

import json
import re
from pathlib import Path


def recipe_paths(recipe: Path) -> tuple[Path, str]:
    """Validate the runtime selection and return configuration and external data paths."""
    config = recipe / "config"
    manifest = json.loads((config / "launch.json").read_text())
    if manifest.get("runtime") != "strata":
        raise ValueError("Preparation and serving require a Strata recipe")
    folder = manifest.get("data_directory", "")
    if not isinstance(folder, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", folder):
        raise ValueError("Strata data_directory must be a single directory name")
    return config, folder
