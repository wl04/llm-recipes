"""Exercise container source extraction with local archives and no runtime dependencies."""

import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest


def load_fetcher(runtime: str) -> ModuleType:
    script = (
        Path(__file__).resolve().parents[1] / "runtimes" / runtime / "container/fetch_sources.py"
    )
    spec = importlib.util.spec_from_file_location(f"fetch_{runtime}", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=["strata", "exllamav3-tabbyapi"])
def extract(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Callable[[bytes, str], Path]:
    runtime = str(request.param)
    torch = ModuleType("torch")
    torch.__version__ = "test"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", torch)
    module = load_fetcher(runtime)
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


def arrange_strata_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    layout: str | None,
    projects: tuple[str, ...],
) -> tuple[ModuleType, Path, Path]:
    module = load_fetcher("strata")
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for project in projects:
            content = b"cmake_minimum_required(VERSION 3.21)\nproject(fixture NONE)\n"
            entry = tarfile.TarInfo(f"project/{project}/CMakeLists.txt")
            entry.size = len(content)
            archive.addfile(entry, io.BytesIO(content))
    payload = stream.getvalue()
    build = tmp_path / "build"
    source = tmp_path / "source trees"
    build.mkdir()
    lock: dict[str, object] = {
        "sources": {
            "strata": {
                "repository": "example/strata",
                "revision": "0123456789abcdef",
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
        },
    }
    if layout is not None:
        lock["layout"] = layout
    (build / "versions.lock.json").write_text(json.dumps(lock))
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(payload))
    return module, build, source


@pytest.mark.parametrize(
    ("layout", "projects", "engine", "vision"),
    [
        (None, (".", "tools/vision"), "strata", "strata/tools/vision"),
        (
            "engine-terminal",
            ("engine", "terminal/tools/vision"),
            "strata-source/engine",
            "strata-source/terminal/tools/vision",
        ),
    ],
    ids=["legacy", "split"],
)
def test_fetch_sources_exports_physical_build_paths_for_locked_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    layout: str | None,
    projects: tuple[str, ...],
    engine: str,
    vision: str,
) -> None:
    module, build, source = arrange_strata_sources(
        tmp_path, monkeypatch, layout=layout, projects=projects
    )

    module.main(build_root=build, source_root=source)

    command = (
        '. "$1"; printf "%s\\n" '
        '"$STRATA_BUILD_LAYOUT" "$STRATA_ENGINE_SOURCE" "$STRATA_VISION_SOURCE"'
    )
    config = subprocess.check_output(
        ["/bin/sh", "-ec", command, "sh", str(build / "strata-build-paths.sh")], text=True
    ).splitlines()
    assert config == [layout or "legacy", str(source / engine), str(source / vision)]
    assert (source / vision).resolve() == source / vision
    assert (source / "strata" / "tools/vision").resolve() == source / vision
    assert (source / "strata" / "BUILD_ID").read_text() == "012345678\n"


def test_fetch_sources_rejects_missing_project_for_locked_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, build, source = arrange_strata_sources(
        tmp_path, monkeypatch, layout="engine-terminal", projects=("engine",)
    )

    with pytest.raises(ValueError, match=r"engine-terminal.*terminal/tools/vision/CMakeLists\.txt"):
        module.main(build_root=build, source_root=source)

    assert not (build / "strata-build-paths.sh").exists()


def test_fetch_sources_rejects_unrecognized_layout_before_downloading_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, build, source = arrange_strata_sources(
        tmp_path, monkeypatch, layout="unrecognized", projects=()
    )
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **kw: pytest.fail("Download"))

    with pytest.raises(ValueError, match="Unsupported Strata source layout: unrecognized"):
        module.main(build_root=build, source_root=source)

    assert not (source / "strata").exists()
