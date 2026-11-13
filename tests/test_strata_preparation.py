"""Preparation integrity and interrupted-download handling without model downloads."""

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
from test_strata import RUNTIME, UNSLOTH, load_module

prepare = load_module("strata_prepare", RUNTIME / "scripts/prepare_models.py")


def test_download_reuses_verified_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "model"
    path.write_bytes(b"weights")
    digest = hashlib.sha256(b"weights").hexdigest()

    with patch.object(prepare.urllib.request, "urlopen") as request:
        prepare.download("https://example.invalid/model", path, 7, digest)

    request.assert_not_called()


def test_download_rejects_corrupt_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "model"
    path.write_bytes(b"damaged")

    with pytest.raises(ValueError, match="checksum"):
        prepare.download("https://example.invalid/model", path, 7, "0" * 64)

    assert path.read_bytes() == b"damaged"


def test_download_publishes_verified_partial_without_network(tmp_path: Path) -> None:
    path = tmp_path / "model"
    partial = path.with_name(path.name + ".part")
    partial.write_bytes(b"weights")

    with patch.object(prepare.urllib.request, "urlopen") as request:
        prepare.download(
            "https://example.invalid/model", path, 7, hashlib.sha256(b"weights").hexdigest()
        )

    request.assert_not_called()
    assert path.read_bytes() == b"weights"
    assert not partial.exists()


def test_download_rejects_ignored_resume_range(tmp_path: Path) -> None:
    path = tmp_path / "model"
    partial = path.with_name(path.name + ".part")
    partial.write_bytes(b"wei")

    with patch.object(prepare.urllib.request, "urlopen") as request:
        request.return_value.__enter__.return_value.status = 200
        with pytest.raises(ValueError, match="resume range"):
            prepare.download("https://example.invalid/model", path, 7, "0" * 64)

    assert partial.read_bytes() == b"wei"
    assert not path.exists()


def test_download_resumes_and_verifies_response(tmp_path: Path) -> None:
    path = tmp_path / "model"
    path.with_name(path.name + ".part").write_bytes(b"wei")

    with patch.object(prepare.urllib.request, "urlopen") as request:
        response = request.return_value.__enter__.return_value
        response.status = 206
        response.headers = {"Content-Range": "bytes 3-6/7"}
        response.read.side_effect = [b"ghts", b""]
        prepare.download(
            "https://example.invalid/model", path, 7, hashlib.sha256(b"weights").hexdigest()
        )

    assert path.read_bytes() == b"weights"


def test_pack_command_selects_four_shards_and_compatibility_for_unsloth() -> None:
    lock = {
        "files": [{"path": "UD-IQ3_XXS/model-00001-of-00004.gguf"}],
        "pack": {"compat_bf16": True},
    }
    args = prepare.pack_arguments(lock, Path("/models/strata-unsloth"))
    assert args == [
        "--gguf",
        "/models/strata-unsloth/models/UD-IQ3_XXS/model-00001-of-00004.gguf",
        "--out",
        "/models/strata-unsloth/packs/iq3_xxs",
        "--compat-bf16",
    ]


def test_pack_command_preserves_two_shard_ista_defaults() -> None:
    lock = {"files": [{"path": "IQ3_XXS/model-00001-of-00002.gguf"}]}
    args = prepare.pack_arguments(lock, Path("/models/strata"))
    assert args[1] == "/models/strata/models/IQ3_XXS/model-00001-of-00002.gguf"
    assert "--compat-bf16" not in args


def test_prepare_records_selected_lock_without_touching_baseline(tmp_path: Path) -> None:
    import json
    import subprocess

    root = tmp_path / "strata-unsloth"
    baseline = tmp_path / "strata/prepared.json"
    baseline.parent.mkdir()
    baseline.write_text("baseline receipt")
    lock = json.loads((UNSLOTH / "config/models.lock.json").read_text())
    versions = json.loads((RUNTIME / "container/versions.lock.json").read_text())
    original_read = Path.read_text
    calls: list[list[str]] = []
    urls: list[str] = []

    def read(path: Path) -> str:
        if path == Path("/opt/build/versions.lock.json"):
            return json.dumps(versions)
        return original_read(path)

    def download(url: str, path: Path, size: int, digest: str) -> None:
        urls.append(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if Path(command[1]).name == "iq_pack.py":
            folder = Path(command[command.index("--out") + 1])
            outputs = [
                "native_experts.txt",
                "index.txt",
                "dense.bin",
                "tokenizer/vocab.json",
                "tokenizer/tokenizer.json",
                "tokenizer/chat_template.jinja",
            ]
        elif Path(command[1]).name == "mtp_rt.py":
            folder = root / "mtp/rt"
            outputs = ["experts.bin", "dense.bin", "dense.txt"]
        else:
            return subprocess.CompletedProcess(command, 0)
        for name in outputs:
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        return subprocess.CompletedProcess(command, 0)

    def copy(source: Path, destination: Path) -> None:
        destination.write_bytes(b"vocabulary")

    with (
        patch.object(Path, "read_text", read),
        patch.object(prepare, "pinned_mtp_revision", return_value=lock["mtp"]["revision"]),
        patch.object(prepare, "download", download),
        patch.object(prepare.subprocess, "run", run),
        patch.object(prepare.shutil, "copyfile", copy),
    ):
        prepare.prepare(UNSLOTH, root)

    assert json.loads((root / "prepared.json").read_text()) == {"models": lock, "image": versions}
    assert baseline.read_text() == "baseline receipt"
    assert len(urls) == 5
    assert all("unsloth/Qwen3.8-Flash-Next-GGUF/resolve/084c631" in url for url in urls[:4])
    assert "ISTA-DASLab/" in urls[-1]
    assert "--compat-bf16" in calls[0]
    assert "00001-of-00004.gguf" in calls[0][3]


def test_prepare_host_mounts_runtime_and_selected_recipe(tmp_path: Path) -> None:
    import subprocess
    import sys

    with (
        patch.object(
            sys,
            "argv",
            ["prepare_models.py", "--recipe", str(UNSLOTH), "--models", str(tmp_path / "models")],
        ),
        patch.object(
            prepare.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
        ) as run,
    ):
        assert prepare.main() == 0
    command = run.call_args.args[0]
    assert f"type=bind,src={UNSLOTH},dst=/recipe,readonly" in command
    assert f"type=bind,src={RUNTIME},dst=/runtime,readonly" in command
    assert command[-4:] == [
        "/runtime/scripts/prepare_models.py",
        "--recipe",
        "/recipe",
        "--inside-container",
    ]
