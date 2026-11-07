#!/usr/bin/env python3
"""Validate native TabbyAPI settings and launch on the discrete GPU."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import gpu
from ruamel.yaml import YAML

RECIPE = Path(__file__).resolve().parents[1]


def apply_overrides(config: dict[str, Any], context: int, vision_on: bool, draft_on: bool) -> None:
    """Apply the CLI context, vision, and draft choices to the loaded TabbyAPI config."""
    config["model"].update(
        max_seq_len=context,
        cache_size=context,
        vision=vision_on,
        vision_offload=False,
    )
    config["draft_model"]["draft_mode"] = "model" if draft_on else "disabled"


def validate_sections(config: dict[str, Any]) -> None:
    """Reject unknown fields in each TabbyAPI section; pydantic would ignore them."""
    sys.path.insert(0, "/opt/src/tabbyAPI")
    from typing import get_args

    from common.config_models import TabbyConfigModel

    for section, fields in config.items():
        annotation = TabbyConfigModel.model_fields[section].annotation
        model = next(t for t in get_args(annotation) if t is not type(None))
        unknown = set(fields) - set(model.model_fields)
        if section == "sampling":
            from common.sampling import BaseSamplerRequest, split_sampling_section

            unknown -= set(BaseSamplerRequest.model_fields)
            split_sampling_section(fields, "the sampling config")
        if unknown:
            raise ValueError(f"Unknown settings in {section}: {unknown}")
    TabbyConfigModel.model_validate(config)


def check_manifest_file(path: Path, required: tuple[str, ...]) -> dict[str, Any]:
    """Load a prepared.json file, reporting missing or malformed fields."""
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{path}: prepared.json is not valid JSON") from exc
    if not isinstance(manifest, dict):
        raise RuntimeError(f"{path}: prepared.json is not a JSON object")
    missing = [key for key in required if key not in manifest]
    if missing:
        raise RuntimeError(f"{path}: prepared.json missing field: {', '.join(missing)}")
    return manifest


def verify_prepared_manifest(manifest: object, expected_spec: dict[str, Any], path: Path) -> None:
    """Compare completion metadata against the locked model spec, without re-hashing weights."""
    if not isinstance(manifest, dict):
        raise RuntimeError(f"{path}: prepared.json is not a JSON object")
    if manifest.get("source") != expected_spec:
        raise RuntimeError(f"{path}: prepared model does not match the locked spec")
    checksums = manifest.get("sha256")
    if not isinstance(checksums, dict) or not checksums:
        raise RuntimeError(f"{path}: prepared.json has no file checksums")
    missing = set(expected_spec["files"]) - set(checksums)
    if missing:
        raise RuntimeError(f"{path}: prepared model is incomplete, missing {sorted(missing)}")


def verify_draft_manifest(
    manifest: dict[str, Any],
    draft_spec: dict[str, Any],
    conversion: dict[str, Any],
    recipe_lock: dict[str, Any],
    path: Path,
) -> None:
    """Verify the converted draft against the locked spec, build pins, and settings."""
    verify_prepared_manifest(manifest, draft_spec, path)
    if manifest.get("build") != recipe_lock:
        raise RuntimeError(f"{path}: draft was converted with different build pins; rerun it")
    arguments = manifest.get("arguments")
    expected = list(conversion["arguments"])
    if not isinstance(arguments, list) or arguments[-len(expected) :] != expected:
        raise RuntimeError(
            f"{path}: draft was converted with different conversion settings; rerun it"
        )


def verify_preparation(config: dict[str, Any], draft_on: bool) -> None:
    """Verify the mounted prepared models match the locked revisions and conversion settings."""
    models_lock = json.loads((RECIPE / "config/models.lock.json").read_text())
    recipe_lock = json.loads((RECIPE / "container/versions.lock.json").read_text())
    image_lock = json.loads(Path("/opt/build/versions.lock.json").read_text())
    if image_lock != recipe_lock:
        raise RuntimeError("Image pins differ from checkout; rebuild the recipe image")
    folders = [("model", models_lock["target"], "")]
    if draft_on:
        folders.append(("draft_model", models_lock["draft"], "draft_"))
    for section, spec, prefix in folders:
        folder = (
            Path(config[section][prefix + "model_dir"]) / config[section][prefix + "model_name"]
        )
        for filename in ("config.json", "prepared.json"):
            if not (folder / filename).is_file():
                raise RuntimeError(f"Missing prepared model file: {folder / filename}")
        manifest = check_manifest_file(folder / "prepared.json", ("source", "sha256"))
        manifest_path = folder / "prepared.json"
        if section == "draft_model":
            verify_draft_manifest(
                manifest, spec, models_lock["conversion"], recipe_lock, manifest_path
            )
        else:
            verify_prepared_manifest(manifest, spec, manifest_path)


def prepare_runtime(source: Path) -> Path:
    """Keep relative runtime writes owned by the invoking user."""
    runtime = Path(tempfile.mkdtemp(prefix="tabby-runtime-"))
    for name in ("templates", "sampler_overrides", "loras"):
        (runtime / name).symlink_to(source / name, target_is_directory=True)
    return runtime


def yaml_dump(config: dict[str, Any]) -> str:
    from io import StringIO

    stream = StringIO()
    YAML().dump(config, stream)
    return stream.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", choices=("on", "off"), default="on")
    parser.add_argument("--vision", choices=("on", "off"), default="off")
    parser.add_argument("--context", type=int, default=4096)
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args()
    if args.context < 1024 or args.context % 256:
        parser.error("context must be at least 1024 and a multiple of 256")
    yaml = YAML(typ="safe")
    config = yaml.load(RECIPE / "config/tabby.yml")
    if not isinstance(config, dict):
        raise RuntimeError(f"{RECIPE / 'config/tabby.yml'}: expected a YAML mapping")
    apply_overrides(config, args.context, args.vision == "on", args.draft == "on")
    validate_sections(config)
    print(yaml_dump(config), flush=True)
    if args.check_config:
        return
    verify_preparation(config, args.draft == "on")
    # Probe in a child process so visibility is set before the server initializes HIP.
    probe = (
        "import torch,json; "
        "print(json.dumps([torch.cuda.get_device_name(i) "
        "for i in range(torch.cuda.device_count())]))"
    )
    names = json.loads(subprocess.check_output([sys.executable, "-c", probe], text=True))
    device = gpu.select_device(names)
    os.environ["HIP_VISIBLE_DEVICES"] = str(device)
    print(f"Selected RX 9070 XT (original HIP index {device})", flush=True)
    runtime = prepare_runtime(Path("/opt/src/tabbyAPI"))
    (runtime / "logs").symlink_to(Path("/logs"), target_is_directory=True)
    destination = runtime / "config.yml"
    destination.write_text(yaml_dump(config))
    os.chdir(runtime)
    os.execv(
        sys.executable, [sys.executable, "/opt/src/tabbyAPI/main.py", "--config", str(destination)]
    )


if __name__ == "__main__":
    main()
