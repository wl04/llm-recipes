"""Download and verify source archives before extracting them into the image."""

import hashlib
import json
import shlex
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path


def extract_verified(archive: Path, destination: Path, expected_sha256: str) -> None:
    """Extract a single-root source archive only after checking its SHA-256."""
    with archive.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected_sha256:
        raise ValueError(f"Source archive checksum mismatch: {archive.name}")
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        with tarfile.open(archive) as source:
            source.extractall(folder, filter="data")
        roots = list(folder.iterdir())
        if len(roots) != 1 or not roots[0].is_dir():
            raise ValueError("Source archive must contain one root directory")
        shutil.copytree(roots[0], destination)


def main(*, build_root: Path = Path("/opt/build"), source_root: Path = Path("/opt/src")) -> None:
    """Extract the locked source trees and publish their build configuration."""
    lock_path = build_root / "versions.lock.json"
    try:
        lock = json.loads(lock_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read Strata build lock {lock_path}: {error}") from error
    layout = lock.get("layout", "legacy")
    if layout not in ("legacy", "engine-terminal"):
        raise ValueError(f"Unsupported Strata source layout: {layout}")
    split = layout == "engine-terminal"
    source_root = source_root.resolve()
    runtime = source_root / "strata"
    archive_root = source_root / "strata-source" if split else runtime
    engine = archive_root / "engine" if split else archive_root
    terminal = archive_root / "terminal" if split else archive_root
    vision = terminal / "tools/vision"

    for name, source in lock["sources"].items():
        url = f"https://codeload.github.com/{source['repository']}/tar.gz/{source['revision']}"
        destination = archive_root if name == "strata" else source_root / name
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "source.tar.gz"
            # The lock supplies only the path segment; scheme and host stay literal.
            with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as output:
                shutil.copyfileobj(response, output)
            extract_verified(archive, destination, source["sha256"])

    for project in (engine, vision):
        cmake_file = project / "CMakeLists.txt"
        if not cmake_file.is_file() or project.resolve() != project:
            raise ValueError(
                f"Strata layout {layout} requires a physical CMake project at {cmake_file}"
            )
    if split:
        runtime.symlink_to(terminal, target_is_directory=True)
    (terminal / "BUILD_ID").write_text(lock["sources"]["strata"]["revision"][:9] + "\n")

    options = lock.get("engine_options", {})
    (build_root / "engine-options.cmake").write_text(
        "".join(
            f'set({key} {"ON" if value else "OFF"} CACHE BOOL "")\n'
            for key, value in options.items()
        )
    )
    paths = {
        "STRATA_BUILD_LAYOUT": layout,
        "STRATA_ENGINE_SOURCE": str(engine),
        "STRATA_VISION_SOURCE": str(vision),
    }
    (build_root / "strata-build-paths.sh").write_text(
        "".join(f"{key}={shlex.quote(value)}\n" for key, value in paths.items())
    )


if __name__ == "__main__":
    main()
