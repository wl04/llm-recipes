"""Recipe identity and reusable launcher operations."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from launcher import LaunchOptions, discover_recipes, instance_name, run_command, start_command


def write_recipe(root: Path, name: str) -> None:
    config = root / name / "config"
    config.mkdir(parents=True)
    (config / "launch.json").write_text(
        json.dumps(
            {
                "adapter": "tabbyapi",
                "engine": "exllamav3",
                "image": "local/test:1",
                "port": 5000,
                "context": 4096,
                "draft": "on",
                "vision": "off",
            }
        )
    )


def test_discover_returns_distinct_recipes_with_shared_adapter(tmp_path: Path) -> None:
    write_recipe(tmp_path, "model-a")
    write_recipe(tmp_path, "model-b")
    (tmp_path / "desktop").mkdir()

    recipes = discover_recipes(tmp_path)

    assert set(recipes) == {"model-a", "model-b"}
    assert recipes["model-a"].adapter == recipes["model-b"].adapter == "tabbyapi"
    assert instance_name(recipes["model-a"].name) != instance_name(recipes["model-b"].name)


def test_discover_rejects_unknown_adapter(tmp_path: Path) -> None:
    write_recipe(tmp_path, "model")
    path = tmp_path / "model/config/launch.json"
    path.write_text(path.read_text().replace("tabbyapi", "unknown"))

    with pytest.raises(ValueError, match="adapter"):
        discover_recipes(tmp_path)


def test_start_labels_recipe_and_named_instance(tmp_path: Path) -> None:
    write_recipe(tmp_path, "model")
    recipe = discover_recipes(tmp_path)["model"]
    options = LaunchOptions("coding", tmp_path, tmp_path / "logs", 131072, "on", "on", 5001)

    command = start_command(recipe, options, groups=[109], uid=1000, gid=1000)

    assert "llm-recipes-coding" in command
    assert "io.llm-recipes.recipe=model" in command
    assert "io.llm-recipes.instance=coding" in command
    assert "127.0.0.1:5001:5000" in command


def test_run_returns_failure_without_replacing_process() -> None:
    with patch("launcher.subprocess.run") as run:
        run.return_value.returncode = 17
        result = run_command(["false"])

    assert result == 17


def test_instance_rejects_paths() -> None:
    with pytest.raises(ValueError, match="instance"):
        instance_name("../coding")


@pytest.mark.parametrize("field,value", [("port", True), ("context", 1025), ("vision", "cpu")])
def test_discover_rejects_invalid_defaults(tmp_path: Path, field: str, value: object) -> None:
    write_recipe(tmp_path, "model")
    path = tmp_path / "model/config/launch.json"
    config = json.loads(path.read_text())
    config[field] = value
    path.write_text(json.dumps(config))

    with pytest.raises(ValueError):
        discover_recipes(tmp_path)


def test_start_keeps_instances_distinct_for_same_recipe(tmp_path: Path) -> None:
    write_recipe(tmp_path, "model")
    recipe = discover_recipes(tmp_path)["model"]
    first = LaunchOptions("coding", tmp_path, tmp_path / "coding", 4096, "on", "off", 5000)
    second = LaunchOptions("review", tmp_path, tmp_path / "review", 4096, "on", "off", 5001)

    first_command = start_command(recipe, first, groups=[], uid=1000, gid=1000)
    second_command = start_command(recipe, second, groups=[], uid=1000, gid=1000)

    assert "llm-recipes-coding" in first_command
    assert "llm-recipes-review" in second_command
    assert "127.0.0.1:5000:5000" in first_command
    assert "127.0.0.1:5001:5000" in second_command
    assert f"type=bind,src={tmp_path}/coding,dst=/logs" in first_command
    assert f"type=bind,src={tmp_path}/review,dst=/logs" in second_command
