"""Tests for the machine cutover: roots, install, data migration."""

import json
import os
import subprocess
from pathlib import Path

import install as install_module
import paths
import pytest
from install import (
    EXL3_RECIPE,
    ISTA_RECIPE,
    UNSLOTH_RECIPE,
    append_journal,
    install,
    migrate_data,
    move_plan,
)
from launcher import LaunchOptions, discover_recipes, start_command

REPO = Path(__file__).resolve().parent.parent
OLD_MARKERS = "Models" + "/llm-recipes"


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


def test_no_reference_to_old_models_path_remains() -> None:
    offenders = []
    for path in REPO.rglob("*"):
        if not path.is_file() or ".venv" in path.parts or ".git" in path.parts:
            continue
        if path.suffix not in {".py", ".sh", ".md", ".json", ".yml", ".yaml"}:
            continue
        if path.relative_to(REPO).parts[:2] == ("docs", "plans"):
            continue
        if OLD_MARKERS in path.read_text(errors="ignore"):
            offenders.append(str(path.relative_to(REPO)))

    assert offenders == []


def test_models_mount_contains_no_code_directories() -> None:
    recipes = discover_recipes(REPO / "recipes")
    recipe = recipes[ISTA_RECIPE]

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


# ---------------------------------------------------------------- migrate-data

RECIPES = (EXL3_RECIPE, ISTA_RECIPE, UNSLOTH_RECIPE)


def prepare_old_root(old_root: Path) -> None:
    old_root.mkdir(parents=True)
    for name in (".cache", "baselines", "logs"):
        (old_root / name).mkdir()
    for name in ("qwen3.8-27b-exl3-3bpw", "draft-conversion-work"):
        (old_root / name).mkdir()
    (old_root / "qwen3.8-27b-exl3-3bpw/model.safetensors").write_text("weights")
    (old_root / "strata").mkdir()
    (old_root / "strata-unsloth").mkdir()


def prepare_app(prefix: Path, data_root: Path) -> None:
    """Installed snapshot with recipe locks that the moved trees will satisfy."""
    app = prefix / "app"
    (app / "scripts").mkdir(parents=True)
    (app / "scripts/launch.py").write_text("print('doctor stub')\n")
    locks = {
        EXL3_RECIPE: {
            "target": {"directory": "qwen3.8-27b-exl3-3bpw"},
            "draft": {"directory": "draft-conversion-work"},
            "conversion": {
                "directory": "draft-conversion-work",
                "work_directory": "draft-conversion-work",
            },
        },
        ISTA_RECIPE: {"files": [{"path": "one.gguf", "size_bytes": 1}]},
        UNSLOTH_RECIPE: {"files": [{"path": "two.gguf", "size_bytes": 1}]},
    }
    for recipe, lock in locks.items():
        config = app / "recipes" / recipe / "config"
        config.mkdir(parents=True)
        (config / "models.lock.json").write_text(json.dumps(lock))


