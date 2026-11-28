import errno
from pathlib import Path

import pytest
from model_artifacts import inventory, stage_files, verify_inventory


def test_stage_files_keeps_payload_after_removing_donor(tmp_path: Path) -> None:
    donor, candidate = tmp_path / "donor", tmp_path / "candidate"
    donor.mkdir()
    (donor / "weights.bin").write_bytes(b"weights")
    (donor / "index.txt").write_text("index")
    records = inventory(donor)

    staged = stage_files(donor, candidate, records)

    assert (candidate / "weights.bin").samefile(donor / "weights.bin")
    assert not (candidate / "index.txt").samefile(donor / "index.txt")
    (donor / "weights.bin").unlink()
    verify_inventory(candidate, staged, verify=True)


def test_verify_inventory_rejects_changed_bytes_when_size_is_unchanged(tmp_path: Path) -> None:
    payload = tmp_path / "weights.bin"
    payload.write_bytes(b"weights")
    records = inventory(tmp_path)
    payload.write_bytes(b"damaged")

    with pytest.raises(ValueError, match=r"checksum.*weights\.bin"):
        verify_inventory(tmp_path, records)


def test_stage_files_requires_consent_when_neither_link_nor_clone_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    donor = tmp_path / "donor"
    donor.mkdir()
    (donor / "weights.bin").write_bytes(b"weights")

    def unavailable(*args: object, **kwargs: object) -> None:
        raise OSError(errno.EXDEV, "cross-device")

    monkeypatch.setattr("model_artifacts.os.link", unavailable)
    monkeypatch.setattr("model_artifacts.fcntl.ioctl", unavailable)
    records = inventory(donor)

    with pytest.raises(ValueError, match=r"7 bytes.*--allow-copy"):
        stage_files(donor, tmp_path / "refused", records)
    stage_files(donor, tmp_path / "allowed", records, allow_copy=True)

    assert (tmp_path / "allowed/weights.bin").read_bytes() == b"weights"
