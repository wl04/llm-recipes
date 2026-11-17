"""Exercise container source extraction with local archives and no runtime dependencies."""

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture(params=["strata", "exllamav3-tabbyapi"])
def extract(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Callable[[bytes, str], Path]:
    runtime = str(request.param)
    script = (
        Path(__file__).resolve().parents[1] / "runtimes" / runtime / "container/fetch_sources.py"
    )
    torch = ModuleType("torch")
    torch.__version__ = "test"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", torch)
    spec = importlib.util.spec_from_file_location(f"fetch_{runtime}", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    staging = tmp_path / "staging"
    staging.mkdir()
    monkeypatch.setattr(module.tempfile, "tempdir", str(staging))

    def run(payload: bytes, digest: str) -> Path:
        destination = tmp_path / "published"
        if runtime == "strata":
            archive = tmp_path / "source.tar.gz"
            archive.write_bytes(payload)
            module.extract_verified(archive, destination, digest)
        else:
            lock = tmp_path / "lock.json"
            lock.write_text(
                json.dumps(
                    {
                        "torch_version": "test",
                        "python_version": ".".join(map(str, sys.version_info[:2])),
                        "sources": {
                            "published": {
                                "repository": "https://github.com/example/source",
                                "revision": "test",
                                "archive_sha256": digest,
                            }
                        },
                    }
                )
            )

            def container_path(value: str) -> Path:
                return {"/opt/build/versions.lock.json": lock, "/opt/src": tmp_path}.get(
                    value, Path(value)
                )

            monkeypatch.setattr(module, "Path", container_path)
            monkeypatch.setattr(
                module.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(payload)
            )
            module.main()
        return destination

    return run


def archive_bytes(extra: tarfile.TarInfo | None = None) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        entry = tarfile.TarInfo("project/source.txt")
        entry.size = 5
        archive.addfile(entry, io.BytesIO(b"hello"))
        if extra is not None:
            archive.addfile(extra)
    return stream.getvalue()


def test_extract_publishes_source_for_verified_archive(
    extract: Callable[[bytes, str], Path],
) -> None:
    payload = archive_bytes()

    destination = extract(payload, hashlib.sha256(payload).hexdigest())

    assert (destination / "source.txt").read_text() == "hello"
    assert list((destination.parent / "staging").iterdir()) == []


def test_extract_rejects_checksum_before_opening_archive(
    extract: Callable[[bytes, str], Path], tmp_path: Path
) -> None:
    with pytest.raises((ValueError, RuntimeError), match="checksum"):
        extract(b"not a tar archive", "0" * 64)

    assert not (tmp_path / "published").exists()
    assert list((tmp_path / "staging").iterdir()) == []


@pytest.mark.parametrize("kind", ["traversal", "symlink", "hardlink"])
def test_extract_rejects_escape_and_cleans_partial_extraction(
    extract: Callable[[bytes, str], Path], tmp_path: Path, kind: str
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("unchanged")
    entry = tarfile.TarInfo("project/link")
    if kind == "traversal":
        entry.name = "../../outside.txt"
    else:
        entry.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
        entry.linkname = str(outside)
    payload = archive_bytes(entry)

    with pytest.raises(tarfile.FilterError):
        extract(payload, hashlib.sha256(payload).hexdigest())

    assert outside.read_text() == "unchanged"
    assert not (tmp_path / "published").exists()
    assert list((tmp_path / "staging").iterdir()) == []
