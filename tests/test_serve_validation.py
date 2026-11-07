"""Tests for prepared-model metadata validation in serve.py."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

RECIPE_SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / "recipes"
    / "qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram"
    / "scripts"
)
sys.path.insert(0, str(RECIPE_SCRIPTS))

import serve  # noqa: E402


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