def test_migrate_data_refuses_without_installed_app(
    roots: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old_root = roots["home"] / "Models" / "llm-recipes"
    prepare_old_root(old_root)

    code = migrate_data(roots["runtime"] / "app", old_root, apply=True)

    assert code == 1
    assert "install the runtime snapshot first" in capsys.readouterr().out
    assert any(old_root.iterdir())


def test_migrate_data_refuses_when_instance_running_or_prepare_lock_held(
    roots: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    old_root = roots["home"] / "Models" / "llm-recipes"
    prepare_old_root(old_root)
    prepare_app(roots["runtime"], paths.data_home())
    for recipe, gguf in ((ISTA_RECIPE, "one.gguf"), (UNSLOTH_RECIPE, "two.gguf")):
        models = old_root / "strata" if recipe == ISTA_RECIPE else old_root / "strata-unsloth"
        (models / "models").mkdir(parents=True, exist_ok=True)
        (models / "models" / gguf).write_text("x")

    monkeypatch.setattr(install_module, "running_instances", lambda: ["llm-recipes-coding"])
    assert migrate_data(roots["runtime"] / "app", old_root, apply=True) == 1
    assert "instances are running" in capsys.readouterr().out

    monkeypatch.setattr(install_module, "running_instances", list)
    (old_root / ".prepare.lock").touch()
    assert migrate_data(roots["runtime"] / "app", old_root, apply=True) == 1
    assert ".prepare.lock" in capsys.readouterr().out
    assert (old_root / "strata").is_dir()


def test_migrate_data_refuses_cross_device_move(
    roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    old_root = roots["home"] / "Models" / "llm-recipes"
    prepare_old_root(old_root)
    prepare_app(roots["runtime"], paths.data_home())
    monkeypatch.setattr(install_module, "running_instances", list)
    monkeypatch.setattr(install_module, "same_device", lambda _a, _b: False)

    code = migrate_data(roots["runtime"] / "app", old_root, apply=True)

    assert code == 1
    assert "cross-device" in capsys.readouterr().out
    assert (old_root / "baselines").is_dir()
    assert not paths.data_home().exists()


def test_migrate_data_never_overwrites_existing_destination(
    roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    old_root = roots["home"] / "Models" / "llm-recipes"
    prepare_old_root(old_root)
    prepare_app(roots["runtime"], paths.data_home())
    (paths.data_home() / "baselines").mkdir(parents=True)
    (paths.data_home() / "baselines/keep.txt").write_text("do not lose me")
    monkeypatch.setattr(install_module, "running_instances", list)

    code = migrate_data(roots["runtime"] / "app", old_root, apply=True)

    assert code == 1
    assert "destination already exists" in capsys.readouterr().out
    assert (paths.data_home() / "baselines/keep.txt").read_text() == "do not lose me"
    assert (old_root / "baselines").is_dir()


def test_migrate_data_dry_run_prints_manifest_without_changes(
    roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    old_root = roots["home"] / "Models" / "llm-recipes"
    prepare_old_root(old_root)
    prepare_app(roots["runtime"], paths.data_home())
    monkeypatch.setattr(install_module, "running_instances", list)

    code = migrate_data(roots["runtime"] / "app", old_root, apply=False)

    printed = capsys.readouterr().out
    assert code == 0
    assert "move: " in printed
    assert "moved: " not in printed
    assert (old_root / "strata").is_dir()
    assert not paths.data_home().exists()
    assert not (roots["runtime"] / "migrate-journal.jsonl").exists()


def test_migrate_data_resumes_after_partial_completion(
    roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    old_root = roots["home"] / "Models" / "llm-recipes"
    prepare_old_root(old_root)
    prepare_app(roots["runtime"], paths.data_home())
    for recipe in (ISTA_RECIPE, UNSLOTH_RECIPE):
        source = old_root / ("strata" if recipe == ISTA_RECIPE else "strata-unsloth")
        (source / "models").mkdir(parents=True, exist_ok=True)
        (source / "models" / ("one.gguf" if recipe == ISTA_RECIPE else "two.gguf")).write_text("x")
    (old_root / "qwen3.8-27b-dflash2-exl3-3bpw").mkdir()
    (old_root / "qwen3.8-27b-dflash2-source").mkdir()
    monkeypatch.setattr(install_module, "running_instances", list)

    # Simulate an interrupted first pass: the logs directory is already moved.
    destination = paths.data_home() / "logs"
    destination.parent.mkdir(parents=True)
    os.rename(old_root / "logs", destination)
    append_journal(roots["runtime"], old_root / "logs", destination)

    code = migrate_data(roots["runtime"] / "app", old_root, apply=True)

    printed = capsys.readouterr().out
    assert code == 0
    assert "skip (journaled)" in printed
    assert destination.is_dir()
    assert not (old_root / "logs").exists()
    assert not old_root.exists()


def test_migrate_data_applies_all_moves_and_cleans_old_root(
    roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    old_root = roots["home"] / "Models" / "llm-recipes"
    prepare_old_root(old_root)
    prepare_app(roots["runtime"], paths.data_home())
    for recipe in (ISTA_RECIPE, UNSLOTH_RECIPE):
        source = old_root / ("strata" if recipe == ISTA_RECIPE else "strata-unsloth")
        (source / "models").mkdir(parents=True, exist_ok=True)
        (source / "models" / ("one.gguf" if recipe == ISTA_RECIPE else "two.gguf")).write_text("x")
    (old_root / "qwen3.8-27b-dflash2-exl3-3bpw").mkdir()
    (old_root / "qwen3.8-27b-dflash2-source").mkdir()
    monkeypatch.setattr(install_module, "running_instances", list)

    code = migrate_data(roots["runtime"] / "app", old_root, apply=True)

    data = paths.data_home()
    assert code == 0
    assert (data / ".cache").is_dir()
    assert (data / "baselines").is_dir()
    assert (data / "logs").is_dir()
    exl3 = data / "recipes" / EXL3_RECIPE
    assert (exl3 / "qwen3.8-27b-exl3-3bpw/model.safetensors").is_file()
    assert (data / "recipes" / ISTA_RECIPE / "models/one.gguf").is_file()
    assert (data / "recipes" / UNSLOTH_RECIPE / "models/two.gguf").is_file()
    assert not old_root.exists()
    assert not (roots["home"] / "Models").exists()
    assert "doctor " in capsys.readouterr().out
    journal = (roots["runtime"] / "migrate-journal.jsonl").read_text()
    assert journal.count('"done": true') == len(move_plan(old_root))


def test_migrate_data_refuses_unmapped_directory(
    roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    old_root = roots["home"] / "Models" / "llm-recipes"
    prepare_old_root(old_root)
    (old_root / "mystery-checkpoints").mkdir()
    prepare_app(roots["runtime"], paths.data_home())
    monkeypatch.setattr(install_module, "running_instances", list)

    code = migrate_data(roots["runtime"] / "app", old_root, apply=True)

    assert code == 1
    assert "mystery-checkpoints" in capsys.readouterr().out
    assert (old_root / "strata").is_dir()
