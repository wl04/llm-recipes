#!/usr/bin/env python3
"""Prepare and check an isolated Strata release on the RX 9070 XT workstation."""

import argparse
import fcntl
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from command_hints import command_hint
from doctor import check_prepared, strata_weight_path
from launcher import (
    Recipe,
    discover_recipes,
    gpu_access_args,
    gpu_groups,
    local_selections,
    write_json_atomic,
)
from paths import data_home, runtime_prefix

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path("runtimes/strata")
LOCK = RUNTIME / "container/versions.lock.json"
DESCRIPTOR = RUNTIME / "runtime.json"
BASE = "rocm/dev-ubuntu-24.04"
ENGINE = "engine/CMakeLists.txt"
TARGETS = "engine/cmake/strata_gpu_engine.cmake"
VISION = "terminal/tools/vision/CMakeLists.txt"
MTP = "terminal/tools/mtp_fetch.py"


def output(*cmd: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(cmd, cwd=cwd or ROOT, text=True).strip()


def worktree(
    root: Path,
    key: str,
    names: tuple[str, ...] = (),
    runtime: str = "strata",
    *,
    update_reference: bool = True,
) -> Path:
    """Create a sibling trial or resume the matching worktree of this repository."""
    branch = f"{runtime}-{key}"
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
        if update_reference and output("git", "rev-parse", "HEAD", cwd=path) != reference:
            # Git handles conflicts in generated files during the fast-forward.
            changes = output(
                "git",
                "status",
                "--porcelain",
                "--",
                ".",
                f":(exclude){LOCK}",
                f":(exclude){DESCRIPTOR}",
                *(f":(exclude){manifest_path(name)}" for name in names),
                f":(exclude)runtimes/{runtime}/releases/{key}/runtime.json",
                f":(exclude)runtimes/{runtime}/releases/{key}/container/versions.lock.json",
                cwd=path,
            )
            if changes or output("git", "diff", "--cached", "--name-only", cwd=path):
                raise ValueError(f"Review the changes in {path} before updating its reference")
            subprocess.run(
                ["git", "merge", "--ff-only", reference],
                cwd=path,
                check=True,
            )
    else:
        if output("git", "branch", "--list", branch, cwd=root):
            subprocess.run(["git", "worktree", "add", str(path), branch], cwd=root, check=True)
        else:
            subprocess.run(
                ["git", "worktree", "add", "-b", branch, str(path), "HEAD"], cwd=root, check=True
            )
    return path


def inspect_source(files: dict[str, str], requirements: dict[str, dict[str, str]]) -> str:
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
    for recipe, mtp in requirements.items():
        vocabulary = "terminal/data/" + mtp["draft_vocabulary"]
        if vocabulary not in files:
            raise ValueError(f"{recipe}: missing {vocabulary} in upstream release")
        revision = re.escape(mtp["revision"])
        if not re.search(rf"""^PINNED_REVISION\s*=\s*["']{revision}["']""", files[MTP], re.M):
            raise ValueError(f"{recipe}: upstream MTP revision differs from its model lock")
    return version[1]


def resolve_revision(repo: str, tag: str) -> str:
    ref = f"refs/tags/{tag}"
    lines = output("git", "ls-remote", "--exit-code", repo, ref, ref + "^{}")
    refs = dict(line.split()[::-1] for line in lines.splitlines())
    revision = refs.get(ref + "^{}", refs[ref])
    if not re.fullmatch("[0-9a-f]{40}", revision):
        raise ValueError(f"Invalid Git revision for {tag}")
    return revision


def release(
    tag: str, requirements: dict[str, dict[str, str]], options: dict[str, bool]
) -> tuple[str, str, str]:
    repo = "https://github.com/Niko1221/Strata.git"
    revision = resolve_revision(repo, tag)
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
    return revision, digest, inspect_source(files, requirements)


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


def build_fingerprint(candidate: Path, runtime: str) -> str:
    # Include all tracked container build inputs except the generated lock itself.
    fingerprint = hashlib.sha256()
    container = Path("runtimes") / runtime / "container"
    for name in sorted(output("git", "ls-files", str(container), cwd=candidate).splitlines()):
        if Path(name) != container / "versions.lock.json":
            fingerprint.update(
                name.encode() + b"\0" + hashlib.sha256((candidate / name).read_bytes()).digest()
            )
    return fingerprint.hexdigest()


def build_or_check(
    candidate: Path, image: str, lock: dict[str, Any], jobs: int, runtime: str = "strata"
) -> str:
    image_id = output("sudo", "docker", "image", "ls", "--no-trunc", "-q", image)
    if not image_id:
        subprocess.run(
            [
                sys.executable,
                "scripts/build_runtime.py",
                runtime,
                "--version",
                image.rsplit(":", 1)[1],
                "--max-jobs",
                str(jobs),
            ],
            cwd=candidate,
            check=True,
        )
        image_id = output("sudo", "docker", "image", "inspect", "--format", "{{.Id}}", image)
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
    print(f"Checking image {image} ({image_id})", flush=True)
    subprocess.run(
        ["sudo", "docker", "run", "--rm", *gpu_access_args(gpu_groups()), image_id], check=True
    )
    return image_id


def upgrade(tag: str, config: dict[str, Any], prepare_only: bool) -> None:
    key = tag + config["image_suffix"]
    if not re.fullmatch(r"v\d+(?:\.\d+)+(?:-[a-zA-Z0-9.-]+)?", tag) or len(key) > 128:
        raise ValueError("Expected a Strata release tag such as v0.2.18")
    record = trial_record(key)
    prior = json.loads(record.read_text()) if record.exists() else {}
    models = data_home().resolve()
    recipes = discover_recipes(ROOT / "recipes", local=False)
    if prior:
        names = trial_names(prior["files"])
    else:
        names = [
            name
            for name, recipe in recipes.items()
            if recipe.adapter == "strata"
            and (weights := models / recipe.data_subpath / "models").is_dir()
            and any(weights.iterdir())
        ]
    if not names:
        raise ValueError(f"No installed Strata models found under {models / 'recipes'}")
    print("Selected local Strata recipes:", *names, sep="\n  ", flush=True)
    requirements = {}
    for name in names:
        recipe = recipes[name]
        if recipe.adapter != "strata":
            raise ValueError(f"{name} no longer selects Strata")
        model_lock = json.loads((recipe.directory / "config/models.lock.json").read_text())
        for item in model_lock["files"]:
            shard = strata_weight_path(models / recipe.data_subpath, model_lock, item["path"])
            if not shard.is_file() or shard.stat().st_size != item["size_bytes"]:
                raise ValueError(f"Incomplete local preparation for {name}: {shard}")
        requirements[name] = model_lock["mtp"]
    descriptor = json.loads((ROOT / DESCRIPTOR).read_text())
    lock = json.loads((ROOT / LOCK).read_text())
    rev, digest, version = release(tag, requirements, config["engine_options"])
    base = base_image(config["base_tag"])
    image = descriptor["image"].rsplit(":", 1)[0] + ":" + key
    print(
        f"Strata: {descriptor['engine_source_version']} -> {tag} ({rev})\n"
        f"Engine: {descriptor['engine_version']} -> {version}\n"
        f"ROCm: {lock['base_tag']} -> {config['base_tag']} ({base})\nImage: {image}",
        flush=True,
    )
    candidate = worktree(ROOT, key, tuple(names))
    lock.update(
        base_image=base,
        base_tag=config["base_tag"],
        layout="engine-terminal",
        engine_options=config["engine_options"],
        build_inputs_sha256=build_fingerprint(candidate, "strata"),
    )
    lock["sources"]["strata"].update(revision=rev, sha256=digest)
    descriptor.update(engine_version=version, engine_source_version=tag, image=image)
    pins = RUNTIME / "releases" / key
    # Preserve edits unless they exactly match the generated trial inputs.
    for path, expected in ((LOCK, lock), (DESCRIPTOR, descriptor)):
        saved = json.loads((candidate / path).read_text())
        if saved != json.loads((ROOT / path).read_text()):
            if saved != expected:
                raise ValueError(f"Conflicting shared runtime edits at {candidate / path}")
            subprocess.run(["git", "restore", "--", str(path)], cwd=candidate, check=True)
    generated = {
        str(pins / "container/versions.lock.json"): lock,
        str(pins / "runtime.json"): descriptor,
    }
    for name in names:
        path = manifest_path(name)
        manifest = json.loads((ROOT / path).read_text())
        manifest["runtime"] = f"strata/releases/{key}"
        generated[str(path)] = manifest
    state = stage_files(record, prior, generated, candidate, models, names)
    if prepare_only:
        return
    image_id = build_or_check(candidate, image, lock, config["max_jobs"])
    save(record, {**prior, **state, "image_id": image_id})
    for index, name in enumerate(names, 1):
        print(f"\nPreparing recipe {index}/{len(names)}  {name}", flush=True)
        subprocess.run(
            [
                sys.executable,
                "runtimes/strata/scripts/prepare_models.py",
                "--recipe",
                str(manifest_path(name).parents[1]),
                "--models",
                str(models),
            ],
            cwd=candidate,
            check=True,
        )
    print(f"\nStrata {key} preparation complete")
    print(f"Candidate checkout  {candidate}")
    print(f"Models root         {models}")
    print("\nChoose one recipe and one action. The baseline starts its own server.")
    print("Stop any interactive server before running a baseline or switching recipes.")
    print(command_hint("Use the candidate checkout", ["cd", str(candidate)], stream=sys.stdout))
    model_args = candidate_model_args(candidate, models)
    for index, name in enumerate(names, 1):
        print(f"\n[{index}/{len(names)}] {name}")
        print(
            command_hint(
                "Start a foreground server",
                ["python3", "scripts/launch.py", "start", name, *model_args],
                stream=sys.stdout,
            )
        )
        print(
            command_hint(
                "Run the baseline",
                ["python3", "scripts/run_baseline.py", "run", name, *model_args],
                stream=sys.stdout,
            )
        )


def candidate_model_args(candidate: Path, models: Path) -> list[str]:
    """Retain a relative data-home override when changing into the candidate checkout."""
    return [] if (candidate / data_home()).resolve() == models else ["--models", str(models)]


def stage_files(
    record: Path,
    prior: dict[str, Any],
    generated: dict[str, Any],
    candidate: Path,
    models: Path,
    names: list[str],
) -> dict[str, Any]:
    state = {"files": generated, "models": str(models), "candidate": str(candidate)}
    if prior and (
        prior["models"] != str(models)
        or prior["candidate"] != str(candidate)
        or any(generated.get(path) != contents for path, contents in prior["files"].items())
    ):
        raise ValueError(f"Conflicting trial inputs at {record}")
    manifests = {manifest_path(name) for name in names}
    for name, value in generated.items():
        path = Path(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or (candidate / path).resolve() != candidate / path
        ):
            raise ValueError(f"Invalid candidate file: {name}")
        dest = candidate / name
        if (
            dest.exists()
            and json.loads(dest.read_text()) != value
            and (Path(name) not in manifests or dest.read_bytes() != (ROOT / name).read_bytes())
        ):
            raise ValueError(f"Conflicting candidate file: {dest}")
    save(record, {**prior, **state})
    for name, value in generated.items():
        save(candidate / name, value)
    return state


def manifest_path(name: str) -> Path:
    return Path("recipes") / name / "config/launch.json"


def trial_names(files: dict[str, Any]) -> list[str]:
    return sorted(
        path.parts[1]
        for filename in files
        if (path := Path(filename)).match("recipes/*/config/launch.json")
        and len(path.parts) == 4
        and path.parts[1] != ".."
    )


def save(path: Path, value: object) -> None:
    if not path.exists() or json.loads(path.read_text()) != value:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, value)


