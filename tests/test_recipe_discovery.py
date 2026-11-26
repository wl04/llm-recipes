"""Recipe identity and reusable launcher operations."""

import json
from pathlib import Path
from unittest.mock import patch

import launch
import pytest
from launcher import (
    LaunchOptions,
    discover_recipes,
    gpu_access_args,
    instance_name,
    run_command,
    start_command,
)


def write_recipe(root: Path, name: str) -> None:
    for runtime, adapter, engine in (
        ("exllamav3-tabbyapi", "tabbyapi", "exllamav3"),
        ("strata", "strata", "strata"),
    ):
        folder = root.parent / "runtimes" / runtime
        (folder / "scripts").mkdir(parents=True, exist_ok=True)
        (folder / "scripts/serve.py").write_text("# serving entry point")
        (folder / "runtime.json").write_text(
            json.dumps({"adapter": adapter, "engine": engine, "image": "local/test:1"})
        )
    config = root / name / "config"
    config.mkdir(parents=True)
    (config / "launch.json").write_text(
        json.dumps(
            {
                "runtime": "exllamav3-tabbyapi",
                "port": 5000,
                "context": 4096,
                "draft": "on",
                "vision": "off",
            }
        )
    )


def test_discover_returns_distinct_recipes_with_shared_adapter(tmp_path: Path) -> None:
    write_recipe(tmp_path / "recipes", "model-a")
    write_recipe(tmp_path / "recipes", "model-b")
    (tmp_path / "recipes/desktop").mkdir()

    recipes = discover_recipes(tmp_path / "recipes")

    assert set(recipes) == {"model-a", "model-b"}
    assert recipes["model-a"].adapter == recipes["model-b"].adapter == "tabbyapi"
    assert instance_name(recipes["model-a"].name) != instance_name(recipes["model-b"].name)


@pytest.fixture
def adopted_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    prefix = tmp_path / "install"
    installed, trial = prefix / "app/recipes", tmp_path / "trial"
    monkeypatch.setenv("LLM_RECIPES_RUNTIME", str(prefix))
    write_recipe(installed, "model")
    write_recipe(trial / "recipes", "model")
    selections = prefix / "selections"
    selections.mkdir()
    (selections / "model.json").write_text(json.dumps([str(trial)]))
    return installed, trial


