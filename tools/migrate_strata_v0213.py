"""Move the v0.2.13 + 95 Strata preparation into its pinned release directory."""

import argparse
import fcntl
import json
import os
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from doctor import STRATA_DRAFT_FILES, STRATA_PACK_FILES, check_prepared, require_file  # noqa: E402
from launcher import Recipe, discover_recipes, local_selections  # noqa: E402
from paths import data_home  # noqa: E402

VERSION = "v0.2.13-95-gdbb2d168"
ITEMS = ("packs", "mtp", "prepared.json")


def plan(recipe: Recipe, models: Path) -> list[tuple[Path, Path]]:
    root = models / recipe.data_subpath
    dest = root / "prepared" / VERSION
    if dest.resolve() != dest:
        raise ValueError(f"Redirected preparation path: {dest}")
    if dest.exists() and any(p.name not in ITEMS for p in dest.iterdir()):
        raise ValueError(f"Unexpected files in {dest}")
    locations = {}
    moves = []
    for item in ITEMS:
        old, new = root / item, dest / item
        if old.is_symlink() or new.is_symlink() or old.exists() == new.exists():
            raise ValueError(f"Expected exactly one original or migrated {item} in {root}")
        source = old if old.exists() else new
        locations[item] = source
        if source == old:
            parent = next(parent for parent in (dest, *dest.parents) if parent.exists())
            if old.stat().st_dev != parent.stat().st_dev:
                raise ValueError(f"Cannot rename across filesystems: {old} -> {new}")
            if old.is_dir():
                for link in old.rglob("*"):
                    if not link.is_symlink():
                        continue
                    target = link.readlink()
                    if target.is_absolute():
                        if any(target.is_relative_to(root / item) for item in ITEMS):
                            raise ValueError(f"Absolute link points into the old layout: {link}")
                    elif not (link.parent / target).resolve().is_relative_to(old):
                        raise ValueError(f"Relative link needs review before moving: {link}")
            moves.append((old, new))
    lock = json.loads((recipe.directory / "config/models.lock.json").read_text())
    versions = json.loads((recipe.runtime_directory / "container/versions.lock.json").read_text())
    if json.loads(locations["prepared.json"].read_text()) != {"models": lock, "image": versions}:
        raise ValueError(f"Model or runtime receipt mismatch: {root}")
    for item in lock["files"]:
        shard = root / "models" / item["path"]
        require_file(shard)
        if shard.stat().st_size != item["size_bytes"]:
            raise ValueError(f"Weight size differs from lock: {shard}")
    for name in (*STRATA_PACK_FILES, *(f"mtp/rt/{file}" for file in STRATA_DRAFT_FILES)):
        top, rest = name.split("/", 1)
        require_file(locations[top] / rest)
    return moves


def migrate(recipes: dict[str, Recipe], models: Path, apply: bool) -> None:
    with ExitStack() as locks:
        plans = []
        for recipe in recipes.values():
            if recipe.runtime != f"strata/releases/{VERSION}":
                continue
            root = models / recipe.data_subpath
            dest = root / "prepared" / VERSION
            if not any(os.path.lexists(p) for p in (dest, *(root / item for item in ITEMS))):
                continue
            if root.resolve() != root:
                raise ValueError(f"Redirected recipe path: {root}")
            if apply:
                lock_path = root / ".prepare.lock"
                if lock_path.is_symlink():
                    raise ValueError(f"Redirected preparation lock: {lock_path}")
                guard = locks.enter_context(lock_path.open("a"))
                fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            moves = plan(recipe, models)
            if moves and apply:
                if local_selections(recipe.name):
                    raise ValueError(f"Roll back the locally adopted trial for {recipe.name} first")
                running = subprocess.check_output(
                    [
                        "sudo",
                        "docker",
                        "ps",
                        "--filter",
                        f"label=io.llm-recipes.recipe={recipe.name}",
                        "--format",
                        "{{.Names}}",
                    ],
                    text=True,
                ).strip()
                if running:
                    raise ValueError(f"Stop the serving container first: {running}")
            for old, new in moves:
                print(f"{old} -> {new}")
            if not moves:
                print(f"Already migrated: {dest}")
            plans.append((recipe, moves))
        if not plans:
            print(f"No existing {VERSION} preparations found under {models}")
        if apply:
            for recipe, moves in plans:
                for old, new in moves:
                    new.parent.mkdir(parents=True, exist_ok=True)
                    old.rename(new)
                finding = check_prepared(recipe, models)
                if finding.status != "PASS":
                    raise ValueError(finding.detail)
                print(f"Verified: {recipe.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Perform the previewed moves")
    args = parser.parse_args()
    try:
        migrate(discover_recipes(ROOT / "recipes", local=False), data_home().resolve(), args.apply)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Migration stopped: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
