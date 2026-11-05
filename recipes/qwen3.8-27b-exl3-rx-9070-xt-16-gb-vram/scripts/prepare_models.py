#!/usr/bin/env python3
"""Download pinned artifacts and convert the DFlash2 draft inside the recipe image."""
import argparse
import hashlib
import json
from pathlib import Path

RECIPE = Path(__file__).resolve().parents[1]


def digest(path, algorithm="sha256", git_blob=False):
    result = hashlib.new(algorithm)
    if git_blob:
        result.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def verify(root, spec):
    manifest = json.loads((root / "prepared.json").read_text())
    if manifest["source"] != spec:
        raise RuntimeError(f"Source lock mismatch: {root}")
    if set(manifest["sha256"]) != set(spec["files"]):
        raise RuntimeError(f"Incomplete manifest: {root}")
    for filename, expected in manifest["sha256"].items():
        if digest(root / filename) != expected:
            raise RuntimeError(f"Checksum mismatch: {root / filename}")


def download(root, spec):
    from huggingface_hub import HfApi, hf_hub_download

    destination = root / spec["directory"]
    marker = destination / "source.json"
    if destination.exists():
        if not marker.exists() or json.loads(marker.read_text()) != spec:
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
        path = Path(hf_hub_download(spec["repo_id"], filename, revision=spec["revision"],
                                    local_dir=destination))
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


def quantize(root, lock):
    source = root / lock["draft"]["directory"]
    output = root / lock["conversion"]["directory"]
    work = root / lock["conversion"]["work_directory"]
    for path in (output, work):
        if path.exists():
            raise RuntimeError(f"Refusing to overwrite {path}; move it aside before a fresh conversion")
    verify(source, lock["draft"])

    import torch
    from exllamav3.conversion.convert_model import parser, prepare, main

    devices = [i for i in range(torch.cuda.device_count())
               if "RX 9070 XT" in torch.cuda.get_device_name(i)]
    if len(devices) != 1:
        raise RuntimeError(f"Expected exactly one RX 9070 XT, found {len(devices)}")
    arguments = ["-i", str(source), "-o", str(output), "-w", str(work),
                 "-d", str(devices[0]), *lock["conversion"]["arguments"]]
    print(f"Converter arguments: {arguments}", flush=True)
    args, state, ok, error = prepare(parser.parse_args(arguments))
    if not ok:
        raise RuntimeError(error)
    main(args, state)
    # Upstream's CLI can return success after a preparation error; call its API
    # above and validate the resulting artifacts before writing completion metadata.
    json.loads((output / "config.json").read_text())
    weights = list(output.glob("*.safetensors"))
    if not weights or any(path.stat().st_size == 0 for path in weights):
        raise RuntimeError("Converter produced no complete weight files")
    index = output / "model.safetensors.index.json"
    if index.exists():
        for filename in set(json.loads(index.read_text())["weight_map"].values()):
            if not (output / filename).is_file():
                raise RuntimeError(f"Missing converted shard: {filename}")
    files = [path for path in output.iterdir() if path.is_file()]
    write_json(output / "prepared.json", {
        "source": lock["draft"],
        "build": json.loads((RECIPE / "container/versions.lock.json").read_text()),
        "arguments": arguments,
        "sha256": {path.name: digest(path) for path in files},
    })
    print(f"Converted draft: {output}", flush=True)
    print(f"Weight size: {sum(path.stat().st_size for path in weights) / 1e9:.3f} GB")


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("download", "quantize-draft"))
    parser.add_argument("--models", type=Path, default=Path("/models"))
    args = parser.parse_args()
    image_lock = json.loads(Path("/opt/build/versions.lock.json").read_text())
    recipe_lock = json.loads((RECIPE / "container/versions.lock.json").read_text())
    if image_lock != recipe_lock:
        raise RuntimeError("Image build pins differ from the checkout; rebuild the recipe image")
    lock = json.loads((RECIPE / "models.lock.json").read_text())
    args.models.mkdir(parents=True, exist_ok=True)
    # One preparation process per mounted model directory, including downloads.
    import fcntl
    with (args.models / ".prepare.lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "download":
            for name in ("target", "draft"):
                download(args.models, lock[name])
        else:
            quantize(args.models, lock)


if __name__ == "__main__":
    cli()