def test_list_shows_adopted_release_and_exact_image(
    adopted_checkout: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    installed, trial = adopted_checkout
    descriptor = trial / "runtimes/exllamav3-tabbyapi/runtime.json"
    settings = json.loads(descriptor.read_text())
    settings.update(
        engine_version="1.0.2", engine_source_version="v1.1.0", image="recipes/model:trial"
    )
    descriptor.write_text(json.dumps(settings))
    monkeypatch.setattr(launch, "ROOT", installed.parent)

    assert launch.main(["list"]) == 0
    row = capsys.readouterr().out.splitlines()[1]
    assert "exllamav3 v1.1.0" in row
    assert "recipes/model:trial" in row

    assert launch.main(["list", "--json"]) == 0
    (record,) = json.loads(capsys.readouterr().out)
    assert record["engine_source_version"] == "v1.1.0"
    assert record["engine_version"] == "1.0.2"
    assert record["image"] == "recipes/model:trial"


def test_discover_uses_installed_recipe_when_adopted_manifest_disappears_at_read(
    adopted_checkout: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    installed, trial = adopted_checkout
    manifest = trial / "recipes/model/config/launch.json"
    read_text = Path.read_text

    def read_after_removal(path: Path) -> str:
        if path == manifest:
            manifest.unlink()
        return read_text(path)

    monkeypatch.setattr(Path, "read_text", read_after_removal)

    recipe = discover_recipes(installed)["model"]

    assert recipe.directory == installed / "model"
    assert recipe.runtime_directory == installed.parent / "runtimes/exllamav3-tabbyapi"


def test_discover_reports_missing_adopted_runtime_when_manifest_is_present(
    adopted_checkout: tuple[Path, Path],
) -> None:
    installed, trial = adopted_checkout
    descriptor = trial / "runtimes/exllamav3-tabbyapi/runtime.json"
    descriptor.unlink()

    with pytest.raises(ValueError, match=r"runtime\.json") as failure:
        discover_recipes(installed)

    assert str(descriptor) in str(failure.value)


def test_discover_rejects_unknown_adapter(tmp_path: Path) -> None:
    write_recipe(tmp_path / "recipes", "model")
    path = tmp_path / "runtimes/exllamav3-tabbyapi/runtime.json"
    path.write_text(path.read_text().replace("tabbyapi", "unknown"))

    with pytest.raises(ValueError, match="adapter"):
        discover_recipes(tmp_path / "recipes")


def test_start_labels_recipe_and_named_instance(tmp_path: Path) -> None:
    write_recipe(tmp_path / "recipes", "model")
    recipe = discover_recipes(tmp_path / "recipes")["model"]
    options = LaunchOptions("coding", tmp_path, tmp_path / "logs", 131072, "on", "on", 5001)

    command = start_command(recipe, options, groups=[109], uid=1000, gid=1000)

    assert "llm-recipes-coding" in command
    assert "io.llm-recipes.recipe=model" in command
    assert "io.llm-recipes.instance=coding" in command
    assert "127.0.0.1:5001:5000" in command


def test_gpu_access_grants_each_group_once_before_the_devices() -> None:
    arguments = gpu_access_args([989, 988, 989])

    assert arguments == [
        "--group-add",
        "988",
        "--group-add",
        "989",
        "--device=/dev/kfd",
        "--device=/dev/dri",
    ]


def test_start_grants_gpu_access_after_the_container_user(tmp_path: Path) -> None:
    write_recipe(tmp_path / "recipes", "model")
    recipe = discover_recipes(tmp_path / "recipes")["model"]
    options = LaunchOptions("coding", tmp_path, tmp_path / "logs", 131072, "on", "off", 5001)

    command = start_command(recipe, options, groups=[989, 988, 989], uid=1000, gid=1000)
    user_index = command.index("--user")
    gpu_arguments = command[command.index("--group-add") : command.index("--publish")]

    assert command[user_index + 1] == "1000:1000"
    assert gpu_arguments == gpu_access_args([989, 988, 989])


def test_run_returns_failure_without_replacing_process() -> None:
    with patch("launcher.subprocess.run") as run:
        run.return_value.returncode = 17
        result = run_command(["false"])

    assert result == 17


def test_instance_rejects_paths() -> None:
    with pytest.raises(ValueError, match="instance"):
        instance_name("../coding")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("port", True, "port must be an integer"),
        ("context", 1025, "multiple of 256"),
        ("vision", "cpu", "vision must be"),
    ],
)
def test_discover_rejects_invalid_defaults(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    write_recipe(tmp_path / "recipes", "model")
    path = tmp_path / "recipes/model/config/launch.json"
    config = json.loads(path.read_text())
    config[field] = value
    path.write_text(json.dumps(config))

    with pytest.raises(ValueError, match=message):
        discover_recipes(tmp_path / "recipes")


def test_start_keeps_instances_distinct_for_same_recipe(tmp_path: Path) -> None:
    write_recipe(tmp_path / "recipes", "model")
    recipe = discover_recipes(tmp_path / "recipes")["model"]
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


def test_discover_accepts_cpu_vision_for_strata(tmp_path: Path) -> None:
    write_recipe(tmp_path / "recipes", "strata-model")
    path = tmp_path / "recipes/strata-model/config/launch.json"
    config = json.loads(path.read_text())
    config.update(runtime="strata", vision="cpu", port=8080)
    path.write_text(json.dumps(config))

    recipe = discover_recipes(tmp_path / "recipes")["strata-model"]
    options = LaunchOptions("coding", tmp_path, tmp_path / "logs", 131072, "on", "cpu", 8081)
    command = start_command(recipe, options, groups=[109], uid=1000, gid=1000)

    assert "127.0.0.1:8081:8080" in command
    assert "memlock=-1:-1" in command
    assert "cpu" in command
    assert "io.llm-recipes.adapter=strata" in command


def test_discover_resolves_two_models_to_one_runtime(tmp_path: Path) -> None:
    runtime = tmp_path / "runtimes/strata"
    (runtime / "scripts").mkdir(parents=True)
    (runtime / "scripts/serve.py").write_text("# serving entry point\n")
    (runtime / "runtime.json").write_text(
        json.dumps({"adapter": "strata", "engine": "strata", "image": "local/strata:1"})
    )
    for name in ("ista", "unsloth"):
        folder = tmp_path / "recipes" / name / "config"
        folder.mkdir(parents=True)
        (folder / "launch.json").write_text(
            json.dumps(
                {
                    "runtime": "strata",
                    "port": 8080,
                    "context": 131072,
                    "draft": "on",
                    "vision": "cpu",
                }
            )
        )
    recipes = discover_recipes(tmp_path / "recipes")
    assert recipes["ista"].runtime_directory == runtime
    assert recipes["unsloth"].runtime_directory == runtime
    assert recipes["ista"].data_subpath == Path("recipes/ista")
    assert recipes["unsloth"].data_subpath == Path("recipes/unsloth")
    command = start_command(
        recipes["unsloth"],
        LaunchOptions("trial", tmp_path, tmp_path / "logs", 131072, "on", "cpu", 8080),
        groups=[],
        uid=1000,
        gid=1000,
    )
    assert f"type=bind,src={runtime},dst=/runtime,readonly" in command
    assert "/runtime/scripts/serve.py" in command
    assert command[-2:] == ["--recipe", "/recipes/unsloth"]
    assert f"type=bind,src={recipes['unsloth'].directory},dst=/recipes/unsloth,readonly" in command


@pytest.mark.parametrize(("field", "value"), [("runtime", "../other")])
def test_discover_rejects_paths_outside_shared_roots(
    tmp_path: Path, field: str, value: str
) -> None:
    write_recipe(tmp_path / "recipes", "model")
    path = tmp_path / "recipes/model/config/launch.json"
    config = json.loads(path.read_text())
    config[field] = value
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match=field):
        discover_recipes(tmp_path / "recipes")


def test_discover_rejects_retired_data_directory_field(tmp_path: Path) -> None:
    write_recipe(tmp_path / "recipes", "model")
    path = tmp_path / "recipes/model/config/launch.json"
    config = json.loads(path.read_text())
    config["data_directory"] = "model-data"
    path.write_text(json.dumps(config))

    with pytest.raises(ValueError, match="expected fields"):
        discover_recipes(tmp_path / "recipes")
