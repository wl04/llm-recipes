"""Resolve the model data directory of a Strata recipe from its folder name."""

import json
from pathlib import Path


def recipe_paths(recipe: Path) -> tuple[Path, Path]:
    """Validate the runtime selection and return configuration and data subpath.

    The data subpath mirrors the repository tree: ``recipes/<recipe-id>``,
    relative to the models root (host) or the ``/models`` mount (container).
    """
    config = recipe / "config"
    manifest = json.loads((config / "launch.json").read_text())
    if manifest.get("runtime") != "strata":
        raise ValueError("Preparation and serving require a Strata recipe")
    if not recipe.name or recipe.name != recipe.name.strip("/"):
        raise ValueError("recipe folder name must match the recipe identifier")
    return config, Path("recipes") / recipe.name
