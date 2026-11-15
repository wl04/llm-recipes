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
        with (
            pytest.raises(SystemExit, match="already running"),
            prepare_models.preparation_lock(tmp_path),
        ):
            pass


def test_model_root_derives_from_recipe_folder_name(tmp_path: Path) -> None:
    import json

    recipe = tmp_path / "recipes/my-model"
    (recipe / "config").mkdir(parents=True)
    (recipe / "config/launch.json").write_text(json.dumps({"runtime": "exllamav3-tabbyapi"}))
    assert (
        prepare_models.model_root(recipe, tmp_path / "models")
        == tmp_path / "models/recipes/my-model"
    )


def test_model_root_rejects_undeclarable_recipe_name(tmp_path: Path) -> None:
    import json

    recipe = tmp_path / "recipes/Outside"
    (recipe / "config").mkdir(parents=True)
    (recipe / "config/launch.json").write_text(json.dumps({"runtime": "exllamav3-tabbyapi"}))
    with pytest.raises(ValueError, match="recipe folder name"):
        prepare_models.model_root(recipe, tmp_path / "models")
