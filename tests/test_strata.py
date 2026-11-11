"""CPU checks for the Strata launch adapter and source verification."""

import hashlib
import importlib.util
import io
import json
import os
import sys
import tarfile
from pathlib import Path
from types import ModuleType

import pytest

RECIPE = (
    Path(__file__).resolve().parents[1]
    / "recipes"
    / "qwen3.8-flash-next-gguf-rx-9070-xt-16-gb-vram"
)


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


serve = load_module("strata_serve", RECIPE / "scripts/serve.py")
sources = load_module("strata_sources", RECIPE / "container/fetch_sources.py")


def test_configure_disables_optional_models_without_mutating_defaults() -> None:
    original = json.loads((RECIPE / "config/strata.json").read_text())

    result = serve.configure(original, 4096, "off", "off")

    assert "vision" not in result
    assert "--mtp" not in result["args"]
    assert result["args"][result["args"].index("--spec") + 1] == "0"
    assert result["args"][result["args"].index("--kv-resident") + 1] == "4096"
    assert "vision" in original and "--mtp" in original["args"]


def test_configure_preserves_cpu_vision_and_resident_cap_for_long_context() -> None:
    original = json.loads((RECIPE / "config/strata.json").read_text())

    result = serve.configure(original, 131072, "on", "cpu")

    assert result["vision"]["gpu"] is False
    assert result["args"][result["args"].index("--kv-resident") + 1] == "32768"
    assert result["args"][result["args"].index("--spec") + 1] == "4"


@pytest.mark.parametrize("context,draft,vision", [(1025, "on", "cpu"), (4096, "on", "on")])
def test_configure_rejects_invalid_options(context: int, draft: str, vision: str) -> None:
    with pytest.raises(ValueError):
        serve.configure({}, context, draft, vision)


def test_validate_files_reports_missing_artifacts(tmp_path: Path) -> None:
    config = {
        "args": [
            "--native",
            str(tmp_path / "missing.gguf"),
            "--ple-gguf",
            str(tmp_path / "second.gguf"),
            "--expert-profile",
            str(tmp_path / "profile.bin"),
        ],
        "tokenizer": str(tmp_path),
    }

    with pytest.raises(ValueError, match=r"missing\.gguf"):
        serve.validate_files(config)


def test_run_logged_preserves_output_and_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "server.log"
    command = [sys.executable, "-c", "print('API started'); raise SystemExit(7)"]

    result = serve.run_logged(command, log, dict(os.environ))

    assert result == 7
    assert "API started" in capsys.readouterr().out
    assert log.read_text() == "API started\n"


def test_extract_rejects_wrong_checksum_before_writing(tmp_path: Path) -> None:
    archive = tmp_path / "source.tar.gz"
    archive.write_bytes(b"untrusted")
    destination = tmp_path / "source"

    with pytest.raises(ValueError, match="checksum"):
        sources.extract_verified(archive, destination, "0" * 64)

    assert not destination.exists()


def test_extract_unpacks_verified_single_root_archive(tmp_path: Path) -> None:
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        entry = tarfile.TarInfo("project/source.txt")
        entry.size = 5
        output.addfile(entry, io.BytesIO(b"hello"))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    sources.extract_verified(archive, tmp_path / "source", digest)

    assert (tmp_path / "source/source.txt").read_text() == "hello"
