#!/usr/bin/env python3
"""Prepare and check an isolated Strata release on the RX 9070 XT workstation."""

import argparse
import fcntl
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from launcher import gpu_access_args, gpu_groups
from paths import data_home

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path("runtimes/strata")
LOCK = RUNTIME / "container/versions.lock.json"
DESCRIPTOR = RUNTIME / "runtime.json"
BASE = "rocm/dev-ubuntu-24.04"
RECIPE = "qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram"
ENGINE = "engine/CMakeLists.txt"
TARGETS = "engine/cmake/strata_gpu_engine.cmake"
VISION = "terminal/tools/vision/CMakeLists.txt"
MTP = "terminal/tools/mtp_fetch.py"


def output(*cmd: str, cwd: Path = ROOT) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True).strip()


def worktree(root: Path, key: str) -> Path:
    """Create a sibling trial or resume the matching worktree of this repository."""
    branch = f"strata-{key}"
    path = root.with_name(f"{root.name}-{branch}")
    if path.exists():
        for directory in (path, root):
            if Path(output("git", "rev-parse", "--show-toplevel", cwd=directory)) != directory:
                raise ValueError(f"Expected a checkout at {directory}")
        git_dir = ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"]
        if (
            output(*git_dir, cwd=path) != output(*git_dir, cwd=root)
            or output("git", "branch", "--show-current", cwd=path) != branch
        ):
            raise ValueError(f"Another checkout occupies {path}")
        reference = output("git", "rev-parse", "HEAD", cwd=root)
        if output("git", "rev-parse", "HEAD", cwd=path) != reference:
            if output("git", "status", "--porcelain", cwd=path):
                raise ValueError(f"Review the changes in {path} before updating its reference")
            subprocess.run(
                ["git", "merge", "--ff-only", reference],
                cwd=path,
                check=True,
            )
    else:
        subprocess.run(
            ["git", "worktree", "add", "-b", branch, str(path), "HEAD"], cwd=root, check=True
        )
    return path


def inspect_source(files: dict[str, str], revision: str, vocabulary: str) -> str:
    """Check the build and preparation contract against the downloaded release."""
    required = [
        MTP,
        ENGINE,
        TARGETS,
        VISION,
        "terminal/serve/server.py",
        "terminal/tools/iq_pack.py",
        "terminal/tools/mtp_pack.py",
        "terminal/tools/mtp_rt.py",
        "terminal/data/expert-profile.bin",
        f"terminal/data/{vocabulary}",
    ]
    for name in required:
        if name not in files:
            raise ValueError(f"Unsupported Strata layout: missing {name}")
    for name, target in [(TARGETS, "strata"), (VISION, "strata-vision")]:
        if not re.search(r"add_executable\(\s*" + target + r"\s", files[name], re.I):
            raise ValueError(f"Missing CMake target {target} in {name}")
    version = re.search(r"project\(\s*strata\s+VERSION\s+([\d.]+)\b", files[ENGINE], re.I)
    if not version:
        raise ValueError(f"Missing Strata project version in {ENGINE}")
    if not re.search(
        rf"""^PINNED_REVISION\s*=\s*["']{re.escape(revision)}["']""", files[MTP], re.M
    ):
        raise ValueError("Upstream MTP revision differs from the recipe model lock")
    return version[1]


