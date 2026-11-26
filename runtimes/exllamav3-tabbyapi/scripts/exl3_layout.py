"""Resolve the recipe's selected ExLlamaV3 build and its generated artifacts."""

import json
import re
import sys
from pathlib import Path


def selection(recipe: Path) -> Path:
    """Return the pin directory relative to the runtime's build context."""
    path = recipe / "config/launch.json"
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{path}: launch settings are not readable: invalid JSON at line {error.lineno}"
        ) from error
    except OSError as error:
        raise ValueError(f"{path}: launch settings are not readable: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    runtime = data.get("runtime")
    if not isinstance(runtime, str):
        raise ValueError(f'{path}: recipe launch settings have no "runtime" field')
    if runtime == "exllamav3-tabbyapi":
        return Path(".")
    if not re.fullmatch(r"exllamav3-tabbyapi/releases/v[0-9][A-Za-z0-9.-]*", runtime):
        raise ValueError(f"{path}: expected an exllamav3-tabbyapi recipe")
    return Path(runtime).relative_to("exllamav3-tabbyapi")


def prepared_root(root: Path, pins: Path) -> Path:
    return root / "prepared" / pins.name if pins.name else root


if __name__ == "__main__":
    # The host preparation wrapper needs the same image as the recipe launcher.
    pins = Path(__file__).resolve().parents[1] / selection(Path(sys.argv[1]))
    print(json.loads((pins / "runtime.json").read_text())["image"])
