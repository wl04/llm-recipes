import json
import shlex
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import upgrade_strata as upgrade
from launcher import local_selections
from paths import data_home, runtime_prefix


def test_candidate_reuses_worktree_and_preserves_local_edits(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.email=a@b",
            "-c",
            "user.name=T",
            "commit",
            "--allow-empty",
            "-qm",
            "initial",
        ],
        check=True,
    )
    candidate = upgrade.worktree(root, "v1.2.3")
    (candidate / "notes").write_text("keep")

    assert upgrade.worktree(root, "v1.2.3") == candidate
    assert (candidate / "notes").read_text() == "keep"
    assert not (root / "notes").exists()


def test_release_preflight_reports_missing_prepare_tool() -> None:
    with pytest.raises(ValueError, match=r"mtp_fetch\.py"):
        upgrade.inspect_source({}, {})


@pytest.mark.parametrize("conflict", [False, True])
def test_existing_image_is_checked_by_id_only_when_lock_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, conflict: bool
) -> None:
    image = "llm-recipes/strata-rdna4:v1.2.3"
    digest = "sha256:" + "f" * 64
    query = Mock(side_effect=[digest, json.dumps({"pin": "other" if conflict else "expected"})])
    run = Mock()
    monkeypatch.setattr(upgrade, "output", query)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(upgrade, "gpu_groups", list)
    monkeypatch.setattr(upgrade, "gpu_access_args", lambda groups: [])

    if conflict:
        with pytest.raises(ValueError, match="image_suffix"):
            upgrade.build_or_check(tmp_path, image, {"pin": "expected"}, 4)
        run.assert_not_called()
    else:
        upgrade.build_or_check(tmp_path, image, {"pin": "expected"}, 4)
        run.assert_called_once_with(["sudo", "docker", "run", "--rm", digest], check=True)


