#!/usr/bin/env python3
"""Build a locked recipe runtime and optionally run its GPU smoke check."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from baseline.host import repository_revision
from launcher import file_sha256, gpu_access_args, gpu_groups, image_reference

ROOT = Path(__file__).resolve().parents[1]


def build_command(context: Path, base: str, image: str, max_jobs: int) -> list[str]:
    """Validate the build arguments and construct the Docker build command."""
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_./:-]*@sha256:[0-9a-f]{64}", base):
        raise ValueError("base_image must be pinned by SHA-256")
    if max_jobs < 1:
        raise ValueError("--max-jobs must be positive")
    return [
        "sudo",
        "docker",
        "build",
        "--progress=plain",
        "--build-arg",
        f"BASE_IMAGE={base}",
        "--build-arg",
        f"MAX_JOBS={max_jobs}",
        "--tag",
        image_reference(image),
        str(context),
    ]


def main(argv: list[str] | None = None) -> int:
    """Build the image selected by a runtime descriptor or a local candidate tag."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "runtime",
        choices=sorted(
            p.name for p in (ROOT / "runtimes").iterdir() if (p / "runtime.json").is_file()
        ),
    )
    parser.add_argument("--tag", help="Override the image tag, for example v0.2.16-rocm10.2")
    parser.add_argument("--max-jobs", type=int, default=4)
    parser.add_argument("--check", action="store_true", help="Run the image's GPU smoke check")
    args = parser.parse_args(argv)
    runtime = ROOT / "runtimes" / args.runtime
    context = runtime / "container"
    lock_path = context / "versions.lock.json"
    try:
        contents = lock_path.read_bytes()
        digest = hashlib.sha256(contents).hexdigest()
        lock = json.loads(contents)
        revision = repository_revision(ROOT)
        descriptor = json.loads((runtime / "runtime.json").read_text())
        image = descriptor["image"]
        if args.tag is not None:
            if not re.fullmatch(r"[\w][\w.-]{0,127}", args.tag, re.ASCII):
                raise ValueError("invalid Docker tag")
            if "@" in image:
                raise ValueError("a digest-pinned runtime image cannot be retagged with --tag")
            image = re.sub(r":[^/:]+$", "", image) + ":" + args.tag
        build = subprocess.run(
            build_command(context, lock["base_image"], image, args.max_jobs), check=False
        )
        if build.returncode:
            return build.returncode
        if file_sha256(lock_path) != digest:
            raise ValueError("runtime lock changed during the build")
        inspection = subprocess.run(
            ["sudo", "docker", "image", "inspect", "--format", "{{.Id}}", image],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        image_id = image_reference(inspection.stdout.strip())
        print(
            json.dumps(
                {
                    "image": image,
                    "image_id": image_id,
                    "checkout": revision,
                    "engine": descriptor["engine"],
                    "engine_version": descriptor.get("engine_version"),
                    "runtime_lock_sha256": digest,
                    "base_image": lock["base_image"],
                    "sources": lock.get("sources"),
                },
                indent=2,
            ),
            flush=True,
        )
        if args.check:
            return subprocess.run(
                ["sudo", "docker", "run", "--rm", *gpu_access_args(gpu_groups()), image_id],
                check=False,
            ).returncode
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"build_runtime: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
