"""Machine-local roots: the data home and the private application prefix.

``~/llm-recipes`` is the data root only — prepared models, shared cache,
baseline runs, and per-instance logs; the ``/models`` container mount points
at it, so it never holds code. ``~/.llm-recipes`` is the app-owned prefix that
holds the installed runtime snapshot, its venv, and command shims. Both roots
are overridable through the environment for tests and unusual machines.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DATA_HOME_ENV = "LLM_RECIPES_HOME"
RUNTIME_PREFIX_ENV = "LLM_RECIPES_RUNTIME"
DATA_DIRNAME = "llm-recipes"
RUNTIME_DIRNAME = ".llm-recipes"
RECIPES_SUBPATH = Path("recipes")
CACHE_DIRNAME = ".cache"
LOGS_DIRNAME = "logs"
BASELINES_DIRNAME = "baselines"


def data_home() -> Path:
    """Data root holding ``recipes/``, ``.cache/``, ``baselines/``, ``logs/``."""
    override = os.environ.get(DATA_HOME_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / DATA_DIRNAME


def runtime_prefix() -> Path:
    """App-private prefix with ``app/``, ``VERSION``, and ``bin/`` shims."""
    override = os.environ.get(RUNTIME_PREFIX_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / RUNTIME_DIRNAME


def recipe_data_dir(models_root: Path, recipe_name: str) -> Path:
    """External data folder of one recipe under a models root."""
    return models_root / RECIPES_SUBPATH / recipe_name


def version_stamp(root: Path) -> dict[str, object] | None:
    """``VERSION`` stamp of an installed snapshot: revision without a git checkout.

    Returns the installer's ``{repo_commit, installed_at, version}`` document as
    ``{commit, dirty, source}``, or ``None`` when the stamp is absent or unreadable.
    """
    try:
        stamp = json.loads((root / "VERSION").read_text())
    except (OSError, ValueError):
        return None
    commit = stamp.get("repo_commit")
    if not isinstance(commit, str) or not commit.strip():
        return None
    return {"commit": commit.strip(), "dirty": False, "source": "install"}


def logs_dir(models_root: Path, instance: str) -> Path:
    """Persistent log directory (and ``facts.json`` home) of one instance."""
    return models_root / LOGS_DIRNAME / instance


def cache_dir(models_root: Path) -> Path:
    """Shared HF/triton/comgr cache directory mounted at ``/cache``."""
    return models_root / CACHE_DIRNAME


def baselines_dir(models_root: Path) -> Path:
    """Parent directory of baseline run outputs."""
    return models_root / BASELINES_DIRNAME
