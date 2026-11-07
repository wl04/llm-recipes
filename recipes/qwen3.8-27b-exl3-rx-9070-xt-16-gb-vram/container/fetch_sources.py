"""Fetch exact upstream archives with checksum verification."""

import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import torch

lock = json.loads(Path("/opt/build/versions.lock.json").read_text())
assert torch.__version__ == lock["torch_version"], torch.__version__
assert ".".join(map(str, sys.version_info[:2])) == lock["python_version"]
for name, source in lock["sources"].items():
    owner_repo = source["repository"].removeprefix("https://github.com/")
    url = f"https://codeload.github.com/{owner_repo}/tar.gz/{source['revision']}"
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "source.tar.gz"
        urllib.request.urlretrieve(url, archive)
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == source["archive_sha256"], name
        unpacked = Path(tmp) / "source"
        with tarfile.open(archive) as tar:
            tar.extractall(unpacked, filter="data")
        entries = list(unpacked.iterdir())
        assert len(entries) == 1 and entries[0].is_dir(), name
        target = Path("/opt/src") / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(entries[0]), target)
    print(f"Verified {name} at {source['revision']}", flush=True)
