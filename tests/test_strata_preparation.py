"""Preparation integrity and interrupted-download handling without model downloads."""

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
from test_strata import RECIPE, load_module

prepare = load_module("strata_prepare", RECIPE / "scripts/prepare_models.py")


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