def test_candidate_resumes_generated_inputs_after_reference_update(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    commit = ["git", "-c", "user.email=a@b", "-c", "user.name=T", "commit", "-qm"]
    for path in (upgrade.LOCK, upgrade.DESCRIPTOR):
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text("{}")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run([*commit, "reference"], cwd=root, check=True)
    candidate = upgrade.worktree(root, "v1.2.3")
    for path in (upgrade.LOCK, upgrade.DESCRIPTOR):
        (candidate / path).write_text('{"candidate":true}')
    (root / "guide.md").write_text("updated")
    subprocess.run(["git", "add", "guide.md"], cwd=root, check=True)
    subprocess.run([*commit, "guide update"], cwd=root, check=True)

    assert upgrade.worktree(root, "v1.2.3") == candidate
    assert (candidate / "guide.md").read_text() == "updated"
    assert (candidate / upgrade.LOCK).read_text() == '{"candidate":true}'
    assert (candidate / upgrade.DESCRIPTOR).read_text() == '{"candidate":true}'


@pytest.fixture
def trial_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import shutil

    source = upgrade.ROOT
    root = tmp_path / "reference"
    prefix = tmp_path / "install"
    app = prefix / "app"
    models = tmp_path / "models"
    monkeypatch.setenv("LLM_RECIPES_RUNTIME", str(prefix))
    monkeypatch.setenv("LLM_RECIPES_HOME", str(models))
    monkeypatch.setattr(upgrade, "ROOT", root)
    shutil.copytree(source / upgrade.RUNTIME, root / upgrade.RUNTIME)
    template = next((source / "recipes").glob("*flash-next*")) / "config"
    weights = {"files": [{"path": "shard.gguf", "size_bytes": 1}], "mtp": {}}
    installed_names = ("first-model", "second-model")
    for name in (*installed_names, "catalog-only"):
        config = root / "recipes" / name / "config"
        shutil.copytree(template, config)
        manifest = json.loads((config / "launch.json").read_text())
        manifest["runtime"] = "strata"
        upgrade.save(config / "launch.json", manifest)
        upgrade.save(config / "models.lock.json", weights)
        if name in installed_names:
            shard = models / "recipes" / name / "models/shard.gguf"
            shard.parent.mkdir(parents=True)
            shard.write_bytes(b"x")
    shutil.rmtree(root / upgrade.RUNTIME / "releases", ignore_errors=True)
    shutil.copytree(root, app)
    upgrade.save(app / "VERSION", {"version": "2"})
    subprocess.run(["git", "init", "-qb", "main"], cwd=root, check=True)
    for key, value in (("user.email", "test@example.org"), ("user.name", "Test")):
        subprocess.run(["git", "config", key, value], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
    monkeypatch.setattr(upgrade, "release", lambda *args: ("f" * 40, "e" * 64, "0.1.64"))
    monkeypatch.setattr(upgrade, "base_image", lambda tag: "rocm/dev@sha256:" + "a" * 64)
    return root


def test_adoption_preserves_selections_when_a_predecessor_manifest_is_missing(
    trial_reference: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    options = upgrade.settings(trial_reference / upgrade.RUNTIME / "upgrade.json")
    monkeypatch.setattr(upgrade, "check_ready_recipe", lambda recipe, models: None)
    first, second = "v0.2.18", "v0.2.19"
    upgrade.upgrade(first, options, prepare_only=True)
    upgrade.manage(first, delete=False)
    upgrade.upgrade(second, options, prepare_only=True)
    first_checkout = Path(local_selections("second-model")[-1])
    (first_checkout / upgrade.manifest_path("second-model")).unlink()

    with pytest.raises(ValueError, match=r"second-model.*restore .* or roll back"):
        upgrade.manage(second, delete=False)

    for name in ("first-model", "second-model"):
        assert local_selections(name) == [str(first_checkout)]
    assert "previous" not in json.loads(upgrade.trial_record(second).read_text())


def test_adoption_selects_installed_strata_models_and_delete_restores_each(
    trial_reference: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from doctor import _strata_required_files
    from launcher import discover_recipes

    root = trial_reference
    models = data_home()
    app = runtime_prefix() / "app"
    installed_names = ("first-model", "second-model")
    shard = models / "recipes/second-model/models/shard.gguf"
    weights = json.loads((root / "recipes/second-model/config/models.lock.json").read_text())
    tag = "v0.2.18"
    options = upgrade.settings(root / upgrade.RUNTIME / "upgrade.json")
    shard.write_bytes(b"")
    with pytest.raises(ValueError, match="Incomplete local preparation for second-model"):
        upgrade.upgrade(tag, options, False)
    shard.write_bytes(b"x")
    query = upgrade.output
    probe = Mock(return_value="image-id")
    run = subprocess.run
    prepared_recipes: list[str] = []

    def prepare_or_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        if command[1] == "runtimes/strata/scripts/prepare_models.py":
            prepared_recipes.append(command[3])
            return subprocess.CompletedProcess(command, 0)
        return run(command, **kwargs)

    with monkeypatch.context() as staging:
        staging.setattr(upgrade, "build_or_check", probe)
        staging.setattr(
            upgrade,
            "output",
            lambda *args, **kw: "image-id" if args[0] == "sudo" else query(*args, **kw),
        )
        staging.setattr(subprocess, "run", prepare_or_run)
        upgrade.upgrade(tag, options, False)
    probe.assert_called_once()
    assert prepared_recipes == ["recipes/first-model", "recipes/second-model"]
    summary = capsys.readouterr().out.split("Strata v0.2.18 preparation complete\n")[1]
    for index, name in enumerate(installed_names, 1):
        section = summary.split(f"[{index}/2] {name}\n")[1].split("\n[")[0].splitlines()
        commands = [shlex.split(line) for line in section if line.startswith("python3 ")]
        assert commands == [
            ["python3", "scripts/launch.py", "start", name],
            ["python3", "scripts/run_baseline.py", "run", name],
        ]
    candidate = root.parent / "reference-strata-v0.2.18"
    assert ["cd", str(candidate)] in [
        shlex.split(line) for line in summary.splitlines() if line.startswith("cd ")
    ]
    old = discover_recipes(app / "recipes")
    trials = discover_recipes(candidate / "recipes")
    trial = trials[installed_names[0]]
    data_dir = models / trials[installed_names[-1]].data_subpath
    for name in installed_names:
        folder = models / trials[name].data_subpath
        for directory, recipe in ((folder, old[name]), (folder / "prepared" / tag, trials[name])):
            versions = json.loads(
                (recipe.runtime_directory / "container/versions.lock.json").read_text()
            )
            upgrade.save(directory / "prepared.json", {"models": weights, "image": versions})
            for filename in _strata_required_files(True):
                path = directory / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x")

    query = upgrade.output

    def fake_output(*args: str, cwd: Path | None = None) -> str:
        if args[:3] == ("sudo", "docker", "run"):
            recipe = trial if trial.image in args else old[installed_names[0]]
            return (recipe.runtime_directory / "container/versions.lock.json").read_text()
        if args[:2] == ("sudo", "docker"):
            return ""
        return query(*args, cwd=cwd)

    monkeypatch.setattr(upgrade, "output", fake_output)
    upgrade.manage(tag, False)
    revision = query("git", "rev-parse", "HEAD", cwd=candidate)
    upgrade.manage(tag, False)
    assert query("git", "rev-parse", "HEAD", cwd=candidate) == revision
    assert query("git", "status", "--porcelain", cwd=candidate) == ""
    selected = discover_recipes(app / "recipes")
    for name in installed_names:
        assert selected[name] == trials[name]
        assert trials[name].image == trial.image
    assert selected["catalog-only"] == old["catalog-only"]
    assert not (models / "recipes/catalog-only").exists()

    (candidate / "notes").write_text("keep")
    with pytest.raises(ValueError, match="pending edits"):
        upgrade.manage(tag, True)
    (candidate / "notes").unlink()
    (data_dir / "prepared.json").rename(data_dir / "backup")
    with pytest.raises(ValueError, match=r"prepared.json"):
        upgrade.manage(tag, True)
    assert discover_recipes(app / "recipes") == selected
    (data_dir / "backup").rename(data_dir / "prepared.json")
    upgrade.manage(tag, True)
    upgrade.manage(tag, True)
    assert discover_recipes(app / "recipes") == old
    assert shard.read_bytes() == b"x"
    assert (data_dir / "prepared.json").is_file()
    assert not (data_dir / "prepared" / tag).exists()
    assert not candidate.exists()
    assert query("git", "rev-parse", f"strata-{tag}") == revision


def test_candidate_preserves_relative_data_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_RECIPES_HOME", "my models")
    models = data_home().resolve()
    assert upgrade.candidate_model_args(tmp_path / "trial", models) == ["--models", str(models)]
