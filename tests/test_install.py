"""Tests for machine roots and runtime installation."""

import json
import subprocess
from pathlib import Path

import install as install_module
import paths
import pytest
from install import install
from launcher import LaunchOptions, discover_recipes, start_command

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Point both roots and HOME at a sandbox tree."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("LLM_RECIPES_HOME", raising=False)
    monkeypatch.delenv("LLM_RECIPES_RUNTIME", raising=False)
    return {
        "tmp": tmp_path,
        "home": tmp_path / "home",
        "data": tmp_path / "home/llm-recipes",
        "runtime": tmp_path / "home/.llm-recipes",
    }


def test_paths_default_to_home_llm_recipes_and_runtime_prefix(roots: dict[str, Path]) -> None:
    assert paths.data_home() == roots["data"]
    assert paths.runtime_prefix() == roots["runtime"]
    assert paths.recipe_data_dir(roots["data"], "model-x") == roots["data"] / "recipes/model-x"
    assert paths.logs_dir(roots["data"], "coding") == roots["data"] / "logs/coding"


def test_paths_honor_environment_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_RECIPES_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("LLM_RECIPES_RUNTIME", str(tmp_path / "app"))

    assert paths.data_home() == tmp_path / "data"
    assert paths.runtime_prefix() == tmp_path / "app"


def test_recipe_data_directory_derives_from_recipe_identifier(tmp_path: Path) -> None:
    runtime = tmp_path / "runtimes/strata"
    (runtime / "scripts").mkdir(parents=True)
    (runtime / "scripts/serve.py").write_text("")
    (runtime / "runtime.json").write_text(
        json.dumps({"adapter": "strata", "engine": "strata", "image": "local/img:1"})
    )
    folder = tmp_path / "recipes/some-model" / "config"
    folder.mkdir(parents=True)
    (folder / "launch.json").write_text(
        json.dumps(
            {"runtime": "strata", "port": 8080, "context": 4096, "draft": "off", "vision": "off"}
        )
    )

    recipe = discover_recipes(tmp_path / "recipes")["some-model"]

    assert recipe.data_subpath == Path("recipes/some-model")


def test_models_mount_contains_no_code_directories() -> None:
    recipes = discover_recipes(REPO / "recipes")
    recipe = recipes["qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram"]

    command = start_command(
        recipe,
        LaunchOptions(
            recipe.name, Path("/data/models"), Path("/data/logs"), 131072, "on", "cpu", 8080
        ),
        groups=[],
        uid=1000,
        gid=1000,
    )

    models_mounts = [
        part
        for part in command
        if part.startswith("type=bind") and part.endswith("dst=/models,readonly")
    ]
    assert [str(Path("/data/models"))] == [
        mount.removeprefix("type=bind,src=").split(",dst=")[0] for mount in models_mounts
    ]
    assert not any(str(REPO) in part for part in models_mounts)


def make_checkout(root: Path) -> None:
    (root / "scripts").mkdir(parents=True)
    (root / "scripts/launch.py").write_text("print('launch')\n")
    (root / "recipes/alpha").mkdir(parents=True)
    (root / "runtimes").mkdir()
    (root / "assets").mkdir()
    (root / "templates").mkdir()
    (root / "tests").mkdir()
    (root / "tests/test_x.py").write_text("")
    (root / ".venv").mkdir()
    (root / "pyproject.toml").write_text("")


def test_install_copies_runtime_subset_and_writes_version_stamp(
    roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkout = tmp_path / "checkout"
    make_checkout(checkout)
    monkeypatch.setattr(install_module, "running_instances", list)

    code = install(checkout, roots["runtime"], force=False, with_dependencies=False)

    app = roots["runtime"] / "app"
    assert code == 0
    assert (app / "scripts/launch.py").is_file()
    assert (app / "recipes/alpha").is_dir()
    assert not (app / "tests").exists()
    assert not (app / ".venv").exists()
    stamp = json.loads((app / "VERSION").read_text())
    assert stamp["repo_commit"] is None
    assert stamp["installed_at"]
    shim = (roots["runtime"] / "bin/llm-recipes").read_text()
    assert str(app / ".venv/bin/python") in shim
    assert (roots["home"] / ".local/bin/llm-recipes").is_symlink()


def test_install_refuses_swap_with_running_instances(
    roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkout = tmp_path / "checkout"
    make_checkout(checkout)
    monkeypatch.setattr(install_module, "running_instances", lambda: ["llm-recipes-alpha"])

    code = install(checkout, roots["runtime"], force=False, with_dependencies=False)

    assert code == 1
    assert not (roots["runtime"] / "app").exists()


def test_install_force_proceeds_and_keeps_previous_snapshot(
    roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkout = tmp_path / "checkout"
    make_checkout(checkout)
    monkeypatch.setattr(install_module, "running_instances", lambda: ["llm-recipes-alpha"])

    assert install(checkout, roots["runtime"], force=True, with_dependencies=False) == 0
    (checkout / "scripts/launch.py").write_text("print('second')\n")
    assert install(checkout, roots["runtime"], force=True, with_dependencies=False) == 0

    assert (roots["runtime"] / "app/scripts/launch.py").read_text() == "print('second')\n"
    assert (roots["runtime"] / "app.prev/scripts/launch.py").read_text() == "print('launch')\n"


def test_repository_revision_falls_back_to_version_stamp_without_git(
    tmp_path: Path,
) -> None:
    import baseline.host as host

    (tmp_path / "VERSION").write_text(
        json.dumps({"repo_commit": "a" * 40, "installed_at": "x", "version": "1"})
    )

    def failing_git(_command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(_command, returncode=1, stdout="", stderr="")

    assert host.repository_revision(tmp_path, run=failing_git) == {
        "commit": "a" * 40,
        "dirty": False,
        "source": "install",
    }


def test_main_lists_only_install_in_command_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as result:
        install_module.main(["--help"])

    assert result.value.code == 0
    assert "{install}" in capsys.readouterr().out
