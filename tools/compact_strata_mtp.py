"""Consolidate completed Strata preparations' raw MTP tensors into the shared cache."""

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtimes/strata"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(RUNTIME / "scripts"))

from mtp_source import cache_path, shared_source, tensor_hashes, validate  # noqa: E402

from runtimes.strata.scripts.prepare_models import pinned_mtp_revision, validate_outputs  # noqa: E402


def offline_only(path: Path) -> None:
    raise ValueError("No complete local MTP source was available to seed the cache")


def compact(models: Path, revision: str, hashes: dict[str, str], apply: bool) -> None:
    recipes = models / "recipes"
    groups: dict[str, list[Path]] = defaultdict(list)
    with ExitStack() as locks:
        locked = set()
        for pattern in ("*/prepared.json", "*/prepared/*/prepared.json"):
            for receipt in sorted(recipes.glob(pattern)):
                if receipt.parent.name.startswith("."):
                    continue
                source = receipt.parent / "mtp"
                tensors = source / "tensors"
                if not tensors.is_dir() or not any((tensors / f"{n}.bin").exists() for n in hashes):
                    continue
                if tensors.resolve() != tensors or receipt.resolve() != receipt:
                    raise ValueError(f"Redirected preparation: {source}")
                root = recipes / receipt.relative_to(recipes).parts[0]
                if apply and root not in locked:
                    lock = root / ".prepare.lock"
                    if lock.is_symlink():
                        raise ValueError(f"Redirected preparation lock: {lock}")
                    guard = locks.enter_context(lock.open("a"))
                    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked.add(root)
                mtp = json.loads(receipt.read_text())["models"]["mtp"]
                if mtp["revision"] != revision:
                    print(f"Skipping another checkpoint revision: {source}")
                    continue
                validate_outputs(receipt.parent)
                groups[mtp["repository"]].append(source)

        if not groups:
            print("No duplicate raw MTP tensors found.")
        for repository, sources in groups.items():
            ready = cache_path(models, repository, revision)
            if ready.resolve() != ready:
                raise ValueError(f"Redirected cache: {ready}")
            url = f"https://huggingface.co/{repository}/resolve/{revision}/"
            cached = ready.exists()
            if cached:
                validate(ready, url, hashes)
            removals = []
            for source in sources:
                inventory = json.loads((source / "mtp-inventory.json").read_text())
                if inventory.get("repo") != url:
                    raise ValueError(f"Checkpoint mismatch: {source}")
                if not cached:
                    validate(source, url, hashes)
                size = 0
                for name, digest in hashes.items():
                    path = source / "tensors" / f"{name}.bin"
                    if path.is_symlink():
                        raise ValueError(f"Redirected tensor: {path}")
                    if path.exists() and not path.is_file():
                        raise ValueError(f"Expected a tensor file: {path}")
                    if not path.exists():
                        continue  # An interrupted cleanup may have removed verified duplicates.
                    if cached:
                        with path.open("rb") as stream:
                            if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                                raise ValueError(f"Tensor checksum mismatch: {path}")
                    removals.append(path)
                    size += path.stat().st_size
                print(f"{source / 'tensors'}  ({size / 2**30:.2f} GiB of duplicate files)")
            print(
                f"Shared source: {ready}" + ("" if ready.exists() else " (requires one local copy)")
            )
            if apply:
                if not cached:
                    shared_source(models, repository, revision, hashes, offline_only)
                for path in removals:
                    path.unlink()
                print(f"Removed {len(removals)} verified duplicate tensor files.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Import locally and remove verified duplicates"
    )
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.inside:
            if json.loads(Path("/opt/build/versions.lock.json").read_text()) != json.loads(
                (RUNTIME / "container/versions.lock.json").read_text()
            ):
                raise ValueError("Image lock differs from the checkout")
            fetch = Path("/opt/src/strata/tools/mtp_fetch.py")
            compact(Path("/models"), pinned_mtp_revision(fetch), tensor_hashes(fetch), args.apply)
            return 0
        sys.path.insert(0, str(ROOT / "scripts"))
        from paths import data_home

        models = data_home().resolve()
        if not models.is_dir():
            raise ValueError(f"Model directory does not exist: {models}")
        image = json.loads((RUNTIME / "runtime.json").read_text())["image"]
        command = [
            "sudo",
            "docker",
            "run",
            "--pull=never",
            "--rm",
            "--network=none",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--mount",
            f"type=bind,src={ROOT},dst=/repo,readonly",
            "--mount",
            f"type=bind,src={models},dst=/models" + ("" if args.apply else ",readonly"),
            "--entrypoint",
            "python3",
            image,
            "/repo/tools/compact_strata_mtp.py",
            "--inside",
        ]
        if args.apply:
            command.append("--apply")
        return subprocess.run(command, check=False).returncode
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f"Compaction stopped: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
