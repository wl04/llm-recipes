"""Fetch exact upstream archives with checksum verification."""

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import urllib.request

import torch


def main() -> None:
    lock = json.loads(Path("/opt/build/versions.lock.json").read_text())
    if torch.__version__ != lock["torch_version"]:
        raise RuntimeError(
            f"Image locks Torch {lock['torch_version']}, found {torch.__version__}; "
            "rebuild the image"
        )
    python = ".".join(map(str, sys.version_info[:2]))
    if python != lock["python_version"]:
        raise RuntimeError(
            f"Image locks Python {lock['python_version']}, found {python}; rebuild the image"
        )
    for name, source in lock["sources"].items():
        owner_repo = source["repository"].removeprefix("https://github.com/")
        url = f"https://codeload.github.com/{owner_repo}/tar.gz/{source['revision']}"
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "source.tar.gz"
            with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as stream:
                shutil.copyfileobj(response, stream)
            expected = source["archive_sha256"]
            actual = hashlib.sha256(archive.read_bytes()).hexdigest()
            if actual != expected:
                raise RuntimeError(
                    f"Archive checksum mismatch for {name}: expected {expected}, got {actual}"
                )
            unpacked = Path(tmp) / "source"
            with tarfile.open(archive) as tar:
                tar.extractall(unpacked, filter="data")
            entries = list(unpacked.iterdir())
            if len(entries) != 1 or not entries[0].is_dir():
                raise RuntimeError(f"Archive for {name} must unpack to a single directory")
            target = Path("/opt/src") / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(entries[0]), target)
        print(f"Verified {name} at {source['revision']}", flush=True)


if __name__ == "__main__":
    main()
