"""Check the one-time move with a small converted draft on disk."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/migrate_exl3_layout.py"
RECIPE = next((ROOT / "recipes").glob("*-exl3-*"))
KEY = "v1.6.6-tabby-8f92fac5"
BUILD = ROOT / "runtimes/exllamav3-tabbyapi/container/versions.lock.json"


@pytest.fixture
def data(tmp_path: Path) -> Path:
    root = tmp_path / "recipes" / RECIPE.name
    spec = json.loads((RECIPE / "config/models.lock.json").read_text())
    draft = root / spec["conversion"]["directory"]
    draft.mkdir(parents=True)
    hashes = {}
    for name in ("config.json", "README.md", "model.safetensors"):
        (draft / name).write_bytes(b"{}")
        hashes[name] = hashlib.sha256(b"{}").hexdigest()
    source = root / spec["draft"]["directory"]
    source.mkdir()
    source_receipt = json.dumps({"source": spec["draft"]}).encode()
    (source / "prepared.json").write_bytes(source_receipt)
    hashes["prepared.json"] = hashlib.sha256(source_receipt).hexdigest()
    (draft / "prepared.json").write_text(
        json.dumps(
            {
                "build": json.loads(BUILD.read_text()),
                "source": spec["draft"],
                "arguments": ["-i", "/original", *spec["conversion"]["arguments"]],
                "sha256": hashes,
            }
        )
    )
    (root / "draft-conversion-work").mkdir()
    (root / spec["target"]["directory"]).mkdir()
    return root


def run_tool(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), "--models", str(root.parents[1]), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_migration_preserves_artifacts_and_resumes_partial_move(data: Path) -> None:
    draft = data / "qwen3.8-27b-dflash2-exl3-3bpw"
    receipt = (draft / "prepared.json").read_bytes()
    inode = draft.stat().st_ino
    dest = data / "prepared" / KEY
    assert run_tool(data, "--dry-run").returncode == 0
    assert not dest.exists()
    dest.mkdir(parents=True)
    draft.rename(dest / draft.name)

    for _ in range(2):
        result = run_tool(data)
        assert result.returncode == 0, result.stderr
    assert (dest / draft.name).stat().st_ino == inode
    assert (dest / draft.name / "prepared.json").read_bytes() == receipt
    assert (dest / "draft-conversion-work").is_dir()
    assert (data / "qwen3.8-27b-exl3-3bpw").is_dir()


def test_migration_moves_converted_draft_when_work_directory_is_absent(data: Path) -> None:
    draft = data / "qwen3.8-27b-dflash2-exl3-3bpw"
    original = draft.stat().st_ino
    (data / "draft-conversion-work").rmdir()

    result = run_tool(data)

    assert result.returncode == 0, result.stderr
    assert not draft.exists()
    assert (data / "prepared" / KEY / draft.name).stat().st_ino == original
    assert (data / "qwen3.8-27b-dflash2-source" / "prepared.json").is_file()


@pytest.mark.parametrize("problem", ["conflict", "checksum", "build", "redirect"])
def test_migration_refuses_invalid_input_before_moving_data(data: Path, problem: str) -> None:
    draft = data / "qwen3.8-27b-dflash2-exl3-3bpw"
    if problem == "conflict":
        (data / "prepared" / KEY / "draft-conversion-work").mkdir(parents=True)
    elif problem == "checksum":
        (draft / "model.safetensors").write_bytes(b"changed")
    elif problem == "redirect":
        (data / "prepared").symlink_to(data.parent)
    else:
        (draft / "prepared.json").write_text("{}")

    assert run_tool(data).returncode != 0
    assert draft.is_dir()
    assert (data / "draft-conversion-work").is_dir()
