"""Tests for the model preparation lock in prepare_models.py."""

import fcntl
import sys
from pathlib import Path

import pytest

RECIPE_SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / "recipes"
    / "qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram"
    / "scripts"
)
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
