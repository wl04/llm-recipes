"""Tests for the model preparation lock in prepare_models.py."""

import fcntl
import sys
from pathlib import Path

import pytest

RECIPE_SCRIPTS = Path(__file__).resolve().parents[1] / "runtimes" / "exllamav3-tabbyapi" / "scripts"
sys.path.insert(0, str(RECIPE_SCRIPTS))

import prepare_models  # noqa: E402


def test_preparation_lock_allows_when_free(tmp_path: Path) -> None:
    with prepare_models.preparation_lock(tmp_path):
        assert (tmp_path / ".prepare.lock").is_file()


def test_preparation_lock_fails_when_already_held(tmp_path: Path) -> None:
    with (tmp_path / ".prepare.lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        with pytest.raises(SystemExit, match="already running"):
            with prepare_models.preparation_lock(tmp_path):
                pass


def test_model_root_uses_recipe_data_directory(tmp_path: Path) -> None:
    import json

    recipe = tmp_path / "recipe"
    (recipe / "config").mkdir(parents=True)
    (recipe / "config/launch.json").write_text(
        json.dumps({"runtime": "exllamav3-tabbyapi", "data_directory": "other-model"})
    )
    assert prepare_models.model_root(recipe, tmp_path / "models") == tmp_path / "models/other-model"


def test_model_root_rejects_parent_traversal(tmp_path: Path) -> None:
    import json

    (tmp_path / "config").mkdir()
    (tmp_path / "config/launch.json").write_text(
        json.dumps({"runtime": "exllamav3-tabbyapi", "data_directory": "../outside"})
    )
    with pytest.raises(ValueError, match="data_directory"):
        prepare_models.model_root(tmp_path, tmp_path / "models")
