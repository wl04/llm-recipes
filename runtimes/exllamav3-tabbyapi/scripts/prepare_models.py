#!/usr/bin/env python3
"""Download pinned artifacts and convert the DFlash2 draft inside the recipe image."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import exl3_layout
import gpu

if TYPE_CHECKING:
    from model_artifacts import FileRecord

RUNTIME = Path(__file__).resolve().parents[1]


def digest(path: Path, algorithm: str = "sha256", git_blob: bool = False) -> str:
    result = hashlib.new(algorithm)
    if git_blob:
        result.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_json(path: Path, value: Any) -> None:  # noqa: ANN401 - JSON document
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def verify(root: Path, spec: dict[str, Any]) -> None:
    manifest = exl3_layout.read_object(root / "prepared.json")
    if manifest["source"] != spec:
        raise RuntimeError(f"Source lock mismatch: {root}")
    if set(manifest["sha256"]) != set(spec["files"]):
        raise RuntimeError(f"Incomplete manifest: {root}")
    for filename, expected in manifest["sha256"].items():
        if digest(root / filename) != expected:
            raise RuntimeError(f"Checksum mismatch: {root / filename}")


def download(root: Path, spec: dict[str, Any]) -> None:
    from huggingface_hub import HfApi, hf_hub_download  # pyright: ignore[reportMissingImports]

    destination = root / spec["directory"]
    marker = destination / "source.json"
    if destination.exists():
        if not marker.exists() or exl3_layout.read_object(marker) != spec:
            raise RuntimeError(f"Refusing to reuse an unrelated directory: {destination}")
    else:
        destination.mkdir()
        write_json(marker, spec)
    if (destination / "prepared.json").exists():
        verify(destination, spec)
        print(f"Verified existing download: {destination}", flush=True)
        return
    info = HfApi().model_info(spec["repo_id"], revision=spec["revision"], files_metadata=True)
    if info.sha != spec["revision"]:
        raise RuntimeError("Hub returned a different model revision")
    metadata = {item.rfilename: item for item in info.siblings}
    hashes = {}
    for filename in spec["files"]:
        item = metadata[filename]
        path = Path(
            hf_hub_download(
                spec["repo_id"], filename, revision=spec["revision"], local_dir=destination
            )
        )
        if path.stat().st_size != item.size:
            raise RuntimeError(f"Size mismatch: {filename}")
        sha256 = digest(path)
        if item.lfs:
            if sha256 != item.lfs.sha256:
                raise RuntimeError(f"LFS checksum mismatch: {filename}")
        elif digest(path, "sha1", git_blob=True) != item.blob_id:
            raise RuntimeError(f"Git blob checksum mismatch: {filename}")
        hashes[filename] = sha256
    write_json(destination / "prepared.json", {"source": spec, "sha256": hashes})
    print(f"Prepared: {destination}", flush=True)


def quantize(root: Path, prepared: Path, lock: dict[str, Any], build: dict[str, Any]) -> None:
    source = root / lock["draft"]["directory"]
    output = prepared / lock["conversion"]["directory"]
    work = prepared / lock["conversion"]["work_directory"]
    for path in (output, work):
        if path.exists():
            raise RuntimeError(
                f"Refusing to overwrite {path}; move it aside before a fresh conversion"
            )
    verify(source, lock["draft"])
    prepared.mkdir(parents=True, exist_ok=True)

    import torch  # pyright: ignore[reportMissingImports]
    from exllamav3.conversion.convert_model import main, parser, prepare  # pyright: ignore[reportMissingImports]

    names = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
    device = gpu.select_device(names)
    arguments = [
        "-i",
        str(source),
        "-o",
        str(output),
        "-w",
        str(work),
        "-d",
        str(device),
        *lock["conversion"]["arguments"],
    ]
    print(f"Converter arguments: {arguments}", flush=True)
    args, state, ok, error = prepare(parser.parse_args(arguments))
    if not ok:
        raise RuntimeError(error)
    main(args, state)
    # Upstream's CLI can return success after a preparation error; call its API
    # above and validate the resulting artifacts before writing completion metadata.
    exl3_layout.read_object(output / "config.json")
    weights = list(output.glob("*.safetensors"))
    if not weights or any(path.stat().st_size == 0 for path in weights):
        raise RuntimeError("Converter produced no complete weight files")
    index = output / "model.safetensors.index.json"
    if index.exists():
        for filename in set(exl3_layout.read_object(index)["weight_map"].values()):
            if not (output / filename).is_file():
                raise RuntimeError(f"Missing converted shard: {filename}")
    files = [path for path in output.iterdir() if path.is_file() and path.name != "prepared.json"]
    write_json(
        output / "prepared.json",
        {
            "source": lock["draft"],
            "build": build,
            "arguments": arguments,
            "sha256": {path.name: digest(path) for path in files},
        },
    )
    print(f"Converted draft: {output}", flush=True)
    print(f"Weight size: {sum(path.stat().st_size for path in weights) / 1024**3:.3f} GiB")


def checked_records(
    folder: Path, manifest: dict[str, Any], *, verify: bool
) -> dict[str, FileRecord]:
    from model_artifacts import inventory, verify_inventory

    checksums = manifest["sha256"]
    exl3_layout.check_inventory(folder, set(checksums))
    recorded: dict[str, FileRecord] | None = manifest.get("inventory")
    if recorded is None:
        recorded = inventory(folder, sorted(checksums))
    else:
        verify_inventory(folder, recorded, verify=verify)
    if checksums != {name: row["sha256"] for name, row in recorded.items()}:
        raise ValueError(f"EXL3 checksum mismatch: {folder}")
    return recorded


def conversion_matches(manifest: dict[str, Any], lock: dict[str, Any]) -> bool:
    arguments = lock["conversion"]["arguments"]
    recorded = manifest.get("arguments")
    return (
        manifest.get("source") == lock["draft"]
        and manifest.get("target", lock["target"]) == lock["target"]
        and isinstance(recorded, list)
        and bool(arguments)
        and recorded[-len(arguments) :] == arguments
    )


def prepare_local(
    root: Path,
    prepared: Path,
    donor_key: str,
    lock: dict[str, Any],
    build: dict[str, Any],
    *,
    use_draft: bool = True,
    allow_copy: bool = False,
    verify_local: bool = False,
) -> None:
    """Publish a candidate draft from a verified local donor or verified original weights."""
    from model_artifacts import artifact_path, stage_files, staged_preparation

    if prepared == root or not (
        donor_key == "base" or re.fullmatch(r"v[0-9][A-Za-z0-9.-]{0,126}", donor_key)
    ):
        raise ValueError("Local preparation needs a versioned candidate and a valid donor key")
    target_spec = lock["target"]
    target_folder = artifact_path(root, target_spec["directory"])
    target_manifest = exl3_layout.read_object(artifact_path(target_folder, "prepared.json"))
    if target_manifest.get("source") != target_spec or set(target_manifest["sha256"]) != set(
        target_spec["files"]
    ):
        raise ValueError(f"Locked EXL3 target differs from {target_folder / 'prepared.json'}")
    directory = lock["conversion"]["directory"]
    donor_root = root if donor_key == "base" else root / "prepared" / donor_key
    source = artifact_path(donor_root, directory)
    output = artifact_path(prepared, directory)
    if use_draft and prepared.exists():
        existing = exl3_layout.read_object(artifact_path(output, "prepared.json"))
        if existing.get("build") != build or not conversion_matches(existing, lock):
            raise ValueError(f"Conflicting EXL3 draft preparation: {output}")
        target_manifest["inventory"] = existing.get("target_inventory")
        checked_records(target_folder, target_manifest, verify=verify_local)
        checked_records(output, existing, verify=verify_local)
        print(f"{root.name}: reusing locked EXL3 target and candidate draft", flush=True)
        return
    previous = {}
    if use_draft and (source / "prepared.json").is_file():
        previous = exl3_layout.read_object(artifact_path(source, "prepared.json"))
        if previous.get("target") == target_spec and previous.get("target_inventory"):
            target_manifest["inventory"] = previous["target_inventory"]
    target_inventory = checked_records(target_folder, target_manifest, verify=verify_local)
    print(f"{root.name}: reusing locked EXL3 target", flush=True)
    if not use_draft:
        return
    with staged_preparation(prepared, {"image": build, "models": lock}) as stage:
        draft = stage / directory
        if conversion_matches(previous, lock):
            records = checked_records(source, previous, verify=verify_local)
            files = stage_files(source, draft, records, allow_copy=allow_copy)
            manifest = previous
            producer = manifest.get("producer", manifest["build"])
            print(f"{root.name}: reused converted draft from {source}", flush=True)
        else:
            print(f"{root.name}: rebuilding draft (no compatible conversion)", flush=True)
            quantize(root, stage, lock, build)
            manifest = exl3_layout.read_object(draft / "prepared.json")
            files = checked_records(draft, manifest, verify=False)
            producer = build
            work = artifact_path(stage, lock["conversion"]["work_directory"])
            if work.exists():
                try:
                    shutil.rmtree(work)
                except OSError as error:
                    raise ValueError(f"Cannot remove converter work at {work}: {error}") from error
        write_json(
            draft / "prepared.json",
            {
                **manifest,
                "build": build,
                "producer": producer,
                "target": target_spec,
                "inventory": files,
                "target_inventory": target_inventory,
            },
        )


@contextmanager
def preparation_lock(models: Path) -> Iterator[None]:
    """Hold the preparation lock; refuse to start when another process holds it."""
    guard = (models / ".prepare.lock").open("a")
    try:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit(
                f"Another preparation is already running in {models}; wait for it to finish"
            ) from exc
        yield
    finally:
        guard.close()


def model_root(recipe: Path, models: Path) -> Path:
    """Resolve the recipe's data folder under the models mount: recipes/<recipe>."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,159}", recipe.name):
        raise ValueError("recipe folder name must match the recipe identifier")
    return models / "recipes" / recipe.name


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("action", choices=("download", "quantize-draft", "upgrade-local"))
    parser.add_argument("--models", type=Path, default=Path("/models"))
    parser.add_argument("--donor", default="base")
    parser.add_argument("--allow-copy", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--no-draft", action="store_true")
    args = parser.parse_args()
    recipe = args.recipe.resolve()
    try:
        pins = exl3_layout.selection(recipe)
        args.models = model_root(recipe, args.models)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    image_lock = exl3_layout.read_object(Path("/opt/build/versions.lock.json"))
    recipe_lock = exl3_layout.read_object(RUNTIME / pins / "container/versions.lock.json")
    if image_lock != recipe_lock:
        raise RuntimeError("Image build pins differ from the checkout; rebuild the recipe image")
    lock = exl3_layout.read_object(recipe / "config/models.lock.json")
    args.models.mkdir(parents=True, exist_ok=True)
    # One preparation process per mounted model directory, including downloads.
    with preparation_lock(args.models):
        if args.action == "download":
            for name in ("target", "draft"):
                download(args.models, lock[name])
        elif args.action == "quantize-draft":
            quantize(args.models, exl3_layout.prepared_root(args.models, pins), lock, image_lock)
        else:
            sys.path.append("/repo-scripts")
            try:
                prepare_local(
                    args.models,
                    exl3_layout.prepared_root(args.models, pins),
                    args.donor,
                    lock,
                    image_lock,
                    use_draft=not args.no_draft,
                    allow_copy=args.allow_copy,
                    verify_local=args.verify,
                )
            except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
                parser.exit(1, f"{recipe.name}: {error}\n")


if __name__ == "__main__":
    cli()
