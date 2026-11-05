#!/usr/bin/env python3
"""Validate native TabbyAPI settings and launch on the discrete GPU."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from ruamel.yaml import YAML

RECIPE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", choices=("on", "off"), default="on")
    parser.add_argument("--context", type=int, default=4096)
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args()
    if args.context < 1024 or args.context % 256:
        parser.error("context must be at least 1024 and a multiple of 256")
    yaml = YAML(typ="safe")
    config = yaml.load(RECIPE / "tabby.yml")
    config["model"].update(max_seq_len=args.context, cache_size=args.context)
    config["draft_model"]["draft_mode"] = "model" if args.draft == "on" else "disabled"
    sys.path.insert(0, "/opt/src/tabbyAPI")
    from common.config_models import TabbyConfigModel
    # Pydantic otherwise ignores misspelled fields in these upstream models.
    for section, fields in config.items():
        from typing import get_args
        annotation = TabbyConfigModel.model_fields[section].annotation
        model = next(t for t in get_args(annotation) if t is not type(None))
        unknown = set(fields) - set(model.model_fields)
        if unknown:
            raise ValueError(f"Unknown settings in {section}: {unknown}")
    TabbyConfigModel.model_validate(config)
    print(yaml_dump(config), flush=True)
    if args.check_config:
        return
    expected = json.loads((RECIPE / "container/versions.lock.json").read_text())
    if json.loads(Path("/opt/build/versions.lock.json").read_text()) != expected:
        raise RuntimeError("Image pins differ from checkout; rebuild the recipe image")
    for section in ("model", "draft_model") if args.draft == "on" else ("model",):
        prefix = "draft_" if section == "draft_model" else ""
        folder = Path(config[section][prefix + "model_dir"]) / config[section][prefix + "model_name"]
        for filename in ("config.json", "prepared.json"):
            if not (folder / filename).is_file():
                raise RuntimeError(f"Missing prepared model file: {folder / filename}")
    # Probe in a child process so visibility is set before the server initializes HIP.
    probe = 'import torch,json; print(json.dumps([i for i in range(torch.cuda.device_count()) if "RX 9070 XT" in torch.cuda.get_device_name(i)]))'
    devices = json.loads(subprocess.check_output([sys.executable, "-c", probe], text=True))
    if len(devices) != 1:
        raise RuntimeError(f"Expected one RX 9070 XT, found {devices}")
    os.environ["HIP_VISIBLE_DEVICES"] = str(devices[0])
    print(f"Selected RX 9070 XT (original HIP index {devices[0]})", flush=True)
    runtime = prepare_runtime(Path("/opt/src/tabbyAPI"))
    destination = runtime / "config.yml"
    destination.write_text(yaml_dump(config))
    os.chdir(runtime)
    os.execv(sys.executable, [sys.executable, "/opt/src/tabbyAPI/main.py", "--config", str(destination)])


def prepare_runtime(source):
    """Keep relative runtime writes owned by the invoking user."""
    runtime = Path(tempfile.mkdtemp(prefix="tabby-runtime-"))
    for name in ("templates", "sampler_overrides", "loras"):
        (runtime / name).symlink_to(source / name, target_is_directory=True)
    return runtime


def yaml_dump(config):
    from io import StringIO
    stream = StringIO()
    YAML().dump(config, stream)
    return stream.getvalue()


if __name__ == "__main__":
    main()
