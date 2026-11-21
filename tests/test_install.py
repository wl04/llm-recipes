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


def test_install_preserves_unrelated_executable_before_swap(
    roots: dict[str, Path], tmp_path: Path
) -> None:
    checkout = tmp_path / "checkout"
    make_checkout(checkout)
    executable = roots["home"] / ".local/bin/llm-recipes"
    executable.parent.mkdir(parents=True)
    executable.write_text("other tool")
    with pytest.raises(RuntimeError, match="refusing"):
        install(checkout, roots["runtime"], force=True, with_dependencies=False)
    assert executable.read_text() == "other tool"
    assert not (roots["runtime"] / "app").exists()


def test_install_restores_snapshot_when_shim_activation_fails(
    roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkout = tmp_path / "checkout"
    make_checkout(checkout)
    install(checkout, roots["runtime"], force=True, with_dependencies=False)
    (checkout / "scripts/launch.py").write_text("print('new')")

    def fail(_prefix: Path) -> None:
        raise OSError("activation failed")

    monkeypatch.setattr(install_module, "write_shims", fail)
    with pytest.raises(OSError, match="activation failed"):
        install(checkout, roots["runtime"], force=True, with_dependencies=False)
    assert (roots["runtime"] / "app/scripts/launch.py").read_text() == "print('launch')\n"


def test_install_refuses_concurrent_install_without_touching_staging(
    roots: dict[str, Path], tmp_path: Path
) -> None:
    import fcntl

    checkout = tmp_path / "checkout"
    make_checkout(checkout)
    roots["runtime"].mkdir(parents=True)
    staging = roots["runtime"] / "app.new"
    staging.mkdir()
    (staging / "keep").touch()
    with (roots["runtime"] / ".install.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="installation"):
            install(checkout, roots["runtime"], force=True, with_dependencies=False)
    assert (staging / "keep").exists()


def test_install_runs_venv_entrypoint_after_snapshot_swap(
    roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import venv

    checkout = tmp_path / "checkout"
    make_checkout(checkout)
    prefix = roots["runtime"] / "spaces ' and $literal"

    def create(path: Path, _python: str) -> None:
        venv.EnvBuilder(with_pip=False).create(path)
        probe = path / "bin/probe"
        # Shell trampoline handles long paths and spaces like installed entry points do.
        import shlex

        probe.write_text(
            "#!/bin/sh\nexec " + shlex.quote(str(path / "bin/python")) + " -c 'print(42)'\n"
        )
        probe.chmod(0o755)

    monkeypatch.setattr(install_module, "create_venv", create)
    install(checkout, prefix, force=True, with_dependencies=True)
    result = subprocess.run(
        [str(prefix / "app/.venv/bin/probe")], check=False, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "42"
    result = subprocess.run(
        [str(roots["home"] / ".local/bin/llm-recipes")], check=False, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "launch"


@pytest.mark.parametrize("existing", [False, True])
def test_install_restores_shims_after_partial_activation(
    roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path, existing: bool
) -> None:
    checkout = tmp_path / "checkout"
    make_checkout(checkout)
    prefix = roots["runtime"]
    if existing:
        install(checkout, prefix, force=True, with_dependencies=False)
    shim = prefix / "bin/llm-recipes"
    old = shim.read_bytes() if existing else None
    original = install_module.write_shims

    def fail_after_writing(path: Path) -> None:
        original(path)
        shim.write_text("incomplete")
        raise OSError("shim failure")

    monkeypatch.setattr(install_module, "write_shims", fail_after_writing)
    with pytest.raises(OSError, match="shim failure"):
        install(checkout, prefix, force=True, with_dependencies=False)

    if existing:
        assert shim.read_bytes() == old
        assert (roots["home"] / ".local/bin/llm-recipes").resolve() == shim
        assert (prefix / "app/scripts/launch.py").exists()
    else:
        assert not shim.exists()
        assert not (roots["home"] / ".local/bin/llm-recipes").is_symlink()
        assert not (prefix / "app").exists()


def test_install_keeps_active_environment_when_new_dependencies_fail(
    roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkout = tmp_path / "checkout"
    make_checkout(checkout)

    def create(path: Path, _python: str) -> None:
        path.mkdir(parents=True)

    monkeypatch.setattr(install_module, "create_venv", create)
    install(checkout, roots["runtime"], force=True, with_dependencies=True)
    active = (roots["runtime"] / "app/.venv").resolve()
    monkeypatch.setattr(install_module, "RUNTIME_REQUIREMENTS", ("test-package==1",))

    def fail(path: Path, _python: str) -> None:
        path.mkdir(parents=True)
        raise RuntimeError("dependency install failed")

    monkeypatch.setattr(install_module, "create_venv", fail)
    with pytest.raises(RuntimeError, match="dependency install failed"):
        install(checkout, roots["runtime"], force=True, with_dependencies=True)
    assert (roots["runtime"] / "app/.venv").resolve() == active
    assert (active / ".ready").exists()
    assert not (roots["runtime"] / "app.new").exists()


def test_install_preserves_unrelated_symlink(roots: dict[str, Path], tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    make_checkout(checkout)
    link = roots["home"] / ".local/bin/llm-recipes"
    link.parent.mkdir(parents=True)
    link.symlink_to("/another/install")
    with pytest.raises(RuntimeError, match="unrelated"):
        install(checkout, roots["runtime"], force=True, with_dependencies=False)
    assert link.readlink() == Path("/another/install")


def test_main_refreshes_credentials_before_inspecting_containers(
    roots: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tmp_path / "checkout"
    make_checkout(checkout)
    monkeypatch.setattr(install_module, "repo_root", lambda: checkout)
    authenticated = False

    def authenticate() -> None:
        nonlocal authenticated
        authenticated = True

    def running() -> list[str]:
        assert authenticated, "Docker inspection needs refreshed credentials"
        return []

    monkeypatch.setattr(install_module, "refresh_sudo_ticket", authenticate, raising=False)
    monkeypatch.setattr(install_module, "running_instances", running)
    assert install_module.main(["install", "--skip-deps"]) == 0


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (FileNotFoundError(2, "No such file or directory", "sudo"), "sudo"),
        (subprocess.TimeoutExpired(["docker", "ps"], 120), "timed out"),
        (PermissionError(13, "Permission denied", "/protected/prefix"), "/protected/prefix"),
    ],
)
def test_main_reports_expected_failure_without_traceback(
    error: Exception,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(*args: object, **kwargs: object) -> int:
        raise error

    monkeypatch.setattr(install_module, "install", fail)
    assert install_module.main(["install", "--force"]) == 1
    output = capsys.readouterr()
    assert message in output.err
    assert "Traceback" not in output.err
    assert output.out == ""


def test_main_stops_before_install_when_credentials_rejected(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def reject() -> None:
        raise ValueError("sudo credentials were not accepted")

    def unexpected(*args: object, **kwargs: object) -> int:
        pytest.fail("installation must not begin after rejected credentials")

    monkeypatch.setattr(install_module, "refresh_sudo_ticket", reject, raising=False)
    monkeypatch.setattr(install_module, "install", unexpected)
    assert install_module.main(["install"]) == 1
    assert "sudo credentials" in capsys.readouterr().err


def test_running_instances_reports_missing_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        install_module,
        "run_process",
        lambda command: subprocess.CompletedProcess(
            command, 1, "", "sudo: docker: command not found"
        ),
    )
    with pytest.raises(RuntimeError, match="docker: command not found"):
        install_module.running_instances()


def test_reinstall_selects_published_build_per_recipe(
    roots: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    checkout, trial = tmp_path / "main", tmp_path / "trial"
    prefix = roots["runtime"]
    selections = prefix / "selections"
    selections.mkdir(parents=True)
    release = "strata/releases/v0.2.18"
    for root in (checkout, trial):
        make_checkout(root)
        scripts = root / "runtimes/strata/scripts"
        scripts.mkdir(parents=True)
        (scripts / "serve.py").touch()
        for name in ("published", "different-release", "different-lock"):
            pin = release
            if name == "different-release" and root == checkout:
                pin = "strata/releases/v0.2.13"
            if name == "different-lock":
                pin += "-variant"
            runtime = root / "runtimes" / pin
            (runtime / "container").mkdir(parents=True, exist_ok=True)
            (runtime / "runtime.json").write_text(
                json.dumps({"adapter": "strata", "engine": "strata", "image": "strata:trial"})
            )
            lock = {"revision": "old" if name == "different-lock" and root == checkout else "new"}
            (runtime / "container/versions.lock.json").write_text(json.dumps(lock))
            config = root / "recipes" / name / "config"
            config.mkdir(parents=True)
            (config / "launch.json").write_text(
                json.dumps(
                    {"runtime": pin, "port": 8080, "context": 4096, "draft": "on", "vision": "cpu"}
                )
            )
            (config / "strata.json").write_text(
                '{"env":{}}' if root == trial else '{"env":{"STRATA_ROUTE_TAIL_SKIP":"7"}}'
            )
            (selections / f"{name}.json").write_text(json.dumps([str(checkout), str(trial)]))
    for _ in range(2):
        assert install(checkout, prefix, force=True, with_dependencies=False) == 0
        recipes = discover_recipes(prefix / "app/recipes")
        assert recipes["published"].directory == prefix / "app/recipes/published"
        for name in ("different-release", "different-lock"):
            assert recipes[name].directory == trial / "recipes" / name
    assert capsys.readouterr().out.count("published: using installed") == 1


def test_failed_selection_switch_restores_snapshot_and_selections(
    roots: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = roots["runtime"]
    checkout = tmp_path / "main"
    make_checkout(checkout)
    install(checkout, prefix, force=True, with_dependencies=False)
    (checkout / "scripts/launch.py").write_text("updated")
    install_module.build_snapshot(checkout, prefix / "app.new")
    directory = prefix / "selections"
    directory.mkdir()
    first, second = directory / "first.json", directory / "second.json"
    first.write_text('["/trial"]')
    second.write_text('["/trial"]')
    rename = Path.rename

    def fail_second(path: Path, target: Path) -> Path:
        if path == second:
            raise OSError("cannot move selection")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_second)
    with pytest.raises(OSError, match="cannot move selection"):
        install_module.activate_snapshot(prefix, [first, second])
    assert first.read_text() == second.read_text() == '["/trial"]'
    assert (prefix / "app/scripts/launch.py").read_text() == "print('launch')\n"
