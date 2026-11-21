"""Exercise the standalone migration against a small preparation on disk."""

import json
import runpy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from doctor import STRATA_DRAFT_FILES, STRATA_PACK_FILES
from launcher import Recipe, discover_recipes

ROOT = Path(__file__).resolve().parents[1]
tool = runpy.run_path(str(ROOT / "tools/migrate_strata_v0213.py"))
VERSION = tool["VERSION"]
migrate = tool["migrate"]


@pytest.fixture
def installation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Recipe, Path, Path]:
    monkeypatch.setenv("LLM_RECIPES_RUNTIME", str(tmp_path / "prefix"))
    recipe = next(r for r in discover_recipes(ROOT / "recipes").values() if r.adapter == "strata")
    assert recipe.runtime == f"strata/releases/{VERSION}"
    recipe = replace(recipe, directory=tmp_path / "checkout")
    (recipe.directory / "config").mkdir(parents=True)
    lock = {"files": [{"path": "model.gguf", "size_bytes": 1}]}
    (recipe.directory / "config/models.lock.json").write_text(json.dumps(lock))
    versions = json.loads((recipe.runtime_directory / "container/versions.lock.json").read_text())
    models = tmp_path / "data"
    root = models / recipe.data_subpath
    (root / "models").mkdir(parents=True)
    (root / "models/model.gguf").write_bytes(b"w")
    for name in (*STRATA_PACK_FILES, *(f"mtp/rt/{name}" for name in STRATA_DRAFT_FILES)):
        file = root / name
        file.parent.mkdir(exist_ok=True, parents=True)
        file.write_bytes(b"x")
    (root / "prepared.json").write_text(json.dumps({"models": lock, "image": versions}))
    return recipe, models, root


@pytest.mark.parametrize("moved", [0, 1, 2, 3])
def test_migrate_preserves_files_and_resumes_at_each_boundary(
    installation: tuple[Recipe, Path, Path], moved: int
) -> None:
    recipe, models, root = installation
    dest = root / "prepared" / VERSION
    weight = root / "models/model.gguf"
    original = weight.stat().st_ino
    pack = (root / "packs").stat().st_ino
    if moved:
        dest.mkdir(parents=True)
    for name in ("packs", "mtp", "prepared.json")[:moved]:
        (root / name).rename(dest / name)

    before = sorted(root.rglob("*"))
    migrate({recipe.name: recipe}, models, False)
    assert sorted(root.rglob("*")) == before
    with patch("subprocess.check_output", return_value=""):
        migrate({recipe.name: recipe}, models, True)
        migrate({recipe.name: recipe}, models, True)

    assert weight.stat().st_ino == original
    assert (dest / "packs").stat().st_ino == pack
    assert (dest / "prepared.json").is_file()
    assert not any((root / name).exists() for name in ("packs", "mtp", "prepared.json"))


@pytest.mark.parametrize("problem", ["conflict", "receipt", "running"])
def test_migrate_refuses_unsafe_preparation_before_moving(
    installation: tuple[Recipe, Path, Path], problem: str
) -> None:
    recipe, models, root = installation
    dest = root / "prepared" / VERSION
    if problem == "conflict":
        (dest / "packs").mkdir(parents=True)
    if problem == "receipt":
        (root / "prepared.json").write_text("{}")

    with (
        patch("subprocess.check_output", return_value="serving" if problem == "running" else ""),
        pytest.raises(ValueError, match=r"Expected exactly one|receipt mismatch|Stop the serving"),
    ):
        migrate({recipe.name: recipe}, models, True)
    assert (root / "packs").is_dir()
    assert (root / "mtp").is_dir()
    assert (root / "prepared.json").is_file()
