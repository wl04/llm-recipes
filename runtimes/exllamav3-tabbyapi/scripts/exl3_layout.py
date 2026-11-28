"""Resolve the recipe's selected ExLlamaV3 build and its generated artifacts."""

import json
import re
import sys
from pathlib import Path
from typing import Any


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


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


def check_inventory(folder: Path, names: set[str]) -> None:
    """Verify the published EXL3 file list and any referenced weight shards."""
    if "config.json" not in names or not any(name.endswith(".safetensors") for name in names):
        raise ValueError(f"Incomplete EXL3 inventory: {folder}")
    for name in names:
        path = folder / name
        if Path(name).name != name or path.resolve() != path.absolute():
            raise ValueError(f"Redirected EXL3 artifact: {path}")
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Missing or empty EXL3 artifact: {path}")
    index = folder / "model.safetensors.index.json"
    if index.is_file():
        files = set(read_object(index)["weight_map"].values())
        if index.name not in names or not files or not files <= names:
            raise ValueError(f"Incomplete EXL3 shard index: {index}")


if __name__ == "__main__":
    # The host preparation wrapper needs the same image as the recipe launcher.
    pins = Path(__file__).resolve().parents[1] / selection(Path(sys.argv[1]))
    print(read_object(pins / "runtime.json")["image"])
