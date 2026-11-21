import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_strata import RUNTIME, load_module

source = load_module("strata_mtp_source", RUNTIME / "scripts/mtp_source.py")
REPO = "test/model"
REV = "a" * 40
PAYLOAD = b"abcd"
HASHES = {"mtp.test": hashlib.sha256(PAYLOAD).hexdigest()}


def write_source(directory: Path) -> None:
    tensors = directory / "tensors"
    tensors.mkdir(parents=True, exist_ok=True)
    (tensors / "mtp.test.bin").write_bytes(PAYLOAD)
    row = {
        "name": "mtp.test",
        "file": "tensors/mtp.test.bin",
        "shape": [2],
        "dtype": "BF16",
        "sha256": HASHES["mtp.test"],
    }
    (directory / "mtp-manifest.json").write_text(json.dumps([row]))
    inventory = {"repo": f"https://huggingface.co/{REPO}/resolve/{REV}/", "tensors": [row]}
    (directory / "mtp-inventory.json").write_text(json.dumps(inventory))


@pytest.mark.parametrize("layout", ["recipes/old", "recipes/other/prepared/v0.2.18"])
def test_shared_source_imports_completed_preparation_offline(tmp_path: Path, layout: str) -> None:
    donor = tmp_path / layout
    write_source(donor / "mtp")
    (donor / "prepared.json").write_text(
        json.dumps({"models": {"mtp": {"repository": REPO, "revision": REV}}})
    )
    fetch = Mock(side_effect=AssertionError("unexpected fetch"))
    ready = source.shared_source(tmp_path, REPO, REV, HASHES, fetch)

    assert (ready / "tensors/mtp.test.bin").read_bytes() == PAYLOAD
    assert source.shared_source(tmp_path, REPO, REV, HASHES, fetch) == ready
    fetch.assert_not_called()


@pytest.mark.parametrize("fault", ["hash", "absent", "revision", "inventory", "manifest"])
def test_shared_source_fetches_when_donor_is_unsuitable(tmp_path: Path, fault: str) -> None:
    donor = tmp_path / "recipes/old"
    write_source(donor / "mtp")
    (donor / "prepared.json").write_text(
        json.dumps(
            {
                "models": {
                    "mtp": {
                        "repository": REPO,
                        "revision": "b" * 40 if fault == "revision" else REV,
                    }
                }
            }
        )
    )
    tensor = donor / "mtp/tensors/mtp.test.bin"
    if fault == "hash":
        tensor.write_bytes(b"bad!")
        (tensor.parent / "verified.json").write_text(
            json.dumps({"mtp.test": [4, tensor.stat().st_mtime_ns, HASHES["mtp.test"]]})
        )
    elif fault == "absent":
        tensor.unlink()
    elif fault == "inventory":
        (donor / "mtp/mtp-inventory.json").write_text("{}")
    elif fault == "manifest":
        (donor / "mtp/mtp-manifest.json").write_text("[]")

    fetch = Mock(side_effect=write_source)
    ready = source.shared_source(tmp_path, REPO, REV, HASHES, fetch)
    assert (ready / "tensors/mtp.test.bin").read_bytes() == PAYLOAD
    fetch.assert_called_once()


def test_shared_source_serializes_concurrent_recipes(tmp_path: Path) -> None:
    start = threading.Barrier(2)
    fetch = Mock(side_effect=write_source)

    def consume() -> Path:
        start.wait(timeout=10)
        return Path(source.shared_source(tmp_path, REPO, REV, HASHES, fetch))

    with ThreadPoolExecutor(2) as pool:
        first, second = [pool.submit(consume) for _ in range(2)]
        assert first.result() == second.result()
    fetch.assert_called_once()


def test_shared_source_keeps_interrupted_download_for_retry(tmp_path: Path) -> None:
    def interrupted(directory: Path) -> None:
        directory.mkdir()
        (directory / "in-progress").touch()
        raise OSError("connection lost")

    def resume(directory: Path) -> None:
        assert (directory / "in-progress").exists()
        write_source(directory)

    with pytest.raises(OSError, match="connection lost"):
        source.shared_source(tmp_path, REPO, REV, HASHES, interrupted)
    ready = source.shared_source(tmp_path, REPO, REV, HASHES, resume)
    assert (ready / "tensors/mtp.test.bin").read_bytes() == PAYLOAD


def test_shared_source_rejects_corruption_before_packing(tmp_path: Path) -> None:
    ready = source.shared_source(tmp_path, REPO, REV, HASHES, write_source)
    (ready / "tensors/mtp.test.bin").write_bytes(b"bad!")
    fetch = Mock()

    with pytest.raises(ValueError, match="checksum mismatch"):
        source.shared_source(tmp_path, REPO, REV, HASHES, fetch)
    fetch.assert_not_called()
