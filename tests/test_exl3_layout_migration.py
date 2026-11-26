"""Check the one-time move with a small converted draft on disk."""

import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram"
KEY = "v1.6.6-tabby-8f92fac5"
RUNTIME = f"exllamav3-tabbyapi/releases/{KEY}"
BUILD = Path("runtimes") / RUNTIME / "container/versions.lock.json"
RunTool = Callable[..., subprocess.CompletedProcess[str]]


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
                "build": json.loads((ROOT / BUILD).read_text()),
                "source": spec["draft"],
                "arguments": ["-i", "/original", *spec["conversion"]["arguments"]],
                "sha256": hashes,
            }
        )
    )
    (root / "draft-conversion-work").mkdir()
    (root / spec["target"]["directory"]).mkdir()
    return root


@pytest.fixture
def run_tool(tmp_path: Path) -> RunTool:
    checkout = tmp_path / "legacy-checkout"
    tool = Path("tools/migrate_exl3_layout.py")
    config = Path("recipes") / RECIPE.name / "config"
    for path in (tool, Path("scripts/paths.py"), config / "models.lock.json", BUILD):
        (checkout / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, checkout / path)
    (checkout / config / "launch.json").write_text(json.dumps({"runtime": RUNTIME}))

    def invoke(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(checkout / tool), "--models", str(tmp_path), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    return invoke


def test_migration_preserves_artifacts_and_resumes_partial_move(
    data: Path, run_tool: RunTool
) -> None:
    draft = data / "qwen3.8-27b-dflash2-exl3-3bpw"
    receipt = (draft / "prepared.json").read_bytes()
    inode = draft.stat().st_ino
    dest = data / "prepared" / KEY
    assert run_tool("--dry-run").returncode == 0
    assert not dest.exists()
    dest.mkdir(parents=True)
    draft.rename(dest / draft.name)

    for _ in range(2):
        result = run_tool()
        assert result.returncode == 0, result.stderr
    assert (dest / draft.name).stat().st_ino == inode
    assert (dest / draft.name / "prepared.json").read_bytes() == receipt
    assert (dest / "draft-conversion-work").is_dir()
    assert (data / "qwen3.8-27b-exl3-3bpw").is_dir()


def test_migration_moves_converted_draft_when_work_directory_is_absent(
    data: Path, run_tool: RunTool
) -> None:
    draft = data / "qwen3.8-27b-dflash2-exl3-3bpw"
    original = draft.stat().st_ino
    (data / "draft-conversion-work").rmdir()

    result = run_tool()

    assert result.returncode == 0, result.stderr
    assert not draft.exists()
    assert (data / "prepared" / KEY / draft.name).stat().st_ino == original
    assert (data / "qwen3.8-27b-dflash2-source" / "prepared.json").is_file()


@pytest.mark.parametrize(
    ("problem", "message"),
    [
        ("conflict", "exist; review them before migrating"),
        ("checksum", "Checksum mismatch"),
        ("build", "Draft receipt does not match"),
        ("redirect", "Missing or redirected recipe data directory"),
    ],
)
def test_migration_refuses_invalid_input_before_moving_data(
    data: Path, run_tool: RunTool, problem: str, message: str
) -> None:
    draft = data / "qwen3.8-27b-dflash2-exl3-3bpw"
    if problem == "conflict":
        (data / "prepared" / KEY / "draft-conversion-work").mkdir(parents=True)
    elif problem == "checksum":
        (draft / "model.safetensors").write_bytes(b"changed")
    elif problem == "redirect":
        (data / "prepared").symlink_to(data.parent)
    else:
        (draft / "prepared.json").write_text("{}")

    result = run_tool()
    assert result.returncode != 0
    assert message in result.stderr
    assert draft.is_dir()
    assert (data / "draft-conversion-work").is_dir()