def release(tag: str, mtp: dict[str, str], options: dict[str, bool]) -> tuple[str, str, str]:
    repo = "https://github.com/Niko1221/Strata.git"
    ref = f"refs/tags/{tag}"
    lines = output("git", "ls-remote", "--exit-code", repo, ref, ref + "^{}")
    refs = dict(line.split()[::-1] for line in lines.splitlines())
    revision = refs.get(ref + "^{}", refs[ref])
    if not re.fullmatch("[0-9a-f]{40}", revision):
        raise ValueError(f"Invalid Git revision for {tag}")
    url = f"https://codeload.github.com/Niko1221/Strata/tar.gz/{revision}"
    with tempfile.TemporaryFile() as archive:
        with urllib.request.urlopen(url, timeout=120) as response:
            shutil.copyfileobj(response, archive)
        archive.seek(0)
        digest = hashlib.file_digest(archive, "sha256").hexdigest()
        archive.seek(0)
        files: dict[str, str] = {}
        with tarfile.open(fileobj=archive, mode="r|gz") as source:
            for member in source:
                if not member.isfile():
                    continue
                name = member.name.partition("/")[2]
                files[name] = ""
                engine_cmake = name.startswith("engine/") and name.endswith(".cmake")
                if name in (ENGINE, TARGETS, VISION, MTP) or (options and engine_cmake):
                    stream = source.extractfile(member)
                    if stream is None:
                        raise ValueError(f"Cannot read {name}")
                    files[name] = stream.read().decode()
    declarations = "\n".join(text for name, text in files.items() if name.startswith("engine/"))
    for key in options:
        if not re.search(rf"(?im)^\s*option\(\s*{key}\s", declarations):
            raise ValueError(f"Engine does not declare Boolean CMake option {key} in {tag}")
    return revision, digest, inspect_source(files, mtp["revision"], mtp["draft_vocabulary"])


def base_image(tag: str) -> str:
    url = f"https://hub.docker.com/v2/repositories/{BASE}/tags/{tag}"
    with urllib.request.urlopen(url, timeout=30) as response:
        data = json.load(response)
    matches = [
        item["digest"]
        for item in data["images"]
        if item["architecture"] == "amd64" and item["os"] == "linux"
    ]
    if len(matches) != 1 or not re.fullmatch(r"sha256:[0-9a-f]{64}", matches[0]):
        raise ValueError(f"Expected one Linux amd64 manifest for {BASE}:{tag}")
    return f"{BASE}@{matches[0]}"


def settings(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text())
    if not isinstance(config, dict) or set(config) != {
        "base_tag",
        "image_suffix",
        "engine_options",
        "max_jobs",
    }:
        raise ValueError("Expected base_tag, image_suffix, engine_options and max_jobs in config")
    if not re.fullmatch(r"[\w][\w.-]{0,127}", config["base_tag"], re.ASCII):
        raise ValueError("Invalid ROCm tag")
    if not re.fullmatch(r"(?:-[a-z0-9][a-z0-9.-]*)?", config["image_suffix"]):
        raise ValueError("image_suffix must be empty or a lowercase suffix beginning with '-'")
    if type(config["max_jobs"]) is not int or config["max_jobs"] < 1:
        raise ValueError("max_jobs must be a positive integer")
    options = config["engine_options"]
    fixed = {"STRATA_ENABLE_HIP", "STRATA_ENABLE_CUDA", "STRATA_BUILD_TESTS", "STRATA_PORTABLE"}
    if not isinstance(options, dict) or any(
        not re.fullmatch(r"STRATA_[A-Z0-9_]+", key) or key in fixed or type(value) is not bool
        for key, value in options.items()
    ):
        raise ValueError("engine_options takes additional STRATA_* Boolean CMake options")
    return config


def build_or_check(candidate: Path, image: str, lock: dict[str, Any], jobs: int) -> None:
    image_id = output("sudo", "docker", "image", "ls", "--no-trunc", "-q", image)
    if image_id:
        saved = output(
            "sudo",
            "docker",
            "run",
            "--rm",
            "--network=none",
            "--entrypoint",
            "cat",
            image_id,
            "/opt/build/versions.lock.json",
        )
        if json.loads(saved) != lock:
            raise ValueError(f"{image} already has different inputs; select a new image_suffix")
        print(f"Checking existing image {image}", flush=True)
        subprocess.run(
            ["sudo", "docker", "run", "--rm", *gpu_access_args(gpu_groups()), image_id], check=True
        )
    else:
        subprocess.run(
            [
                sys.executable,
                "scripts/build_runtime.py",
                "strata",
                "--check",
                "--max-jobs",
                str(jobs),
            ],
            cwd=candidate,
            check=True,
        )


