"""Read-only diagnostics without Docker, GPU, or model downloads."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import doctor
import pytest
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
    folder = tmp_path / STRATA.data_subpath / "prepared" / STRATA.runtime_directory.name
    folder.mkdir(parents=True)
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
    root = models / recipe.data_subpath
    (root / "models").mkdir(parents=True)
    (root / "models/target.gguf").write_bytes(b"abc")
    versions = json.loads((recipe.runtime_directory / "container/versions.lock.json").read_text())
    prepared = root / "prepared" / recipe.runtime_directory.name
    prepared.mkdir(parents=True)
    (prepared / "prepared.json").write_text(json.dumps({"models": lock, "image": versions}))
    for name in (
        "native_experts.txt",
        "index.txt",
        "dense.bin",
        "tokenizer/tokenizer.json",
        "tokenizer/chat_template.jinja",
        "tokenizer/vocab.json",
    ):
        path = prepared / "packs/iq3_xxs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("artifact")

    assert doctor.check_prepared(recipe, models).status == "PASS"
    (root / "models/target.gguf").write_bytes(b"ab")
    assert "Size differs" in doctor.check_prepared(recipe, models).detail
    (root / "models/target.gguf").write_bytes(b"abc")
    (prepared / "packs/iq3_xxs/index.txt").unlink()
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


@pytest.mark.parametrize(
    ("filename", "field", "value", "message"),
    [
        ("pi.models.json", "providers", None, "providers must be an object"),
        ("strata.json", "args", None, "args must be a list"),
        ("strata.json", "vision", None, "vision must be an object"),
    ],
)
def test_diagnose_reports_invalid_nested_config_without_aborting(
    tmp_path: Path, filename: str, field: str, value: object, message: str
) -> None:
    import shutil
    from dataclasses import replace

    shutil.copytree(STRATA.directory / "config", tmp_path / "config")
    path = tmp_path / "config" / filename
    data = json.loads(path.read_text())
    data[field] = value
    path.write_text(json.dumps(data))
    recipe = replace(STRATA, directory=tmp_path)

    with patch("doctor.subprocess.run", side_effect=FileNotFoundError("sudo missing")):
        findings = doctor.diagnose(recipe, tmp_path / "models", devices=tmp_path / "dev")

    configuration = next(item for item in findings if item.name == "Configuration")
    assert configuration.status == "FAIL"
    assert message in configuration.detail
    assert findings[-1].name == "Prepared models"


@pytest.mark.parametrize("payload", [b"{", b"[]", b"\xff", None])
def test_diagnose_reports_unreadable_metadata_and_continues(
    tmp_path: Path, payload: bytes | None
) -> None:
    from dataclasses import replace

    folder = tmp_path / "config"
    folder.mkdir()
    if payload is not None:
        (folder / "models.lock.json").write_bytes(payload)
    recipe = replace(STRATA, directory=tmp_path)

    with patch("doctor.subprocess.run", side_effect=FileNotFoundError("sudo missing")):
        findings = doctor.diagnose(recipe, tmp_path / "models", devices=tmp_path / "dev")

    assert [(item.name, item.status) for item in findings[-2:]] == [
        ("Configuration", "FAIL"),
        ("Prepared models", "FAIL"),
    ]
    assert "setup.md" in findings[-1].detail
    assert not (tmp_path / "models").exists()


def test_diagnose_reports_metadata_permission_error_and_continues(tmp_path: Path) -> None:
    with (
        patch("doctor.subprocess.run", side_effect=FileNotFoundError("sudo missing")),
        patch.object(Path, "read_text", side_effect=PermissionError("metadata access denied")),
    ):
        findings = doctor.diagnose(STRATA, tmp_path / "models", devices=tmp_path / "dev")

    assert [(item.name, item.status) for item in findings[-2:]] == [
        ("Configuration", "FAIL"),
        ("Prepared models", "FAIL"),
    ]
    assert all("metadata access denied" in item.detail for item in findings[-2:])
