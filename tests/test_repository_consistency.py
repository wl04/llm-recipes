"""Check contracts between checked-in recipes, runtimes, and authoring templates."""

import json
import shutil
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

import generate_configurations as gen
import pytest
import yaml
from baseline import schema
from baseline_data import sample_results
from install import RUNTIME_REQUIREMENTS
from launcher import discover_recipes

ROOT = Path(__file__).resolve().parents[1]
RECIPES = discover_recipes(ROOT / "recipes")


def test_runtime_dependencies_match_pins_in_project_installer_and_dev_requirements() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    development_pins = set((ROOT / "dev-requirements.txt").read_text().splitlines())
    project_pins = set(project["dependencies"])

    assert project_pins == set(RUNTIME_REQUIREMENTS), "Installer pins must match pyproject.toml"
    assert project_pins <= development_pins, "Development must use the same runtime pins"


@pytest.mark.parametrize("name", sorted(RECIPES))
def test_recipe_matches_preparation_and_client_with_native_configuration(name: str) -> None:
    recipe = RECIPES[name]
    config = recipe.directory / "config"
    lock = json.loads((config / "models.lock.json").read_text())
    root = Path("/models") / "recipes" / recipe.name
    if recipe.adapter == "strata":
        native = json.loads((config / "strata.json").read_text())
        port, model = native["port"], native["model_name"]
        args = native["args"]
        assert int(args[args.index("--max-context") + 1]) == recipe.context
        locked_files = {root / "models" / item["path"] for item in lock["files"]}
        for flag in ("--native", "--ple-gguf"):
            assert Path(args[args.index(flag) + 1]) in locked_files
        assert Path(native["vision"]["mmproj"]) in locked_files
        assert Path(args[args.index("--pack") + 1]) == root / "packs/iq3_xxs"
        assert Path(args[args.index("--mtp") + 1]) == root / "mtp/rt"
        assert Path(native["tokenizer"]) == root / "packs/iq3_xxs/tokenizer"
    else:
        native = yaml.safe_load((config / "tabby.yml").read_text())
        port, model = native["network"]["port"], native["model"]["model_name"]
        assert native["model"]["max_seq_len"] == recipe.context
        assert Path(native["model"]["model_dir"]) / model == root / lock["target"]["directory"]
        draft = native["draft_model"]
        assert (
            Path(draft["draft_model_dir"]) / draft["draft_model_name"]
            == root / lock["conversion"]["directory"]
        )
    assert port == recipe.port
    providers = json.loads((config / "pi.models.json").read_text())["providers"]
    assert any(
        urlsplit(provider["baseUrl"]).port == port
        and any(item["id"] == model for item in provider["models"])
        for provider in providers.values()
    )


@pytest.mark.parametrize("runtime", sorted((ROOT / "runtimes").iterdir()), ids=lambda p: p.name)
def test_build_matches_locked_base_image_for_runtime(runtime: Path) -> None:
    lock = json.loads((runtime / "container/versions.lock.json").read_text())
    dockerfile = (runtime / "container/Dockerfile").read_text()

    assert f"FROM {lock['base_image']}\n" in dockerfile


@pytest.mark.parametrize("container", [False, True], ids=["desktop", "container"])
def test_templates_generate_current_guides_for_new_recipe(tmp_path: Path, container: bool) -> None:
    recipe = tmp_path / "model-format-hardware-memory"
    shutil.copytree(ROOT / "templates/recipe", recipe)
    if container:
        shutil.copytree(ROOT / "templates/container", recipe, dirs_exist_ok=True)
    result = recipe / "001-2026-11-13-check"
    (recipe / "NNN-YYYY-MM-DD-description").rename(result)
    summary = result / "summary.md"
    summary.write_text(summary.read_text().replace("NNN · YYYY-MM-DD", "001 · 2026-11-13"))

    path, _, rendered = gen.update(result)
    path.write_text(rendered)
    index, _, rendered_index = gen.update_index(recipe)
    index.write_text(rendered_index)

    assert gen.update(result)[1] == gen.update(result)[2]
    assert gen.update_index(recipe)[1] == gen.update_index(recipe)[2]
    assert ("[Build and run](../setup.md)" in rendered) == container
    assert "[Configuration](001-2026-11-13-check/configuration.md)" in rendered_index


def test_baseline_summary_template_renders_results_and_is_index_compatible(tmp_path: Path) -> None:
    recipe = tmp_path / "model-format-hardware-memory"
    shutil.copytree(ROOT / "templates/recipe", recipe)
    result = recipe / "002-2026-11-13-baseline"
    (recipe / "NNN-YYYY-MM-DD-description").rename(result)
    template = (recipe / "baseline-summary.md").read_text()
    (result / "summary.md").write_text(template.replace("NNN · YYYY-MM-DD", "002 · 2026-11-13"))
    (result / "results.json").write_text(schema.dump_results(sample_results()))

    path, _, rendered = gen.update_summary(result)
    path.write_text(rendered)

    assert gen.update_summary(result)[1] == gen.update_summary(result)[2]
    assert "## Baseline results" in rendered
    assert gen.update_index(recipe)[2].count("002 · 2026-11-13 — Baseline") == 1