def upgrade(tag: str, config: dict[str, Any], prepare_only: bool) -> None:
    key = tag + config["image_suffix"]
    if not re.fullmatch(r"v\d+(?:\.\d+)+(?:-[a-zA-Z0-9.-]+)?", tag) or len(key) > 128:
        raise ValueError("Expected a Strata release tag such as v0.2.18")
    descriptor = json.loads((ROOT / DESCRIPTOR).read_text())
    lock = json.loads((ROOT / LOCK).read_text())
    mtp = json.loads((ROOT / "recipes" / RECIPE / "config/models.lock.json").read_text())["mtp"]
    rev, digest, version = release(tag, mtp, config["engine_options"])
    base = base_image(config["base_tag"])
    image = descriptor["image"].rsplit(":", 1)[0] + ":" + key
    print(
        f"Strata: {descriptor['engine_source_version']} -> {tag} ({rev})\n"
        f"Engine: {descriptor['engine_version']} -> {version}\n"
        f"ROCm: {lock['base_tag']} -> {config['base_tag']} ({base})\nImage: {image}",
        flush=True,
    )
    candidate = worktree(ROOT, key)
    # Include all tracked container build inputs except the generated lock itself.
    fingerprint = hashlib.sha256()
    container = LOCK.parent
    for name in sorted(output("git", "ls-files", str(container), cwd=candidate).splitlines()):
        if Path(name) != LOCK:
            fingerprint.update(
                name.encode() + b"\0" + hashlib.sha256((candidate / name).read_bytes()).digest()
            )
    lock.update(
        base_image=base,
        base_tag=config["base_tag"],
        layout="engine-terminal",
        engine_options=config["engine_options"],
        build_inputs_sha256=fingerprint.hexdigest(),
    )
    lock["sources"]["strata"].update(revision=rev, sha256=digest)
    descriptor.update(engine_version=version, engine_source_version=tag, image=image)
    generated = {LOCK: lock, DESCRIPTOR: descriptor}
    for path, value in generated.items():
        current = json.loads((candidate / path).read_text())
        if current not in (value, json.loads((ROOT / path).read_text())):
            raise ValueError(
                f"Different candidate inputs in {candidate / path}; use an image_suffix"
            )
    for path, value in generated.items():
        dest = candidate / path
        with tempfile.NamedTemporaryFile("w", dir=dest.parent, delete=False) as pending:
            pending.write(json.dumps(value, indent=2) + "\n")
        Path(pending.name).chmod(0o644)
        Path(pending.name).replace(dest)
    if not prepare_only:
        build_or_check(candidate, image, lock, config["max_jobs"])
    models = data_home().absolute()
    trial = models.with_name(f"{models.name}-strata-{key}")
    folder = Path("recipes") / RECIPE
    print(f"\nCandidate checkout: {candidate}\nCandidate model root: {trial}")
    if prepare_only:
        print(
            "Image build skipped. Run the same command without --prepare-only to build and check."
        )
        return
    for cmd in [
        ["cd", str(candidate)],
        ["mkdir", "-p", str(trial / folder / "models")],
        [
            "cp",
            "-a",
            "--reflink=auto",
            str(models / folder / "models") + "/.",
            str(trial / folder / "models"),
        ],
        [
            "python3",
            "runtimes/strata/scripts/prepare_models.py",
            "--recipe",
            str(folder),
            "--models",
            str(trial),
        ],
        ["python3", "scripts/launch.py", "doctor", RECIPE, "--models", str(trial)],
        ["python3", "scripts/launch.py", "start", RECIPE, "--models", str(trial), "--detach"],
    ]:
        print(shlex.join(cmd))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--config", type=Path, default=ROOT / RUNTIME / "upgrade.json")
    parser.add_argument(
        "--prepare-only", action="store_true", help="Resolve and write inputs; skip Docker"
    )
    args = parser.parse_args()
    try:
        common = Path(output("git", "rev-parse", "--path-format=absolute", "--git-common-dir"))
        with (common / "strata-upgrade.lock").open("a") as guard:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            upgrade(args.tag, settings(args.config), args.prepare_only)
    except BlockingIOError:
        parser.exit(1, "Another Strata upgrade is in progress\n")
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        tarfile.TarError,
        subprocess.CalledProcessError,
    ) as error:
        parser.exit(1, f"Strata upgrade: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