def trial_record(key: str, runtime: str = "strata") -> Path:
    common = Path(output("git", "rev-parse", "--path-format=absolute", "--git-common-dir"))
    return common / f"{runtime}-trials" / (key + ".json")


def check_ready_recipe(recipe: Recipe, models: Path) -> None:
    finding = check_prepared(recipe, models)
    if finding.status != "PASS":
        raise ValueError(finding.detail)
    saved = output(
        "sudo",
        "docker",
        "run",
        "--pull=never",
        "--rm",
        "--network=none",
        "--entrypoint",
        "cat",
        recipe.image,
        "/opt/build/versions.lock.json",
    )
    if json.loads(saved) != json.loads(
        (recipe.runtime_directory / "container/versions.lock.json").read_text()
    ):
        raise ValueError(f"Image lock mismatch: {recipe.image}")


def selection_identity(recipe: Recipe) -> list[str]:
    return [
        recipe.runtime,
        recipe.image,
        *[
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                recipe.runtime_directory / "container/versions.lock.json",
                recipe.directory / "config/models.lock.json",
            )
        ],
    ]


def manage(key: str, delete: bool, runtime: str = "strata") -> None:
    with ExitStack() as guards:
        manage_trial(key, delete, guards, runtime)


def manage_trial(key: str, delete: bool, guards: ExitStack, runtime: str) -> None:
    record = trial_record(key, runtime)
    candidate = ROOT.with_name(f"{ROOT.name}-{runtime}-{key}")
    if not record.exists():
        if delete and not candidate.exists():
            return
        raise ValueError(f"Run the upgrade command for {key} first")
    state = json.loads(record.read_text())
    models = data_home().resolve()
    if state["candidate"] != str(candidate) or state["models"] != str(models):
        raise ValueError("Use the checkout and model root that prepared this trial")
    pins = Path("runtimes") / runtime / "releases" / key
    files = state["files"]
    names = trial_names(files)
    manifests = {str(manifest_path(name)) for name in names}
    expected = {
        *manifests,
        str(pins / "runtime.json"),
        str(pins / "container/versions.lock.json"),
    }
    if not names or set(files) != expected:
        raise ValueError("Invalid trial record")
    image = files[str(pins / "runtime.json")]["image"]
    branch = f"{runtime}-{key}"
    if candidate.exists():
        common = ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"]
        if (
            output(*common, cwd=candidate) != output(*common)
            or output("git", "branch", "--show-current", cwd=candidate) != branch
        ):
            raise ValueError(f"Unexpected trial checkout at {candidate}")
        extra = output(
            "git",
            "status",
            "--porcelain",
            "--",
            ".",
            *(f":(exclude){f}" for f in files),
            cwd=candidate,
        )
        staged = output("git", "diff", "--cached", "--name-only", cwd=candidate).splitlines()
        if extra or (set(staged) - set(files)) or (delete and staged):
            raise ValueError(f"Preserve pending edits in {candidate} first")
        for name, value in files.items():
            path = candidate / name
            if path.exists() and json.loads(path.read_text()) == value:
                continue
            if delete and (
                not path.exists()
                or (name in manifests and path.read_bytes() == (ROOT / name).read_bytes())
            ):
                continue
            raise ValueError(f"Modified trial file: {path}")
    previous_ids = state.get("previous", {})
    if isinstance(previous_ids, list) and len(names) == 1:
        previous_ids = {names[0]: previous_ids}
    app = runtime_prefix() / "app"
    overlays = runtime_prefix() / "selections"
    if not delete:
        candidates = discover_recipes(candidate / "recipes", local=False)
        for name in names:
            check_ready_recipe(candidates[name], models)
        stamp = app / "VERSION"
        if not stamp.exists() or json.loads(stamp.read_text()).get("version") != "2":
            if app.exists():
                installed = discover_recipes(app / "recipes", local=False)
                reference = discover_recipes(ROOT / "recipes", local=False)
                if any(
                    name not in reference
                    or selection_identity(recipe) != selection_identity(reference[name])
                    for name, recipe in installed.items()
                ):
                    raise ValueError(
                        "Installed runtime pins differ; review before refreshing the launcher"
                    )
            subprocess.run(
                [sys.executable, str(ROOT / "scripts/install.py"), "install"], check=True
            )
    # Serialize selection changes with snapshot installation, after any installer subprocess.
    runtime_prefix().mkdir(parents=True, exist_ok=True)
    install_lock = guards.enter_context((runtime_prefix() / ".install.lock").open("a"))
    fcntl.flock(install_lock, fcntl.LOCK_EX)
    selections = {name: local_selections(name) for name in names}
    for stack in selections.values():
        if str(candidate) in stack and stack[-1] != str(candidate):
            raise ValueError("A newer trial is active; roll it back first")
    active = {name for name, stack in selections.items() if str(candidate) in stack}
    if not delete:
        installed = discover_recipes(app / "recipes")
        for name in names:
            if name in active:
                continue
            if stack := selections[name]:
                predecessor = Path(stack[-1]) / manifest_path(name)
                if installed[name].directory != predecessor.parents[1].resolve():
                    raise ValueError(
                        f"Cannot adopt {name}: restore {predecessor} or roll back the prior trial"
                    )
            identity = selection_identity(installed[name])
            if name in previous_ids and previous_ids[name] != identity:
                raise ValueError(f"The prior selection for {name} changed; review before adoption")
            previous_ids[name] = identity
        state["previous"] = previous_ids
        save(record, state)
        subprocess.run(["git", "add", "--", *files], cwd=candidate, check=True)
        if output("git", "diff", "--cached", "--name-only", cwd=candidate):
            subprocess.run(
                ["git", "commit", "-m", f"Select {runtime} {key} for {len(names)} local recipes"],
                cwd=candidate,
                check=True,
            )
        for name in names:
            if name not in active:
                save(overlays / (name + ".json"), [*selections[name], str(candidate)])
        print(f"Adopted {key} for {', '.join(names)}.")
        print(
            command_hint(
                "Publish the adoption branch",
                ["git", "-C", str(candidate), "push", "-u", "origin", branch],
                stream=sys.stdout,
            )
        )
        return

    # A published or installed default still owns its versioned preparation.
    for checkout in (ROOT, app):
        for path in (checkout / "recipes").glob("*/config/launch.json"):
            if json.loads(path.read_text()).get("runtime") == f"{runtime}/releases/{key}":
                raise ValueError(
                    f"{path} still selects {key}; revert the published selection first"
                )
    image_id = output("sudo", "docker", "image", "ls", "--no-trunc", "-q", image)
    for ancestor in {image_id, state.get("image_id")} - {None, ""}:
        if output("sudo", "docker", "container", "ls", "-aq", "--filter", f"ancestor={ancestor}"):
            raise ValueError(f"A container still uses {image}")
    directories: list[Path] = []
    for name in names:
        root = models / manifest_path(name).parents[1]
        if root.is_dir():
            guard = guards.enter_context((root / ".prepare.lock").open("a"))
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prepared = root / "prepared" / key
        partial = prepared.with_name("." + key + ".partial")
        if any(path.resolve() != path for path in [prepared, partial]):
            raise ValueError("Refusing to remove a redirected preparation directory")
        if (
            partial.exists()
            and json.loads((partial / "preparing.json").read_text()).get("image")
            != files[str(pins / "container/versions.lock.json")]
        ):
            raise ValueError(f"Unexpected partial preparation at {partial}")
        if prepared.exists():
            if runtime == "exllamav3-tabbyapi":
                model_lock = json.loads(
                    (ROOT / manifest_path(name).parent / "models.lock.json").read_text()
                )
                draft = prepared / model_lock["conversion"]["directory"]
                allowed = {draft.name, model_lock["conversion"]["work_directory"]}
                if draft.parent != prepared or any(
                    p.is_symlink() or p.name not in allowed for p in prepared.iterdir()
                ):
                    raise ValueError(f"Unexpected converted draft directory: {prepared}")
                receipt = json.loads((draft / "prepared.json").read_text())
                owner = receipt.get("build")
            else:
                receipt = json.loads((prepared / "prepared.json").read_text())
                owner = receipt.get("image")
            if owner != files[str(pins / "container/versions.lock.json")]:
                raise ValueError(f"Unexpected preparation at {prepared}")
        directories.extend((prepared, partial))
    if image_id:
        embedded = output(
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
        if json.loads(embedded) != files[str(pins / "container/versions.lock.json")]:
            raise ValueError(f"Image tag belongs to another build: {image}")
    for name in sorted(active):
        stack = selections[name]
        previous_root = Path(stack[-2]) if len(stack) > 1 else app
        previous = discover_recipes(previous_root / "recipes", local=False)[name]
        if selection_identity(previous) != previous_ids.get(name):
            raise ValueError(f"The rollback target for {name} differs from the adopted predecessor")
        check_ready_recipe(previous, models)
    for name in sorted(active):
        save(overlays / (name + ".json"), selections[name][:-1])
    if candidate.exists():
        for name in files:
            tracked = output("git", "ls-files", "--", name, cwd=candidate)
            if tracked:
                subprocess.run(["git", "restore", "--", name], cwd=candidate, check=True)
            else:
                (candidate / name).unlink(missing_ok=True)
        subprocess.run(["git", "worktree", "remove", str(candidate)], cwd=ROOT, check=True)
    if image_id:
        subprocess.run(["sudo", "docker", "image", "rm", image], check=True)
    for directory in directories:
        if directory.exists():
            shutil.rmtree(directory)
    if output("git", "branch", "--merged", "HEAD", "--list", branch):
        subprocess.run(["git", "branch", "-d", branch], cwd=ROOT, check=True)
    record.unlink()
    print(f"Removed trial {key}. Any unmerged adoption commit remains on {branch}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="Upstream release tag, for example v0.2.18")
    parser.add_argument("--config", type=Path, default=ROOT / RUNTIME / "upgrade.json")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--adopt", action="store_true", help="Commit the pins and select this trial locally"
    )
    modes.add_argument(
        "--delete",
        action="store_true",
        help="Restore the prior local selection and remove trial artifacts",
    )
    modes.add_argument(
        "--prepare-only", action="store_true", help="Resolve and write inputs; skip Docker"
    )
    args = parser.parse_args()
    try:
        common = Path(output("git", "rev-parse", "--path-format=absolute", "--git-common-dir"))
        with (common / "strata-upgrade.lock").open("a") as guard:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            config = settings(args.config)
            if not re.fullmatch(r"v\d+(?:\.\d+)+(?:-[a-zA-Z0-9.-]+)?", args.tag):
                raise ValueError("Invalid release tag")
            if args.adopt or args.delete:
                manage(args.tag + config["image_suffix"], args.delete)
            else:
                upgrade(args.tag, config, args.prepare_only)
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
