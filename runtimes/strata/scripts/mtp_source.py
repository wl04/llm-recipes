"""Share verified BF16 draft tensors across Strata preparations."""

import ast
import fcntl
import hashlib
import json
import math
import re
import shutil
from collections.abc import Callable
from pathlib import Path


def tensor_hashes(fetch_script: Path) -> dict[str, str]:
    """Read the expected tensor names and hashes from the pinned engine."""
    for node in ast.parse(fetch_script.read_text()).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "SHA256" for target in node.targets
        ):
            hashes = ast.literal_eval(node.value)
            if (
                isinstance(hashes, dict)
                and hashes
                and all(
                    isinstance(name, str)
                    and re.fullmatch(r"[\w.-]+", name)
                    and isinstance(digest, str)
                    and re.fullmatch("[0-9a-f]{64}", digest)
                    for name, digest in hashes.items()
                )
            ):
                return hashes
    raise ValueError(f"No complete tensor SHA-256 table in {fetch_script}")


def validate(source: Path, url: str, hashes: dict[str, str]) -> None:
    inventory = json.loads((source / "mtp-inventory.json").read_text())
    manifest = json.loads((source / "mtp-manifest.json").read_text())
    if not isinstance(inventory, dict) or inventory.get("repo") != url:
        raise ValueError(f"Different MTP checkpoint at {source}")
    if not isinstance(manifest, list) or len(manifest) != len(hashes):
        raise ValueError(f"Incomplete tensor manifest at {source}")
    seen = set()
    for row in manifest:
        if not isinstance(row, dict):
            raise ValueError(f"Invalid tensor manifest at {source}")
        name = row.get("name")
        if not isinstance(name, str) or name not in hashes or name in seen:
            raise ValueError(f"Unexpected tensor {name!r} at {source}")
        seen.add(name)
        relative = f"tensors/{name}.bin"
        shape = row.get("shape")
        path = source / relative
        if (
            row.get("file") != relative
            or row.get("dtype") != "BF16"
            or row.get("sha256") != hashes[name]
            or not isinstance(shape, list)
            or not shape
            or not all(type(dim) is int and dim > 0 for dim in shape)
            or not path.is_file()
            or path.resolve() != path.absolute()
            or path.stat().st_size != 2 * math.prod(shape)
        ):
            raise ValueError(f"Invalid MTP tensor metadata: {path}")
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != hashes[name]:
                raise ValueError(f"MTP tensor checksum mismatch: {path}")


def cache_path(models: Path, repository: str, revision: str) -> Path:
    if (
        not re.fullmatch(r"[\w.-]+/[\w.-]+", repository)
        or any(part in (".", "..") for part in repository.split("/"))
        or not re.fullmatch("[a-f0-9]{40}", revision)
    ):
        raise ValueError("Expected a Hugging Face repository and a pinned MTP commit")
    return models / ".cache/strata/mtp" / repository / revision


def shared_source(
    models: Path,
    repository: str,
    revision: str,
    hashes: dict[str, str],
    fetch: Callable[[Path], None],
) -> Path:
    ready = cache_path(models, repository, revision)
    parent = ready.parent
    url = f"https://huggingface.co/{repository}/resolve/{revision}/"
    parent.mkdir(parents=True, exist_ok=True)
    with (parent / f"{revision}.lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        if ready.exists():
            validate(ready, url, hashes)
            print(f"Reusing verified MTP source: {ready}", flush=True)
            return ready
        recipes = models / "recipes"
        stage = parent / f"{revision}.import"
        for pattern in ("*/prepared/*/prepared.json", "*/prepared.json"):
            for receipt in sorted(recipes.glob(pattern)):
                donor = receipt.parent / "mtp"
                if not (donor / "mtp-manifest.json").is_file():
                    continue
                try:
                    mtp = json.loads(receipt.read_text())["models"]["mtp"]
                    if mtp["repository"] != repository or mtp["revision"] != revision:
                        continue
                    if stage.exists():
                        shutil.rmtree(stage)
                    (stage / "tensors").mkdir(parents=True)
                    for metadata in ("mtp-inventory.json", "mtp-manifest.json"):
                        shutil.copyfile(donor / metadata, stage / metadata)
                    for name in hashes:
                        file = Path("tensors") / f"{name}.bin"
                        shutil.copyfile(donor / file, stage / file)
                    validate(stage, url, hashes)
                except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
                    print(f"Skipping MTP source {donor}: {error}", flush=True)
                    continue
                stage.rename(ready)
                print(f"Imported verified MTP source from {donor}", flush=True)
                return ready
        if stage.exists():
            shutil.rmtree(stage)
        partial = parent / f"{revision}.partial"
        print(f"Fetching MTP source into {partial}", flush=True)
        fetch(partial)
        validate(partial, url, hashes)
        partial.rename(ready)
        return ready
