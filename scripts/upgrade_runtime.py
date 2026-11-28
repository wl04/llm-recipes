#!/usr/bin/env python3
"""Build and test a runtime upgrade against locally installed model artifacts."""

import argparse
import fcntl
import hashlib
import json
import os
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
from doctor import check_configuration, check_prepared, read_json
from launcher import Recipe, discover_recipes
from paths import data_home, runtime_prefix

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
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            result = json.load(response)
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot read release metadata from {url}: {error}") from error
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
    recipe: Recipe,
    release: str | None,
    rocm: str | None,
    pytorch: str | None,
    requirements: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    runtime = recipe.runtime_source.name
    repo = REPOS[recipe.adapter]
    lock = read_json(recipe.runtime_directory / "container/versions.lock.json")
    descriptor = read_json(recipe.runtime_directory / "runtime.json")
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
        if requirements is None:
            model = read_json(recipe.directory / "config/models.lock.json")
            requirements = {recipe.name: model["mtp"]}
        revision, checksum, engine = trials.release(
            release, requirements, lock.get("engine_options", {})
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


def preparation_commands(recipe: Recipe, models: Path) -> list[list[str]]:
    scripts = recipe.runtime_source / "scripts"
    if recipe.adapter == "strata":
        return [
            [
                sys.executable,
                str(scripts / "prepare_models.py"),
                "--recipe",
                str(recipe.directory),
                "--models",
                str(models),
            ]
        ]
    commands = [
        ["bash", str(scripts / "prepare-models.sh"), str(recipe.directory), "download", str(models)]
    ]
    if recipe.draft == "on":
        commands.append([*commands[0][:3], "quantize-draft", str(models)])
    return commands


def prepare_models(
    recipe: Recipe, models: Path, donor: str, image_id: str, *, allow_copy: bool, verify: bool
) -> None:
    commands = preparation_commands(recipe, models)
    options = ["--donor", donor]
    if allow_copy:
        options.append("--allow-copy")
    if verify:
        options.append("--verify")
    if recipe.adapter == "strata":
        command = [*commands[0], "--local-only", "--runtime-image", image_id, *options]
    else:
        command = [*commands[0][:3], "upgrade-local", str(models), *options]
        if recipe.draft == "off":
            command.append("--no-draft")
    try:
        subprocess.run(
            command, check=True, env={**os.environ, "LLM_RECIPES_RUNTIME_IMAGE": image_id}
        )
        finding = check_prepared(recipe, models)
        if finding.status != "PASS":
            raise ValueError(finding.detail)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise ValueError(
            command_hint(
                f"{recipe.name}: {error}\nFor missing or damaged inputs, explicitly prepare them",
                *commands,
                stream=sys.stderr,
            )
        ) from error


def select_recipes(
    runtime: str, subject: str, catalog: dict[str, Recipe], models: Path
) -> list[Recipe]:
    installed = discover_recipes(runtime_prefix() / "app/recipes")
    if subject in catalog:
        return [installed.get(subject, catalog[subject])]
    selected = []
    for name, default in catalog.items():
        if default.runtime_source.name != runtime:
            continue
        recipe = installed.get(name, default)
        root = models / recipe.data_subpath
        lock = read_json(recipe.directory / "config/models.lock.json")
        markers = (
            ("models", "packs", "mtp")
            if recipe.adapter == "strata"
            else (
                lock["target"]["directory"],
                lock["draft"]["directory"],
                lock["conversion"]["directory"],
            )
        )
        if any((root / path).exists() for path in (*markers, "prepared", "prepared.json")):
            selected.append(recipe)
    if not selected:
        raise ValueError(f"No local {runtime} model installations under {models / 'recipes'}")
    return selected


def grouped_inputs(recipes: list[Recipe], pytorch: str | None) -> list[list[Recipe]]:
    groups: dict[str, list[Recipe]] = {}
    for recipe in recipes:
        lock = read_json(recipe.runtime_directory / "container/versions.lock.json")
        for field in ("base_tag", "base_image", "build_inputs_sha256", "layout"):
            lock.pop(field, None)
        lock["sources"].pop(recipe.engine)
        if pytorch != "current":
            lock.pop("torch_version", None)
        else:
            lock["torch_version"] = lock["torch_version"].partition("+")[0]
        groups.setdefault(json.dumps(lock, sort_keys=True), []).append(recipe)
    return list(groups.values())


def run(subject: str, runtime: str, catalog: dict[str, Recipe], args: argparse.Namespace) -> None:
    models = data_home().resolve()
    pins = Path("runtimes") / runtime / "releases"
    key = args.resume or args.adopt or args.delete
    if key:
        if not re.fullmatch(r"v[0-9][A-Za-z0-9.-]{0,126}", key):
            raise ValueError("Invalid candidate key")
        if any(v is not None for v in (args.release, args.rocm, args.pytorch)):
            raise ValueError("An existing candidate already has locked versions")
        record = trials.trial_record(key, runtime)
        if not record.exists():
            if (
                args.delete
                and not trials.ROOT.with_name(f"{trials.ROOT.name}-{runtime}-{key}").exists()
            ):
                return
            raise ValueError(f"No saved {runtime} trial for {key}")
        state = read_json(record)
        files = state["files"]
        if subject in catalog and subject not in trials.trial_names(files):
            raise ValueError(f"{subject} is not part of trial {key}")
        if args.adopt:
            check_adoption(
                subject, key, state, files[str(pins / key / "runtime.json")]["image"], args
            )
        if args.adopt or args.delete:
            trials.manage(key, bool(args.delete), runtime)
            return
        stage_trial(
            subject,
            runtime,
            key,
            files[str(pins / key / "container/versions.lock.json")],
            files[str(pins / key / "runtime.json")],
            [],
            models,
        )
        if not args.prepare_only:
            run_trial(runtime, key, models, args)
        return

    if runtime == "strata" and args.pytorch is not None:
        raise ValueError("--pytorch applies only to ExLlamaV3")
    recipes = select_recipes(runtime, subject, catalog, models)
    locks = {recipe.name: validated_model_lock(recipe) for recipe in recipes}
    candidates: dict[str, tuple[dict[str, Any], dict[str, Any], list[Recipe]]] = {}
    for group in grouped_inputs(recipes, args.pytorch):
        anchor = group[0]
        requirements = (
            {recipe.name: locks[recipe.name]["mtp"] for recipe in group}
            if runtime == "strata"
            else None
        )
        key, lock, descriptor = resolve(anchor, args.release, args.rocm, args.pytorch, requirements)
        _, _, names = candidates.setdefault(key, (lock, descriptor, []))
        names.extend(group)
    for key, (lock, descriptor, group) in candidates.items():
        stage_trial(subject, runtime, key, lock, descriptor, group, models)
    if not args.prepare_only:
        for key in candidates:
            run_trial(runtime, key, models, args)


def validated_model_lock(recipe: Recipe) -> dict[str, Any]:
    path = recipe.directory / "config/models.lock.json"
    lock = read_json(path)
    try:
        if recipe.adapter == "strata":
            validate_strata_lock(lock)
        else:
            validate_exl3_lock(lock)
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError(f"{recipe.name}: invalid {path}: {error}") from error
    finding = check_configuration(recipe)
    if finding.status == "FAIL":
        raise ValueError(f"{recipe.name}: {finding.detail}")
    return lock


def local_name(name: str, *, flat: bool = False) -> str:
    path = Path(name)
    if (
        not path.parts
        or path.is_absolute()
        or ".." in path.parts
        or (flat and len(path.parts) != 1)
    ):
        raise ValueError(f"Expected a local artifact path, got {name!r}")
    return path.as_posix()


def validate_strata_lock(lock: dict[str, Any]) -> None:
    def checked_spec(file: dict[str, Any]) -> str:
        if type(file["size_bytes"]) is not int or file["size_bytes"] <= 0:
            raise ValueError(f"Invalid byte size for {file['path']}")
        if not re.fullmatch(r"[a-f0-9]{64}", file["sha256"]):
            raise ValueError(f"Invalid SHA-256 for {file['path']}")
        return local_name(file["path"])

    files = [checked_spec(item) for item in lock["files"]]
    if len(set(files)) != len(files) or not any(
        re.search(r"-00001-of-\d{5}\.gguf$", x) for x in files
    ):
        raise ValueError("Expected unique files and a first target shard")
    if not re.fullmatch(r"[a-f0-9]{40}", lock["mtp"]["revision"]):
        raise ValueError("Expected a pinned MTP revision")
    local_name(lock["mtp"]["draft_vocabulary"], flat=True)
    if lock.get("projector"):
        projector = lock["projector"]
        checked_spec(projector)
        if local_name(projector["source"], flat=True) not in files:
            raise ValueError("Projector conversion source is not locked")


def validate_exl3_lock(lock: dict[str, Any]) -> None:
    dirs = []
    for spec in (lock["target"], lock["draft"]):
        dirs.append(local_name(spec["directory"], flat=True))
        if not re.fullmatch(r"[a-f0-9]{40}", spec["revision"]):
            raise ValueError(f"Expected a pinned revision for {spec['directory']}")
        files = [local_name(name, flat=True) for name in spec["files"]]
        if (
            len(files) != len(set(files))
            or "config.json" not in files
            or not any(name.endswith(".safetensors") for name in files)
        ):
            raise ValueError(f"Incomplete or duplicate artifact paths for {spec['directory']}")
    conversion = lock["conversion"]
    dirs.extend(
        local_name(conversion[field], flat=True) for field in ("directory", "work_directory")
    )
    if len(dirs) != len(set(dirs)):
        raise ValueError("Target, draft, conversion and work directories must differ")
    arguments = conversion["arguments"]
    if (
        not isinstance(arguments, list)
        or not arguments
        or not all(isinstance(arg, str) for arg in arguments)
    ):
        raise ValueError("Expected locked draft conversion arguments")


def check_adoption(
    subject: str, key: str, state: dict[str, Any], image: str, args: argparse.Namespace
) -> None:
    resume = ["python3", "scripts/upgrade_runtime.py", subject, "--resume", key]
    if not state.get("image_id"):
        raise ValueError(
            command_hint(
                "Build and smoke-test the candidate before adopting",
                resume,
                stream=sys.stderr,
            )
        )
    current_id = trials.output("sudo", "docker", "image", "inspect", "--format", "{{.Id}}", image)
    if current_id != state["image_id"]:
        raise ValueError(
            command_hint(
                "Verify the changed candidate image before adopting",
                resume,
                stream=sys.stderr,
            )
        )
    if state.get("model_locks") and not args.confirm_model_load:
        raise ValueError(
            "Run every candidate baseline before adopting; then pass --confirm-model-load"
        )
    for name, lock in state.get("model_locks", {}).items():
        path = Path(state["candidate"]) / trials.manifest_path(name).with_name("models.lock.json")
        if read_json(path) != lock:
            raise ValueError(f"{name}: model lock differs from the saved trial")


def stage_trial(
    subject: str,
    runtime: str,
    key: str,
    lock: dict[str, Any],
    descriptor: dict[str, Any],
    recipes: list[Recipe],
    models: Path,
) -> None:
    root = trials.ROOT
    pins = Path("runtimes") / runtime / "releases" / key
    record = trials.trial_record(key, runtime)
    state = read_json(record) if record.exists() else {}
    generated = dict(state.get("files", {}))
    donor_keys: dict[str, str] = dict(state.get("donors", {}))
    model_locks: dict[str, Any] = dict(state.get("model_locks", {}))
    for recipe in recipes:
        manifest = trials.manifest_path(recipe.name)
        if str(manifest) not in generated:
            if state.get("previous"):
                raise ValueError(
                    "The trial has been adopted; publish or roll it back before extending it"
                )
            settings = read_json(recipe.directory / "config/launch.json")
            settings["runtime"] = f"{runtime}/releases/{key}"
            generated[str(manifest)] = settings
        donor_keys.setdefault(
            recipe.name, Path(recipe.runtime).name if "/" in recipe.runtime else "base"
        )
        model_locks.setdefault(recipe.name, read_json(recipe.directory / "config/models.lock.json"))
    generated[str(pins / "runtime.json")] = descriptor
    generated[str(pins / "container/versions.lock.json")] = lock
    names = trials.trial_names(generated)
    allowed = {str(trials.manifest_path(name)) for name in names}
    allowed.update((str(pins / "runtime.json"), str(pins / "container/versions.lock.json")))
    if not names or set(generated) != allowed:
        raise ValueError(f"Unexpected files in trial record {record}")
    candidate = trials.worktree(root, key, tuple(names), runtime, update_reference=False)
    if trials.build_fingerprint(candidate, runtime) != lock["build_inputs_sha256"]:
        raise ValueError("Candidate Docker build inputs differ from the resolved lock")
    trials.stage_files(
        record,
        state,
        generated,
        candidate,
        models,
        names,
        metadata={"donors": donor_keys, "model_locks": model_locks},
    )
    selected = discover_recipes(candidate / "recipes", local=False)
    for name in names:
        if (model_lock := validated_model_lock(selected[name])) != model_locks.get(
            name, model_lock
        ):
            raise ValueError(f"{name}: model lock differs from the saved trial")
    print(
        f"Candidate: {key}\nCheckout: {candidate}\nBase: {lock['base_tag']} ({lock['base_image']})"
    )
    print(f"Image: {descriptor['image']}\nRecipes: {', '.join(names)}")
    for source, pin in lock["sources"].items():
        print(f"{source}: {pin['revision']}")
    print(
        command_hint(
            "Resume this trial with its exact pins",
            ["python3", "scripts/upgrade_runtime.py", subject, "--resume", key],
            stream=sys.stdout,
        ),
        flush=True,
    )


def run_trial(runtime: str, key: str, models: Path, args: argparse.Namespace) -> None:
    record = trials.trial_record(key, runtime)
    state = read_json(record)
    files = state["files"]
    pins = Path("runtimes") / runtime / "releases" / key
    lock = files[str(pins / "container/versions.lock.json")]
    descriptor = files[str(pins / "runtime.json")]
    candidate = Path(state["candidate"])
    names = trials.trial_names(files)
    selected = discover_recipes(candidate / "recipes", local=False)
    donor_keys = state.get("donors", {})
    model_locks = state.get("model_locks", {})
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
    state = {**read_json(record), "image_id": image_id, "container_python": container_python}
    trials.save(record, state)
    if args.image_only:
        return
    failures = []
    for name in names:
        recipe = selected[name]
        try:
            if (
                name not in model_locks
                and not args.verify
                and check_prepared(recipe, models).status == "PASS"
            ):
                print(f"{name}: reusing the existing trial preparation")
            else:
                prepare_models(
                    recipe,
                    models,
                    donor_keys.get(name, "base"),
                    image_id,
                    allow_copy=args.allow_copy,
                    verify=args.verify,
                )
        except ValueError as error:
            failures.append(str(error))
            continue
        print(
            command_hint(
                f"Run the candidate baseline for {name}",
                ["cd", str(candidate)],
                [
                    "python3",
                    "scripts/run_baseline.py",
                    "run",
                    name,
                    *trials.candidate_model_args(candidate, models),
                ],
                stream=sys.stdout,
            )
        )
    if failures:
        raise ValueError("\n\n".join(failures))
    print("Preparation is complete; verify model loading with the candidate baselines.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "subject", help="Runtime ID (strata or exllamav3-tabbyapi) or one recipe ID"
    )
    parser.add_argument("--release", help="Upstream engine tag (default: latest stable release)")
    parser.add_argument("--rocm", help="Exact ROCm X.Y.Z (default: newest compatible stable image)")
    parser.add_argument(
        "--pytorch", help="ExLlamaV3 only: exact X.Y.Z or current (default: newest compatible)"
    )
    parser.add_argument("--max-jobs", type=int, default=4)
    parser.add_argument(
        "--allow-copy",
        action="store_true",
        help="Allow copying payloads if links and reflinks are unavailable",
    )
    parser.add_argument("--verify", action="store_true", help="Rehash reusable artifacts")
    parser.add_argument(
        "--confirm-model-load",
        action="store_true",
        help="Confirm all candidate baseline runs passed before adoption",
    )
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
        catalog = discover_recipes(trials.ROOT / "recipes", local=False)
        if args.subject in catalog:
            runtime = catalog[args.subject].runtime_source.name
        elif args.subject in ("strata", "exllamav3-tabbyapi"):
            runtime = args.subject
        else:
            raise ValueError(f"Unknown runtime or container recipe: {args.subject}")
        common = Path(
            trials.output("git", "rev-parse", "--path-format=absolute", "--git-common-dir")
        )
        with (common / f"{runtime}-upgrade.lock").open("a") as guard:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(args.subject, runtime, catalog, args)
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
