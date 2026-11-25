"""Tests for the model preparation lock in prepare_models.py."""

import fcntl
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

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


@pytest.mark.parametrize("action", ["download", "quantize-draft"])
def test_prepare_wrapper_targets_serving_model_root_for_shipped_recipe(
    tmp_path: Path, action: str
) -> None:
    root = RECIPE_SCRIPTS.parents[2]
    recipe = root / "recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram"
    sudo = tmp_path / "sudo"
    sudo.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
    python = tmp_path / "python3"
    python.write_text(
        '#!/bin/sh\ncase "$1" in\n'
        '  */gpu_access.py) printf "%s\\n" --device=/dev/kfd ;;\n'
        f'  *) exec {shlex.quote(sys.executable)} "$@" ;;\nesac\n'
    )
    for executable in (sudo, python):
        executable.chmod(0o755)
    environment = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}

    result = subprocess.run(
        ["bash", RECIPE_SCRIPTS / "prepare-models.sh", recipe, action, tmp_path / "models"],
        check=True,
        text=True,
        capture_output=True,
        env=environment,
        timeout=10,
    )

    arguments = result.stdout.splitlines()
    container_recipe = Path(arguments[arguments.index("--recipe") + 1])
    assert arguments[-1] == action
    assert f"type=bind,src={recipe},dst={container_recipe},readonly" in arguments
    mounted_recipe = tmp_path / container_recipe.name
    mounted_recipe.symlink_to(recipe, target_is_directory=True)
    prepared = prepare_models.model_root(mounted_recipe, Path("/models"))
    tabby = yaml.safe_load((recipe / "config/tabby.yml").read_text())
    assert prepared == Path(tabby["model"]["model_dir"])
    assert prepared == Path(tabby["draft_model"]["draft_model_dir"])
