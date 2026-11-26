#!/usr/bin/env python3
"""Resolve and test a container recipe's upstream engine and AMD base image."""

import argparse
import fcntl
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import upgrade_strata as trials
from command_hints import command_hint
from doctor import check_prepared
from launcher import Recipe, discover_recipes
from paths import data_home

VERSION = r"[0-9]+\.[0-9]+\.[0-9]+"
HUB = "https://hub.docker.com/v2/repositories/"
TORCH_REPO = "rocm/pytorch"
REPOS = {"tabbyapi": "turboderp-org/exllamav3", "strata": "Niko1221/Strata"}


@dataclass(frozen=True)
class BaseImage:
    repository: str
    tag: str
    digest: str
    rocm: str
    torch: str | None
    python: str | None


def json_url(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise ValueError(f"Expected a JSON object from {url}")
    return result


def registry_tags(repository: str, search: str) -> Iterator[dict[str, Any]]:
    endpoint = f"{HUB}{repository}/tags"
    url = endpoint + "?" + urllib.parse.urlencode({"page_size": 100, "name": search})
    while url:
        page = json_url(url)
        yield from page["results"]
        url = page.get("next") or ""
        if url and url.partition("?")[0].rstrip("/") != endpoint:
            raise ValueError(f"Unexpected registry pagination URL: {url}")


def select_image(
    tags: Iterable[dict[str, Any]], python: str | None, rocm: str | None, pytorch: str | None
) -> BaseImage:
    if python is None and pytorch is not None:
        raise ValueError("--pytorch applies only to ExLlamaV3")
    if python:
        pattern = rf"rocm({VERSION})_ubuntu24\.04_py{re.escape(python)}_pytorch_release_({VERSION})"
    else:
        pattern = rf"({VERSION})-full"
    choices = []
    for tag in tags:
        name = tag["name"]
        match = re.fullmatch(pattern, name)
        if not match:
            continue
        digests = {
            i.get("digest")
            for i in tag["images"]
            if i.get("architecture") == "amd64" and i.get("os") == "linux"
        }
        if not digests:
            continue
        if len(digests) != 1 or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", (digest := digests.pop()) or ""
        ):
            raise ValueError(f"Ambiguous or invalid Linux/amd64 manifest for {name}")
        choices.append(
            BaseImage(
                TORCH_REPO if python else trials.BASE,
                name,
                digest,
                match[1],
                match[2] if python else None,
                python,
            )
        )
    matches = [
        c for c in choices if (not rocm or c.rocm == rocm) and (not pytorch or c.torch == pytorch)
    ]
    if not matches:
        available = ", ".join(sorted(c.tag for c in choices)) or "none"
        raise ValueError(f"No matching stable Linux/amd64 AMD image. Available tags: {available}")
    return max(
        matches,
        key=lambda c: (
            tuple(map(int, c.rocm.split("."))),
            tuple(map(int, (c.torch or "0").split("."))),
        ),
    )


