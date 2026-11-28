"""Tests for prepared-model metadata validation in serve.py."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from ruamel.yaml import YAML

RECIPE_SCRIPTS = Path(__file__).resolve().parents[1] / "runtimes" / "exllamav3-tabbyapi" / "scripts"
sys.path.insert(0, str(RECIPE_SCRIPTS))

import serve  # noqa: E402


@pytest.fixture
def tabby_startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    recipe = tmp_path / "recipe"
    config = recipe / "config"
    config.mkdir(parents=True)
    weights = tmp_path / "weights"
    model = weights / "target"
    model.mkdir(parents=True)
    (model / "config.json").write_text("{}")
    (model / "model.safetensors").write_bytes(b"weights")
    spec = {"files": ["config.json", "model.safetensors"]}
    write_manifest(model, {"source": spec, "sha256": dict.fromkeys(spec["files"], "fixture")})
    (config / "launch.json").write_text('{"runtime":"exllamav3-tabbyapi"}')
    (config / "models.lock.json").write_text(json.dumps({"target": spec}))
    (config / "tabby.yml").write_text(
        json.dumps(
            {"model": {"model_dir": str(weights), "model_name": "target"}, "draft_model": {}}
        )
    )
    runtime = tmp_path / "runtime"
    (runtime / "container").mkdir(parents=True)
    image = '{"version":"locked"}'
    (runtime / "container/versions.lock.json").write_text(image)
    image_lock = tmp_path / "image.lock.json"
    image_lock.write_text(image)
    monkeypatch.setattr(
        serve,
        "Path",
        lambda path: image_lock if path == "/opt/build/versions.lock.json" else Path(path),
    )
    monkeypatch.setattr(serve, "RUNTIME", runtime)
    # The upstream TabbyAPI schema is only installed in the image.
    monkeypatch.setattr(serve, "validate_sections", lambda _config: None)
    monkeypatch.setattr(
        sys, "argv", ["serve.py", "--recipe", str(recipe), "--draft", "off", "--context", "8192"]
    )
    return image_lock, model / "prepared.json"


def test_main_passes_validated_settings_to_tabby_when_preparation_matches(
    tabby_startup: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = tmp_path / "instance"
    instance.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HIP_VISIBLE_DEVICES", "previous")
    monkeypatch.setattr(
        subprocess, "check_output", lambda *args, **kwargs: '["Other GPU","AMD RX 9070 XT"]'
    )
    monkeypatch.setattr(serve, "prepare_runtime", lambda _source: instance)
    execv = Mock()
    monkeypatch.setattr(os, "execv", execv)

    serve.main()

    config_path = instance / "config.yml"
    execv.assert_called_once_with(
        sys.executable, [sys.executable, "/opt/src/tabbyAPI/main.py", "--config", str(config_path)]
    )
    config = YAML(typ="safe").load(config_path)
    assert config["model"]["max_seq_len"] == config["model"]["cache_size"] == 8192
    assert config["draft_model"]["draft_mode"] == "disabled"
    assert os.environ["HIP_VISIBLE_DEVICES"] == "1"


@pytest.mark.parametrize(
    ("mismatch", "message"),
    [("image", "Image pins differ"), ("receipt", "prepared model does not match the locked spec")],
)
def test_main_refuses_tabby_startup_when_preparation_is_stale(
    tabby_startup: tuple[Path, Path], mismatch: str, message: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    image_lock, receipt = tabby_startup
    (image_lock if mismatch == "image" else receipt).write_text('{"source":{},"sha256":{}}')
    probe = Mock(side_effect=AssertionError("Unexpected GPU probe"))
    execv = Mock(side_effect=AssertionError("Unexpected engine launch"))
    monkeypatch.setattr(subprocess, "check_output", probe)
    monkeypatch.setattr(os, "execv", execv)

    with pytest.raises(RuntimeError, match=message):
        serve.main()

    probe.assert_not_called()
    execv.assert_not_called()


def write_manifest(directory: Path, manifest: Any) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "prepared.json"
    path.write_text(json.dumps(manifest))
    return path


def test_verify_prepared_manifest_passes_when_metadata_matches_spec() -> None:
    spec = {
        "repo_id": "repo",
        "revision": "abc",
        "directory": "model",
        "files": ["config.json", "weights.safetensors"],
    }
    manifest = {"source": spec, "sha256": {"config.json": "a", "weights.safetensors": "b"}}

    serve.verify_prepared_manifest(manifest, spec, Path("/models/model"))


def test_verify_prepared_manifest_fails_when_source_spec_mismatches() -> None:
    spec = {"repo_id": "repo", "revision": "abc", "directory": "model", "files": ["config.json"]}
    wrong_revision = dict(spec, revision="def")
    manifest = {"source": wrong_revision, "sha256": {"config.json": "a"}}

    with pytest.raises(RuntimeError, match="does not match the locked spec"):
        serve.verify_prepared_manifest(manifest, spec, Path("/models/model"))


def test_verify_prepared_manifest_accepts_extra_files_in_converted_output() -> None:
    spec = {"repo_id": "repo", "revision": "abc", "directory": "model", "files": ["config.json"]}
    manifest = {
        "source": spec,
        "sha256": {"config.json": "a", "quantization_config.json": "b", "source.json": "c"},
    }

    serve.verify_prepared_manifest(manifest, spec, Path("/models/model"))


def test_verify_prepared_manifest_fails_when_locked_file_is_missing() -> None:
    spec = {
        "repo_id": "repo",
        "revision": "abc",
        "directory": "model",
        "files": ["config.json", "weights.safetensors"],
    }
    manifest = {"source": spec, "sha256": {"config.json": "a"}}

    with pytest.raises(RuntimeError, match="incomplete"):
        serve.verify_prepared_manifest(manifest, spec, Path("/models/model"))


def test_verify_prepared_manifest_fails_when_checksums_are_empty() -> None:
    spec = {"repo_id": "repo", "revision": "abc", "directory": "model", "files": []}
    manifest = {"source": spec, "sha256": {}}

    with pytest.raises(RuntimeError, match="no file checksums"):
        serve.verify_prepared_manifest(manifest, spec, Path("/models/model"))


def test_verify_prepared_manifest_fails_when_manifest_is_not_an_object() -> None:
    spec = {"repo_id": "repo", "revision": "abc", "directory": "model", "files": []}

    with pytest.raises(RuntimeError, match="not a JSON object"):
        serve.verify_prepared_manifest(["unrelated"], spec, Path("/models/model"))


def test_verify_draft_manifest_fails_when_build_pins_differ() -> None:
    spec = {"repo_id": "repo", "revision": "abc", "directory": "draft", "files": ["config.json"]}
    conversion = {"arguments": ["-b", "3.0"]}
    recipe_lock = {"torch_version": "2.14.0"}
    manifest = {
        "source": spec,
        "sha256": {"config.json": "a"},
        "build": {"torch_version": "2.13.0"},
        "arguments": ["-i", "/in", "-o", "/out", "-d", "0", "-b", "3.0"],
    }

    with pytest.raises(RuntimeError, match="different build pins"):
        serve.verify_draft_manifest(manifest, spec, conversion, recipe_lock, Path("/models/draft"))


def test_verify_draft_manifest_fails_when_conversion_arguments_differ() -> None:
    spec = {"repo_id": "repo", "revision": "abc", "directory": "draft", "files": ["config.json"]}
    conversion = {"arguments": ["-b", "3.0", "-cb", "mul1"]}
    recipe_lock = {"torch_version": "2.14.0"}
    manifest = {
        "source": spec,
        "sha256": {"config.json": "a"},
        "build": recipe_lock,
        "arguments": ["-i", "/in", "-o", "/out", "-d", "0", "-b", "2.0"],
    }

    with pytest.raises(RuntimeError, match="different conversion settings"):
        serve.verify_draft_manifest(manifest, spec, conversion, recipe_lock, Path("/models/draft"))


def test_verify_draft_manifest_passes_when_metadata_matches_lock() -> None:
    spec = {"repo_id": "repo", "revision": "abc", "directory": "draft", "files": ["config.json"]}
    conversion = {"arguments": ["-b", "3.0", "-cb", "mul1"]}
    recipe_lock = {"torch_version": "2.14.0"}
    manifest = {
        "source": spec,
        "sha256": {"config.json": "a"},
        "build": recipe_lock,
        "arguments": ["-i", "/in", "-o", "/out", "-d", "0", "-b", "3.0", "-cb", "mul1"],
    }

    serve.verify_draft_manifest(manifest, spec, conversion, recipe_lock, Path("/models/draft"))


def test_load_json_object_reports_missing_and_malformed_fields(tmp_path: Path) -> None:
    path = write_manifest(tmp_path, {"source": "unrelated"})

    with pytest.raises(RuntimeError, match="missing field: sha256"):
        serve.check_manifest_file(path, ("source", "sha256"))
    path.write_text("{ not json")
    with pytest.raises(RuntimeError, match="not valid JSON"):
        serve.check_manifest_file(path, ("source", "sha256"))


@pytest.mark.parametrize("contents", [None, "{ not json"], ids=["missing", "malformed"])
def test_main_rejects_recipe_when_launch_settings_are_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    contents: str | None,
) -> None:
    if contents is not None:
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "launch.json").write_text(contents)
    monkeypatch.setattr(sys, "argv", ["serve", "--recipe", str(tmp_path)])

    with pytest.raises(SystemExit) as exit_call:
        serve.main()

    captured = capsys.readouterr()

    assert exit_call.value.code == 2
    assert "config/launch.json" in captured.err
    assert "launch settings are not readable" in captured.err


def test_main_rejects_recipe_when_launch_settings_have_no_runtime_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "launch.json").write_text('{"runtime": 7}')
    monkeypatch.setattr(sys, "argv", ["serve", "--recipe", str(tmp_path)])

    with pytest.raises(SystemExit) as exit_call:
        serve.main()

    captured = capsys.readouterr()

    assert exit_call.value.code == 2
    assert 'launch settings have no "runtime" field' in captured.err


def test_main_rejects_recipe_for_another_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "launch.json").write_text('{"runtime": "exllamav2"}')
    monkeypatch.setattr(sys, "argv", ["serve", "--recipe", str(tmp_path)])

    with pytest.raises(SystemExit) as exit_call:
        serve.main()

    captured = capsys.readouterr()

    assert exit_call.value.code == 2
    assert "expected an exllamav3-tabbyapi recipe" in captured.err


def test_main_selects_draft_and_build_from_recipe_release(
    tabby_startup: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_lock, _ = tabby_startup
    config = tmp_path / "recipe/config"
    key = "v1.6.6-rocm10.2"
    spec = {"files": ["config.json", "model.safetensors"]}
    (config / "launch.json").write_text(
        json.dumps({"runtime": f"exllamav3-tabbyapi/releases/{key}"})
    )
    models = {"target": spec, "draft": spec, "conversion": {"arguments": ["-b", "3"]}}
    (config / "models.lock.json").write_text(json.dumps(models))
    native = json.loads((config / "tabby.yml").read_text())
    native["draft_model"] = {
        "draft_model_dir": str(tmp_path / "weights"),
        "draft_model_name": "draft",
    }
    (config / "tabby.yml").write_text(json.dumps(native))
    pins = tmp_path / "runtime/releases" / key / "container"
    pins.mkdir(parents=True)
    image_lock.write_text('{"version":"candidate"}')
    (pins / "versions.lock.json").write_text(image_lock.read_text())
    draft = tmp_path / "weights/prepared" / key / "draft"
    draft.mkdir(parents=True)
    (draft / "config.json").write_text("{}")
    (draft / "model.safetensors").write_bytes(b"weights")
    write_manifest(
        draft,
        {
            "source": spec,
            "build": {"version": "candidate"},
            "arguments": ["-b", "3"],
            "sha256": dict.fromkeys(spec["files"], "fixture"),
        },
    )
    instance = tmp_path / "server"
    instance.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HIP_VISIBLE_DEVICES", "0")
    monkeypatch.setattr(subprocess, "check_output", lambda *_args, **_kwargs: '["RX 9070 XT"]')
    monkeypatch.setattr(serve, "prepare_runtime", lambda _source: instance)
    monkeypatch.setattr(os, "execv", Mock())
    monkeypatch.setattr(sys, "argv", ["serve", "--recipe", str(config.parent)])

    serve.main()

    served = YAML(typ="safe").load(instance / "config.yml")
    assert served["model"]["model_dir"] == str(tmp_path / "weights")
    assert served["draft_model"]["draft_model_dir"] == str(draft.parent)
