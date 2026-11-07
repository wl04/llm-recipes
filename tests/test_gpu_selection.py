"""Tests for the RX 9070 XT selection shared by the recipe serving scripts."""

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

from gpu import GPU_NAME, select_device  # noqa: E402


def test_select_device_returns_matching_index() -> None:
    names = ["AMD Radeon RX 7800 XT", "AMD Radeon RX 9070 XT"]

    assert select_device(names) == 1


def test_select_device_fails_when_multiple_gpus_match() -> None:
    names = [f"AMD Radeon {GPU_NAME}" for _ in range(2)]

    with pytest.raises(RuntimeError, match="Expected one"):
        select_device(names)


def test_select_device_fails_when_no_gpu_matches() -> None:
    names = ["AMD Radeon RX 7800 XT"]

    with pytest.raises(RuntimeError, match="Expected one"):
        select_device(names)
