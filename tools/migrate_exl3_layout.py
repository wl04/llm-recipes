#!/usr/bin/env python3
"""Move the existing ExLlamaV3 1.6.6 draft into its release directory."""

import argparse
import fcntl
import hashlib
import json
import sys
from contextlib import ExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from paths import data_home  # noqa: E402

KEY = "v1.6.6-tabby-8f92fac5"
RECIPE = "qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram"
RUNTIME = f"exllamav3-tabbyapi/releases/{KEY}"


def migrate(models: Path, dry_run: bool) -> None:
    config = ROOT / "recipes" / RECIPE / "config"
    if json.loads((config / "launch.json").read_text())["runtime"] != RUNTIME:
        raise ValueError("This migration requires the recipe pinned to " + RUNTIME)
    spec = json.loads((config / "models.lock.json").read_text())
    conversion = spec["conversion"]
    build = json.loads((ROOT / "runtimes" / RUNTIME / "container/versions.lock.json").read_text())
    root = models.expanduser().resolve() / "recipes" / RECIPE
    dest = root / "prepared" / KEY
    if root.resolve() != root or not root.is_dir() or dest.resolve() != dest:
        raise ValueError(f"Missing or redirected recipe data directory: {root}")

    with ExitStack() as stack:
        guard = root / ".prepare.lock"
        if guard.is_symlink():
            raise ValueError(f"Redirected preparation lock: {guard}")
        if not dry_run or guard.exists():
            handle = stack.enter_context(guard.open("r" if dry_run else "a"))
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)

        moves = []
        draft = None
        for name in (conversion["directory"], conversion["work_directory"]):
            old, new = root / name, dest / name
            for path in (old, new):
                if path.is_symlink() or (path.exists() and not path.is_dir()):
                    raise ValueError(f"Expected a directory: {path}")
            if old.exists() and new.exists():
                raise ValueError(f"Both {old} and {new} exist; review them before migrating")
            if old.exists():
                moves.append((old, new))
            if name == conversion["directory"]:
                draft = old if old.exists() else new
        if draft is None or not draft.is_dir():
            raise ValueError(f"Missing converted draft under {root}")
        marker = draft / "prepared.json"
        if marker.is_symlink():
            raise ValueError(f"Redirected receipt: {marker}")
        receipt = json.loads(marker.read_text())
        if not isinstance(receipt, dict):
            raise ValueError(f"Invalid draft receipt: {marker}")
        args = receipt.get("arguments")
        expected = conversion["arguments"]
        if (
            receipt.get("source") != spec["draft"]
            or receipt.get("build") != build
            or not isinstance(args, list)
            or args[-len(expected) :] != expected
        ):
            raise ValueError(
                f"Draft receipt does not match the selected build and conversion: {marker}"
            )
        hashes = receipt.get("sha256")
        if not isinstance(hashes, dict) or not set(spec["draft"]["files"]).issubset(hashes):
            raise ValueError(f"Incomplete draft receipt: {marker}")
        for name, digest in hashes.items():
            # Older conversions hashed the source receipt copied by ExLlamaV3
            # immediately before replacing it with the conversion receipt.
            path = (
                root / spec["draft"]["directory"] / name
                if name == "prepared.json"
                else draft / name
            )
            if Path(name).name != name or path.is_symlink() or not path.is_file():
                raise ValueError(f"Missing or invalid artifact: {path}")
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                    raise ValueError(f"Checksum mismatch: {path}")
        if not moves:
            print(f"Verified existing preparation: {dest}")
        for old, new in moves:
            print(f"{'Would move' if dry_run else 'Moving'} {old} -> {new}")
            if not dry_run:
                dest.mkdir(parents=True, exist_ok=True)
                old.rename(new)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        type=Path,
        default=data_home(),
        help="Launcher data root (defaults to LLM_RECIPES_HOME or ~/llm-recipes)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify the draft and show the moves without writing files",
    )
    args = parser.parse_args()
    try:
        migrate(args.models, args.dry_run)
    except BlockingIOError:
        parser.exit(1, "Another preparation is active; retry after it finishes\n")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Migration failed: {error}\n")