def resolve(
    recipe: Recipe, release: str | None, rocm: str | None, pytorch: str | None
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    runtime = recipe.runtime_source.name
    repo = REPOS[recipe.adapter]
    lock = json.loads((recipe.runtime_directory / "container/versions.lock.json").read_text())
    descriptor = json.loads((recipe.runtime_directory / "runtime.json").read_text())
    python = lock["python_version"] if recipe.adapter == "tabbyapi" else None
    if pytorch is not None and not python:
        raise ValueError("--pytorch applies only to ExLlamaV3")
    if pytorch == "current":
        pytorch = lock["torch_version"].split("+")[0]
    for value in (rocm, pytorch):
        if value and not re.fullmatch(VERSION, value):
            raise ValueError(f"Expected a stable X.Y.Z version, got {value!r}")
    if release is None:
        release = str(json_url(f"https://api.github.com/repos/{repo}/releases/latest")["tag_name"])
    if not re.fullmatch("v" + VERSION, release):
        raise ValueError(f"Expected a stable release tag such as v1.6.7, got {release!r}")
    # Ask for the supported image family, including alternatives for an unavailable override.
    search = f"ubuntu24.04_py{python}_pytorch_release_" if python else "-full"
    base = select_image(
        registry_tags(TORCH_REPO if python else trials.BASE, search), python, rocm, pytorch
    )
    lock.update(
        base_tag=base.tag,
        base_image=f"{base.repository}@{base.digest}",
        build_inputs_sha256=trials.build_fingerprint(trials.ROOT, runtime),
    )
    if recipe.adapter == "strata":
        model = json.loads((recipe.directory / "config/models.lock.json").read_text())
        revision, checksum, engine = trials.release(
            release, {recipe.name: model["mtp"]}, lock.get("engine_options", {})
        )
        lock.update(layout="engine-terminal")
        lock["sources"]["strata"].update(revision=revision, sha256=checksum)
    else:
        revision = trials.resolve_revision(f"https://github.com/{repo}.git", release)
        url = f"https://codeload.github.com/{repo}/tar.gz/{revision}"
        with urllib.request.urlopen(url, timeout=120) as archive:
            checksum = hashlib.file_digest(archive, "sha256").hexdigest()
        engine = release.removeprefix("v")
        lock["sources"]["exllamav3"].update(revision=revision, archive_sha256=checksum)
        lock["torch_version"] = f"{base.torch}+rocm{base.rocm}"
    identity = hashlib.sha256(json.dumps(lock, sort_keys=True).encode()).hexdigest()[:12]
    key = f"{release}-rocm{base.rocm}"
    if base.torch:
        key += f"-torch{base.torch}"
    key += f"-{identity}"
    descriptor.update(
        engine_source_version=release,
        engine_version=engine,
        image=recipe.image.rsplit(":", 1)[0] + ":" + key,
    )
    return key, lock, descriptor


def prepare_models(recipe: Recipe, models: Path) -> None:
    if recipe.adapter == "strata":
        subprocess.run(
            [
                sys.executable,
                str(recipe.runtime_source / "scripts/prepare_models.py"),
                "--recipe",
                str(recipe.directory),
                "--models",
                str(models),
            ],
            check=True,
        )
    elif check_prepared(recipe, models).status != "PASS":
        wrapper = str(recipe.runtime_source / "scripts/prepare-models.sh")
        subprocess.run(
            ["bash", wrapper, str(recipe.directory), "download", str(models)], check=True
        )
        if recipe.draft == "on" and check_prepared(recipe, models).status != "PASS":
            subprocess.run(
                ["bash", wrapper, str(recipe.directory), "quantize-draft", str(models)], check=True
            )
    finding = check_prepared(recipe, models)
    if finding.status != "PASS":
        raise ValueError(finding.detail)


def run(recipe: Recipe, args: argparse.Namespace) -> None:
    root = trials.ROOT
    models = data_home().resolve()
    runtime = recipe.runtime_source.name
    key = args.resume or args.adopt or args.delete
    pins = Path("runtimes") / runtime / "releases"
    if key:
        if not re.fullmatch(r"v[0-9][A-Za-z0-9.-]{0,126}", key):
            raise ValueError("Invalid candidate key")
        if any(v is not None for v in (args.release, args.rocm, args.pytorch)):
            raise ValueError("An existing candidate already has locked versions")
        record = trials.trial_record(key, runtime)
        if not record.exists():
            if args.delete and not root.with_name(f"{root.name}-{runtime}-{key}").exists():
                return
            raise ValueError(f"No saved {runtime} trial for {key}")
        state = json.loads(record.read_text())
        files = state["files"]
        if recipe.name not in trials.trial_names(files):
            raise ValueError(f"{recipe.name} is not part of trial {key}")
        resume = ["python3", "scripts/upgrade_runtime.py", recipe.name, "--resume", key]
        if args.adopt and not state.get("image_id"):
            raise ValueError(
                command_hint(
                    "Build and smoke-test the candidate before adopting", resume, stream=sys.stderr
                )
            )
        if args.adopt:
            image = files[str(pins / key / "runtime.json")]["image"]
            current_id = trials.output(
                "sudo", "docker", "image", "inspect", "--format", "{{.Id}}", image
            )
            if current_id != state["image_id"]:
                raise ValueError(
                    command_hint(
                        "Verify the changed candidate image before adopting",
                        resume,
                        stream=sys.stderr,
                    )
                )
        if args.adopt or args.delete:
            trials.manage(key, bool(args.delete), runtime)
            return
        lock = files[str(pins / key / "container/versions.lock.json")]
        descriptor = files[str(pins / key / "runtime.json")]
    else:
        key, lock, descriptor = resolve(recipe, args.release, args.rocm, args.pytorch)
        record = trials.trial_record(key, runtime)
        state = json.loads(record.read_text()) if record.exists() else {}
    generated = dict(state.get("files", {}))
    manifest = trials.manifest_path(recipe.name)
    if str(manifest) not in generated:
        if state.get("previous"):
            raise ValueError(
                "The trial has been adopted; publish or roll it back before extending it"
            )
        settings = json.loads((root / manifest).read_text())
        settings["runtime"] = f"{runtime}/releases/{key}"
        generated[str(manifest)] = settings
    generated[str(pins / key / "runtime.json")] = descriptor
    generated[str(pins / key / "container/versions.lock.json")] = lock
    names = trials.trial_names(generated)
    allowed = {str(trials.manifest_path(name)) for name in names}
    allowed.update(
        (str(pins / key / "runtime.json"), str(pins / key / "container/versions.lock.json"))
    )
    if set(generated) != allowed:
        raise ValueError(f"Unexpected files in trial record {record}")
    candidate = trials.worktree(root, key, tuple(names), runtime, update_reference=False)
    if trials.build_fingerprint(candidate, runtime) != lock["build_inputs_sha256"]:
        raise ValueError("Candidate Docker build inputs differ from the resolved lock")
    trials.stage_files(record, state, generated, candidate, models, names)
    print(
        f"Candidate: {key}\nCheckout: {candidate}\nBase: {lock['base_tag']} ({lock['base_image']})"
    )
    print(f"Image: {descriptor['image']}")
    for source, pin in lock["sources"].items():
        print(f"{source}: {pin['revision']}")
    if runtime == "strata":
        print("Python: supplied by Ubuntu 24.04 (recorded after the image check)")
    else:
        print(f"Python: {lock['python_version']}   PyTorch: {lock['torch_version']}")
    print(
        command_hint(
            "Resume this trial with its exact pins",
            ["python3", "scripts/upgrade_runtime.py", recipe.name, "--resume", key],
            stream=sys.stdout,
        ),
        flush=True,
    )
    if args.prepare_only:
        return
    image_id = trials.build_or_check(candidate, descriptor["image"], lock, args.max_jobs, runtime)
    container_python = trials.output(
        "sudo",
        "docker",
        "run",
        "--rm",
        "--network=none",
        "--entrypoint",
        "python3",
        image_id,
        "--version",
    )
    print(f"Verified image: {image_id} ({container_python})", flush=True)
    trials.save(
        record,
        {
            **json.loads(record.read_text()),
            "image_id": image_id,
            "container_python": container_python,
        },
    )
    if args.image_only:
        return
    selected = discover_recipes(candidate / "recipes", local=False)[recipe.name]
    prepare_models(selected, models)
    print(
        command_hint(
            "Run the candidate baseline",
            ["cd", str(candidate)],
            [
                "python3",
                "scripts/run_baseline.py",
                "run",
                recipe.name,
                *trials.candidate_model_args(candidate, models),
            ],
            stream=sys.stdout,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recipe", help="Recipe ID from llm-recipes list")
    parser.add_argument("--release", help="Upstream engine tag (default: latest stable release)")
    parser.add_argument("--rocm", help="Exact ROCm X.Y.Z (default: newest compatible stable image)")
    parser.add_argument(
        "--pytorch", help="ExLlamaV3 only: exact X.Y.Z or current (default: newest compatible)"
    )
    parser.add_argument("--max-jobs", type=int, default=4)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--resume", metavar="KEY", help="Reuse a trial's saved pins without resolving versions"
    )
    modes.add_argument("--adopt", metavar="KEY", help="Adopt the prepared recipes in a trial")
    modes.add_argument("--delete", metavar="KEY", help="Discard a trial or roll it back")
    stages = parser.add_mutually_exclusive_group()
    stages.add_argument(
        "--prepare-only",
        action="store_true",
        help="Write pins and checkout; skip Docker and models",
    )
    stages.add_argument(
        "--image-only",
        action="store_true",
        help="Build and GPU-check the image; skip model preparation",
    )
    args = parser.parse_args(argv)
    if args.max_jobs < 1 or (
        (args.adopt or args.delete) and (args.image_only or args.prepare_only)
    ):
        parser.error("Invalid build options for the requested operation")
    try:
        recipe = discover_recipes(trials.ROOT / "recipes", local=False).get(args.recipe)
        if recipe is None:
            raise ValueError(f"Unknown container recipe: {args.recipe}")
        common = Path(
            trials.output("git", "rev-parse", "--path-format=absolute", "--git-common-dir")
        )
        with (common / f"{recipe.runtime_source.name}-upgrade.lock").open("a") as guard:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(recipe, args)
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        subprocess.CalledProcessError,
        tarfile.TarError,
    ) as error:
        parser.exit(1, f"Runtime upgrade: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
