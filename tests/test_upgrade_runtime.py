import hashlib
import io
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import upgrade_runtime as upgrade
import upgrade_strata as trials
from launcher import local_selections


def image(tag: str, arch: str = "amd64") -> dict[str, Any]:
    return {
        "name": tag,
        "images": [{"architecture": arch, "os": "linux", "digest": "sha256:" + "1" * 64}],
    }


def test_resolver_selects_latest_compatible_numeric_versions() -> None:
    tags = [
        image("rocm10.2.0_ubuntu24.04_py3.12_pytorch_release_" + version)
        for version in ("2.9.0", "2.15.0", "2.16.0rc1")
    ]
    tags += [
        image("rocm10.3.0_ubuntu24.04_py3.13_pytorch_release_2.17.0"),
        image("rocm10.3.0_ubuntu24.04_py3.12_pytorch_release_2.17.0", "arm64"),
    ]
    latest = upgrade.select_image(tags, "3.12", None, None)
    assert (latest.rocm, latest.torch, latest.python) == ("10.2.0", "2.15.0", "3.12")
    assert upgrade.select_image(tags, "3.12", "10.2.0", "2.9.0").torch == "2.9.0"
    with pytest.raises(ValueError, match=r"2\.15\.0"):
        upgrade.select_image(tags, "3.12", "10.2.0", "9.0.0")


def test_resolver_selects_full_dev_tag_for_strata() -> None:
    base = upgrade.select_image([image("10.2.0-full"), image("10.3.0-mini")], None, None, None)
    assert (base.repository, base.tag, base.torch) == ("rocm/dev-ubuntu-24.04", "10.2.0-full", None)


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    for subdir in ("runtimes", "recipes"):
        shutil.copytree(trials.ROOT / subdir, root / subdir)
    prefix = tmp_path / "prefix"
    shutil.copytree(root, prefix / "app")
    trials.save(prefix / "app/VERSION", {"version": "2"})
    monkeypatch.setattr(trials, "ROOT", root)
    monkeypatch.setenv("LLM_RECIPES_RUNTIME", str(prefix))
    monkeypatch.setenv("LLM_RECIPES_HOME", str(tmp_path / "weights"))
    subprocess.run(["git", "init", "-qb", "main"], cwd=root, check=True)
    for key, value in (("user.name", "fixture"), ("user.email", "test@example.org")):
        subprocess.run(["git", "config", key, value], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
    return root


def test_strata_recipes_share_image_pins_and_resume_offline(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = sorted(p.name for p in (checkout / "recipes").glob("*-flash-next-*"))
    assert len(names) == 2
    monkeypatch.setattr(upgrade, "registry_tags", lambda *args: [image("10.2.0-full")])
    monkeypatch.setattr(upgrade, "json_url", lambda url: {"tag_name": "v0.2.22"})
    monkeypatch.setattr(trials, "release", lambda *args: ("a" * 40, "b" * 64, "0.1.68"))

    for name in names:
        assert upgrade.main([name, "--prepare-only"]) == 0
    records = list((checkout / ".git/strata-trials").glob("*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text())
    key = records[0].stem
    assert trials.trial_names(record["files"]) == names
    monkeypatch.setattr(upgrade, "resolve", lambda *args: pytest.fail("Resume contacted upstream"))
    assert upgrade.main([names[0], "--resume", key, "--prepare-only"]) == 0
    assert json.loads(records[0].read_text()) == record
    assert not (checkout.parent / "weights").exists()


def test_exllama_trial_checks_image_and_only_adopts_on_request(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe = next((checkout / "recipes").glob("*-exl3-*"))
    reference = (recipe / "config/launch.json").read_bytes()
    tags = [
        image(f"rocm10.2.0_ubuntu24.04_py3.12_pytorch_release_{v}") for v in ("2.14.0", "2.15.0")
    ]
    monkeypatch.setattr(upgrade, "registry_tags", lambda *args: tags)
    monkeypatch.setattr(trials, "resolve_revision", lambda repo, tag: "b" * 40)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(b"archive"))
    build = Mock(return_value="sha256:" + "8" * 64)
    monkeypatch.setattr(trials, "build_or_check", build)
    original = trials.output

    def inspect(*cmd: str, cwd: Path | None = None) -> str:
        if cmd[:2] == ("sudo", "docker"):
            if "inspect" in cmd:
                return "sha256:" + "8" * 64
            if "--version" in cmd:
                return "Python 3.12.3"
            return ""
        return original(*cmd, cwd=cwd)

    monkeypatch.setattr(trials, "output", inspect)
    monkeypatch.setattr(
        upgrade, "prepare_models", lambda *args: pytest.fail("Unexpected model preparation")
    )

    assert (
        upgrade.main(
            [
                recipe.name,
                "--release",
                "v1.6.7",
                "--rocm",
                "10.2.0",
                "--pytorch",
                "current",
                "--image-only",
            ]
        )
        == 0
    )
    file = next((checkout / ".git/exllamav3-tabbyapi-trials").glob("*.json"))
    state = json.loads(file.read_text())
    lock = build.call_args.args[2]
    assert lock["torch_version"] == "2.14.0+rocm10.2.0"
    assert lock["sources"]["tabbyAPI"]["revision"] == "8f92fac5d9307bf1e09668c3715b32ff46ad0333"
    assert lock["sources"]["exllamav3"]["archive_sha256"] == hashlib.sha256(b"archive").hexdigest()
    assert state["container_python"] == "Python 3.12.3"
    assert (recipe / "config/launch.json").read_bytes() == reference
    assert not local_selections(recipe.name)

    monkeypatch.setattr(trials, "check_ready_recipe", lambda *args: None)
    assert upgrade.main([recipe.name, "--adopt", file.stem]) == 0
    assert local_selections(recipe.name) == [state["candidate"]]
    assert upgrade.main([recipe.name, "--delete", file.stem]) == 0
    assert not local_selections(recipe.name)
    assert not file.exists()
    assert upgrade.main([recipe.name, "--delete", file.stem]) == 0


def test_resolver_rejects_python_override_and_strata_pytorch(checkout: Path) -> None:
    name = next((checkout / "recipes").glob("*-flash-next-*")).name
    with pytest.raises(SystemExit):
        upgrade.main([name, "--python", "3.13"])
    with pytest.raises(SystemExit):
        upgrade.main([name, "--pytorch", "2.15.0"])
