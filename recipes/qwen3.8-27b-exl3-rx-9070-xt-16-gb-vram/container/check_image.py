"""Check the compiled engine and the target GPU without model weights."""

import argparse
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

import torch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()
    lock = json.loads(Path("/opt/build/versions.lock.json").read_text())
    if torch.__version__ != lock["torch_version"]:
        raise RuntimeError(
            f"Image locks Torch {lock['torch_version']}, found {torch.__version__}; "
            "rebuild the image"
        )
    python = ".".join(map(str, sys.version_info[:2]))
    if python != lock["python_version"]:
        raise RuntimeError(
            f"Image locks Python {lock['python_version']}, found {python}; rebuild the image"
        )
    spec = importlib.util.find_spec("exllamav3_ext")
    if spec is None or not (spec.origin or "").endswith(
        tuple(importlib.machinery.EXTENSION_SUFFIXES)
    ):
        raise RuntimeError("Missing compiled extension")
    print("Compiled extension:", spec.origin)
    if args.build_only:
        print("Build artifact check: PASS; GPU execution pending")
        sys.exit(0)
    matches = [
        i for i in range(torch.cuda.device_count()) if "9070 XT" in torch.cuda.get_device_name(i)
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one visible RX 9070 XT, found {matches}")
    torch.cuda.set_device(matches[0])
    # These imports are the importability smoke test; keep them despite being unused.
    import exllamav3_ext  # noqa: F401
    import exllamav3  # noqa: F401
    from exllamav3.architecture.dflash2 import DFlash2Model  # noqa: F401

    sys.path.insert(0, "/opt/src/tabbyAPI")
    from common.config_models import TabbyConfigModel  # noqa: F401

    x = torch.ones((1024, 1024), device=f"cuda:{matches[0]}")
    y = x @ x
    torch.cuda.synchronize()
    if not torch.all(y == 1024).item():
        raise RuntimeError("GPU matrix multiplication produced wrong results")
    print("Python:", sys.version.split()[0])
    print("PyTorch:", torch.__version__, "HIP:", torch.version.hip)
    print("GPU:", torch.cuda.get_device_name(matches[0]))
    print("ExLlamaV3 extension, DFlash2 architecture, TabbyAPI schema imports: PASS")
    print("GPU matrix multiplication: PASS")
    print("Model loading, generation, and DFlash2 drafting remain to be tested.")


if __name__ == "__main__":
    main()
