"""Download verified model files and prepare Strata packs in an external directory."""

import argparse
import ast
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

from recipe_config import recipe_paths

RUNTIME = Path(__file__).resolve().parents[1]


def verify(path: Path, size: int, digest: str) -> None:
    """Check both the expected size and SHA-256; preserve invalid files for inspection."""
    if path.stat().st_size != size:
        raise ValueError(f"Size mismatch: {path}; expected {size} bytes")
    print(f"Verifying {path.name}…", flush=True)
    with path.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != digest:
        raise ValueError(f"SHA-256 checksum mismatch: {path}; move the file aside before retrying")


def download(url: str, path: Path, size: int, digest: str) -> None:
    """Resume into a .part file, then atomically publish only verified bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        verify(path, size, digest)
        return
    partial = path.with_name(path.name + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > size:
        raise ValueError(f"Oversized partial download: {partial}")
    if offset < size:
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        request = urllib.request.Request(url, headers=headers)
        print(f"Downloading {path.name}: {offset:,}/{size:,} bytes", flush=True)
        with urllib.request.urlopen(request, timeout=120) as response:
            if offset and (
                response.status != 206
                or response.headers.get("Content-Range") != f"bytes {offset}-{size - 1}/{size}"
            ):
                raise ValueError(f"Server did not honor the resume range for {path.name}")
            with partial.open("ab" if offset else "wb") as output:
                reported = offset
                while block := response.read(8 * 1024 * 1024):
                    if offset + len(block) > size:
                        raise ValueError(f"Response exceeds locked file size: {path.name}")
                    output.write(block)
                    offset += len(block)
                    if offset - reported >= 1024**3:
                        print(f"{path.name}: {offset:,}/{size:,} bytes", flush=True)
                        reported = offset
    verify(partial, size, digest)
    partial.replace(path)


def pinned_mtp_revision(source: Path) -> str:
    """Read the downloader's literal revision without executing upstream code."""
    for node in ast.parse(source.read_text()).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "PINNED_REVISION"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, str):
                return value
    raise ValueError("Pinned MTP revision missing from the image")


def pack_arguments(lock: dict[str, Any], root: Path) -> list[str]:
    """Select the first shard for any split count and the locked conversion options."""
    first = [item for item in lock["files"] if re.search(r"-00001-of-\d{5}\.gguf$", item["path"])]
    if len(first) != 1:
        raise ValueError("Model lock must contain exactly one first shard")
    args = ["--gguf", str(root / "models" / first[0]["path"]), "--out", str(root / "packs/iq3_xxs")]
    if lock.get("pack", {}).get("compat_bf16", False):
        args.append("--compat-bf16")
    return args


def prepare(recipe: Path, root: Path) -> None:
    """Prepare the locked target, CPU projector, tokenizer, and Q2_0 MTP runtime."""
    config, _ = recipe_paths(recipe)
    lock = json.loads((config / "models.lock.json").read_text())
    versions = json.loads((RUNTIME / "container/versions.lock.json").read_text())
    if json.loads(Path("/opt/build/versions.lock.json").read_text()) != versions:
        raise ValueError("Image lock differs from the recipe; rebuild the image")
    tools = Path("/opt/src/strata/tools")
    if pinned_mtp_revision(tools / "mtp_fetch.py") != lock["mtp"]["revision"]:
        raise ValueError("MTP revision differs from the pinned upstream downloader")
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".prepare.lock").open("w") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt = root / "prepared.json"
        receipt.unlink(missing_ok=True)
        for item in lock["files"]:
            url = (
                f"https://huggingface.co/{item.get('repository', lock['repository'])}/resolve/"
                f"{item.get('revision', lock['revision'])}/{item['path']}"
            )
            download(url, root / "models" / item["path"], item["size_bytes"], item["sha256"])
        environment = dict(
            os.environ,
            STRATA_GGUF_PY="/opt/src/llama_cpp/gguf-py",
            STRATA_MTP_REVISION=lock["mtp"]["revision"],
            STRATA_ALLOW_UNPINNED="0",
            STRATA_SOURCE="huggingface",
            HF_ENDPOINT="https://huggingface.co",
        )

        def run(script: str, *args: str) -> None:
            subprocess.run(
                [sys.executable, str(tools / script), *args], env=environment, check=True
            )

        pack = root / "packs/iq3_xxs"
        run("iq_pack.py", *pack_arguments(lock, root))
        mtp = root / "mtp"
        run("mtp_fetch.py", "fetch", "--out", str(mtp))
        run("mtp_fetch.py", "verify", "--out", str(mtp))
        intermediate = mtp / "mtp-q2_0.gguf"
        run(
            "mtp_pack.py",
            "--src",
            str(mtp),
            "--experts",
            lock["mtp"]["expert_quantization"],
            "--out",
            str(intermediate),
        )
        run("mtp_rt.py", "--gguf", str(intermediate), "--out", str(mtp / "rt"))
        shutil.copyfile(
            tools.parent / "data" / lock["mtp"]["draft_vocabulary"], mtp / "rt/draft_vocab.bin"
        )
        required = [
            pack / "native_experts.txt",
            pack / "index.txt",
            pack / "dense.bin",
            pack / "tokenizer/chat_template.jinja",
            pack / "tokenizer/vocab.json",
            pack / "tokenizer/tokenizer.json",
            mtp / "rt/experts.bin",
            mtp / "rt/dense.bin",
            mtp / "rt/dense.txt",
            mtp / "rt/draft_vocab.bin",
        ]
        for path in required:
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f"Missing preparation output: {path}")
        temporary = receipt.with_suffix(".tmp")
        temporary.write_text(json.dumps({"models": lock, "image": versions}, indent=2) + "\n")
        temporary.replace(receipt)
        print(
            f"Prepared Strata model, tokenizer, MTP, and CPU vision files under {root}", flush=True
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, default=Path.home() / "Models/llm-recipes")
    parser.add_argument("--recipe", type=Path, required=True, help="recipe directory")
    parser.add_argument("--inside-container", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    recipe = args.recipe.expanduser().resolve()
    try:
        _, folder = recipe_paths(recipe)
        if args.inside_container:
            prepare(recipe, Path("/models") / folder)
            return 0
        models = args.models.expanduser().resolve()
        if any(char in str(models) + str(recipe) + str(RUNTIME) for char in (",", "\n")):
            raise ValueError("Mount paths must not contain commas or newlines")
        models.mkdir(parents=True, exist_ok=True)
        (models / ".cache").mkdir(exist_ok=True)
        manifest = json.loads((RUNTIME / "runtime.json").read_text())
        command = [
            "sudo",
            "docker",
            "run",
            "--rm",
            "--init",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--env",
            "HOME=/tmp",
            "--env",
            "XDG_CACHE_HOME=/cache",
            "--mount",
            f"type=bind,src={recipe},dst=/recipe,readonly",
            "--mount",
            f"type=bind,src={RUNTIME},dst=/runtime,readonly",
            "--mount",
            f"type=bind,src={models},dst=/models",
            "--mount",
            f"type=bind,src={models / '.cache'},dst=/cache",
            manifest["image"],
            "python3",
            "/runtime/scripts/prepare_models.py",
            "--recipe",
            "/recipe",
            "--inside-container",
        ]
        return subprocess.run(command, check=False).returncode
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Preparation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
