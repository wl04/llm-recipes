"""Translate launch options into native Strata settings and persist API output."""

import argparse
import copy
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from types import FrameType
from typing import Any

from recipe_config import recipe_paths, release_key

RUNTIME = Path(__file__).resolve().parents[1]


def configure(
    source: dict[str, Any],
    context: int,
    draft: str,
    vision: str,
    *,
    modern: bool = False,
    api_monitor: bool = False,
) -> dict[str, Any]:
    """Return an independent native config with requested context, MTP, and CPU vision."""
    if context < 1024 or context % 256 or context > 999999999:
        raise ValueError("context must be at least 1024, a multiple of 256, and at most 9 digits")
    if draft not in ("on", "off") or vision not in ("cpu", "off"):
        raise ValueError("draft must be on/off; vision must be cpu/off")
    config = copy.deepcopy(source)
    if api_monitor:
        config["api_monitor"] = True
    args = config["args"]
    args[args.index("--max-context") + 1] = str(context)
    args[args.index("--kv-resident") + 1] = str(min(context, 32768))
    if modern:
        config["drafting"] = "mtp" if draft == "on" else "off"
        user = config.setdefault("user_args", [])
        resident = args[args.index("--kv-resident") + 1]
        if "--kv-resident" in user:
            user[user.index("--kv-resident") + 1] = resident
        else:
            user.extend(["--kv-resident", resident])
    if draft == "off":
        args[args.index("--spec") + 1] = "0"
        index = args.index("--mtp")
        del args[index : index + 2]
    if vision == "off":
        config.pop("vision", None)
        if "--vision" in args:
            args.remove("--vision")
    return config


def validate_model_files(
    root: Path, lock: dict[str, Any], projector: dict[str, Any] | None = None
) -> None:
    """Check every locked shard, including middle shards, without rehashing at startup."""
    for item in lock["files"]:
        path = root / "models" / item["path"]
        if projector and item["path"] == projector["source"]:
            path = (root.parents[1] / projector["path"]).with_name(path.name)
        if not path.is_file() or path.stat().st_size != item["size_bytes"]:
            raise ValueError(f"Missing or incomplete model file: {path}; rerun prepare_models.py")


def validate_files(config: dict[str, Any]) -> None:
    """Reject missing preparation artifacts before starting the engine."""
    args = config["args"]
    files = [Path(config["tokenizer"]) / "tokenizer.json"]
    for flag in ("--native", "--ple-gguf", "--expert-profile"):
        files.append(Path(args[args.index(flag) + 1]))
    if "vision" in config:
        files.append(Path(config["vision"]["mmproj"]))
    missing = [str(path) for path in files if not path.is_file()]
    for flag in ("--pack", "--mtp"):
        if flag in args:
            folder = Path(args[args.index(flag) + 1])
            if not folder.is_dir() or not any(folder.iterdir()):
                missing.append(str(folder))
    if missing:
        raise ValueError("Missing prepared model artifacts:\n" + "\n".join(missing))


def run_logged(command: list[str], log: Path, environment: dict[str, str]) -> int:
    """Relay combined output to Docker and a persistent log; forward stop signals."""
    with (
        log.open("a", encoding="utf-8") as output,
        subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=environment,
        ) as process,
    ):

        def forward(signum: int, frame: FrameType | None) -> None:
            if process.poll() is None:
                process.send_signal(signum)

        previous = {sig: signal.signal(sig, forward) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            assert process.stdout is not None
            for line in process.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                output.write(line)
                output.flush()
            return process.wait()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=110)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def probe_device() -> str:
    """Read the HIP device index before the server initializes HIP."""
    output = subprocess.check_output(["/opt/strata/bin/check_hip"], text=True)
    try:
        report = json.loads(output)
    except json.JSONDecodeError as error:
        raise ValueError(f"check_hip returned invalid JSON: {error.msg}") from error
    device = report.get("device") if isinstance(report, dict) else None
    if type(device) is not int or device < 0:
        raise ValueError("check_hip must report a non-negative integer device index")
    return str(device)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--context", type=int, default=131072)
    parser.add_argument("--draft", choices=("on", "off"), default="on")
    parser.add_argument("--vision", choices=("cpu", "off"), default="cpu")
    parser.add_argument("--api-monitor", action="store_true")
    options = parser.parse_args()
    recipe = options.recipe.resolve()
    try:
        config_dir, folder = recipe_paths(recipe)
        built = json.loads(Path("/opt/build/versions.lock.json").read_text())
        key = release_key(config_dir)
        pins = RUNTIME / "releases" / key if key else RUNTIME
        expected = json.loads((pins / "container/versions.lock.json").read_text())
        if built != expected:
            raise ValueError("Image lock differs from the runtime; rebuild the image")
        config = configure(
            json.loads((config_dir / "strata.json").read_text()),
            options.context,
            options.draft,
            options.vision,
            api_monitor=options.api_monitor,
            modern=built.get("layout") == "engine-terminal",
        )
        root = Path("/models") / folder
        prepared = root / "prepared" / key if key else root
        if key:
            for flag in ("--pack", "--mtp"):
                if flag in config["args"]:
                    index = config["args"].index(flag) + 1
                    config["args"][index] = str(
                        prepared / Path(config["args"][index]).relative_to(root)
                    )
            config["tokenizer"] = str(prepared / Path(config["tokenizer"]).relative_to(root))
        receipt = json.loads((prepared / "prepared.json").read_text())
        models = json.loads((config_dir / "models.lock.json").read_text())
        projector = models.pop("projector", None)
        if projector and "vision" in config:
            target = Path("/models") / projector["path"]
            if (
                Path(config["vision"]["mmproj"]) != target
                or target.stat().st_size != projector["size_bytes"]
            ):
                raise ValueError("Invalid shared vision projector; rerun prepare_models.py")
        if receipt != {"models": models, "image": expected}:
            raise ValueError("Prepared model lock differs; rerun prepare_models.py")
        validate_model_files(Path("/models") / folder, models, projector)
        validate_files(config)
        environment = dict(os.environ, HIP_VISIBLE_DEVICES=probe_device())
        print(json.dumps(config, indent=2), flush=True)
        with tempfile.TemporaryDirectory(prefix="strata-runtime-") as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(json.dumps(config))
            return run_logged(
                [
                    sys.executable,
                    "-m",
                    "serve.server",
                    "--engine",
                    "strata",
                    "--config",
                    str(path),
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(config["port"]),
                    "--offline",
                    "--no-api-key",
                ],
                Path("/logs/server.log"),
                environment,
            )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Strata startup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
