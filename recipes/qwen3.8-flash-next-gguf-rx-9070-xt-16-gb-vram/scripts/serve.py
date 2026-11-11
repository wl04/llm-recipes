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


def configure(source: dict[str, Any], context: int, draft: str, vision: str) -> dict[str, Any]:
    """Return an independent native config with requested context, MTP, and CPU vision."""
    if context < 1024 or context % 256 or context > 999999999:
        raise ValueError("context must be at least 1024, a multiple of 256, and at most 9 digits")
    if draft not in ("on", "off") or vision not in ("cpu", "off"):
        raise ValueError("draft must be on/off; vision must be cpu/off")
    config = copy.deepcopy(source)
    args = config["args"]
    args[args.index("--max-context") + 1] = str(context)
    args[args.index("--kv-resident") + 1] = str(min(context, 32768))
    if draft == "off":
        args[args.index("--spec") + 1] = "0"
        index = args.index("--mtp")
        del args[index : index + 2]
    if vision == "off":
        config.pop("vision", None)
    return config


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=int, default=131072)
    parser.add_argument("--draft", choices=("on", "off"), default="on")
    parser.add_argument("--vision", choices=("cpu", "off"), default="cpu")
    options = parser.parse_args()
    recipe = Path(__file__).resolve().parents[1]
    try:
        built = json.loads(Path("/opt/build/versions.lock.json").read_text())
        expected = json.loads((recipe / "container/versions.lock.json").read_text())
        if built != expected:
            raise ValueError("Image lock differs from the recipe; rebuild the image")
        config = configure(
            json.loads((recipe / "config/strata.json").read_text()),
            options.context,
            options.draft,
            options.vision,
        )
        receipt = json.loads(Path("/models/strata/prepared.json").read_text())
        models = json.loads((recipe / "config/models.lock.json").read_text())
        if receipt != {"models": models, "image": expected}:
            raise ValueError("Prepared model lock differs; rerun prepare_models.py")
        validate_files(config)
        device = json.loads(subprocess.check_output(["/opt/strata/bin/check_hip"], text=True))
        environment = dict(os.environ, HIP_VISIBLE_DEVICES=str(device["device"]))
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
