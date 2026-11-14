"""Read-only diagnostics without Docker, GPU, or model downloads."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import doctor
from launcher import discover_recipes

ROOT = Path(__file__).resolve().parents[1]
RECIPES = discover_recipes(ROOT / "recipes")
STRATA = next(recipe for recipe in RECIPES.values() if "ista" in recipe.name)


def test_doctor_reports_failures_without_creating_models(tmp_path: Path) -> None:
    models = tmp_path / "absent"
    with patch("doctor.subprocess.run", side_effect=FileNotFoundError("sudo missing")):
        findings = doctor.diagnose(STRATA, models, devices=tmp_path / "dev")

    assert any(item.status == "FAIL" and item.name == "Docker" for item in findings)
    assert any(item.status == "FAIL" and item.name == "AMD devices" for item in findings)
    assert any(item.status == "FAIL" and item.name == "Prepared models" for item in findings)
    assert not models.exists()


def test_doctor_uses_only_noninteractive_inspection_commands(tmp_path: Path) -> None:
    with patch("doctor.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, "available", "")
        doctor.diagnose(STRATA, tmp_path, devices=tmp_path / "dev")

    commands = [call.args[0] for call in run.call_args_list]
    assert commands == [
        ["sudo", "-n", "docker", "version", "--format", "{{.Server.Version}}"],
        ["sudo", "-n", "docker", "image", "inspect", STRATA.image, "--format", "{{.Id}}"],
    ]
    assert all(call.kwargs["timeout"] == 15 for call in run.call_args_list)


def test_prepared_rejects_stale_receipt_for_strata(tmp_path: Path) -> None:
    folder = tmp_path / STRATA.data_directory
    folder.mkdir()
    (folder / "prepared.json").write_text(json.dumps({"models": {}, "image": {}}))

    finding = doctor.check_prepared(STRATA, tmp_path)

    assert finding.status == "FAIL"
    assert "lock" in finding.detail


def test_doctor_reports_timeout_without_aborting_other_checks(tmp_path: Path) -> None:
    with patch("doctor.subprocess.run", side_effect=subprocess.TimeoutExpired("docker", 15)):
        findings = doctor.diagnose(STRATA, tmp_path, devices=tmp_path / "dev")

    assert any(item.name == "Docker" and item.status == "FAIL" for item in findings)
    assert any(item.name == "Configuration" for item in findings)


def test_prepared_checks_sizes_and_missing_artifacts_for_strata(tmp_path: Path) -> None:
    from dataclasses import replace

    recipe_dir = tmp_path / "recipe"
    (recipe_dir / "config").mkdir(parents=True)
    lock = {"files": [{"path": "target.gguf", "size_bytes": 3}]}
    (recipe_dir / "config/models.lock.json").write_text(json.dumps(lock))
    recipe = replace(STRATA, directory=recipe_dir, draft="off")
    models = tmp_path / "models"
    root = models / recipe.data_directory
    (root / "models").mkdir(parents=True)
    (root / "models/target.gguf").write_bytes(b"abc")
    versions = json.loads((recipe.runtime_directory / "container/versions.lock.json").read_text())
    (root / "prepared.json").write_text(json.dumps({"models": lock, "image": versions}))
    for name in (
        "native_experts.txt",
        "index.txt",
        "dense.bin",
        "tokenizer/tokenizer.json",
        "tokenizer/chat_template.jinja",
        "tokenizer/vocab.json",
    ):
        path = root / "packs/iq3_xxs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("artifact")

    assert doctor.check_prepared(recipe, models).status == "PASS"
    (root / "models/target.gguf").write_bytes(b"ab")
    assert "Size differs" in doctor.check_prepared(recipe, models).detail
    (root / "models/target.gguf").write_bytes(b"abc")
    (root / "packs/iq3_xxs/index.txt").unlink()
    assert "Missing or empty" in doctor.check_prepared(recipe, models).detail


def test_configuration_reports_port_mismatch(tmp_path: Path) -> None:
    import shutil
    from dataclasses import replace

    shutil.copytree(STRATA.directory / "config", tmp_path / "config")
    path = tmp_path / "config/strata.json"
    data = json.loads(path.read_text())
    data["port"] = 9999
    path.write_text(json.dumps(data))

    result = doctor.check_configuration(replace(STRATA, directory=tmp_path))

    assert result.status == "FAIL"
    assert "Native port" in result.detail


def test_cli_reports_failure_status_and_preserves_models(tmp_path: Path) -> None:
    import sys

    import launch

    models = tmp_path / "missing"
    with (
        patch.object(sys, "argv", ["launch.py", "doctor", STRATA.name, "--models", str(models)]),
        patch("doctor.subprocess.run", side_effect=FileNotFoundError("sudo missing")),
    ):
        status = launch.main()

    assert status == 1
    assert not models.exists()
