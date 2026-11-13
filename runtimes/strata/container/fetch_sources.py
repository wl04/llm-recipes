"""Download and verify source archives before extracting them into the image."""

import hashlib
import json
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


def main() -> None:
    lock = json.loads(Path("/opt/build/versions.lock.json").read_text())
    for name, source in lock["sources"].items():
        url = f"https://codeload.github.com/{source['repository']}/tar.gz/{source['revision']}"
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "source.tar.gz"
            with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as output:
                shutil.copyfileobj(response, output)
            extract_verified(archive, Path("/opt/src") / name, source["sha256"])
    Path("/opt/src/strata/BUILD_ID").write_text(lock["sources"]["strata"]["revision"][:9] + "\n")


if __name__ == "__main__":
    main()
