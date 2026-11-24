"""One-time move of the two Qwen Strata recipes' BF16 projector to shared storage."""

import fcntl
import hashlib
import os
from pathlib import Path

NAME = "mmproj-Qwen3.8-Flash-Next-BF16.gguf"
SHA256 = "b1a82259702816a5330d7bd7607cd9676b11780e79ff7348c21103ff3ce49bd0"
RECIPES = (
    "qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram",
    "qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram",
)


def migrate(root: Path) -> None:
    """Move a verified original, then remove verified duplicates and legacy links."""
    target = root / "projectors" / NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.with_suffix(".lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        if target.is_symlink():
            raise ValueError(f"Expected a regular shared file: {target}")
        originals = []
        links = []
        for recipe in RECIPES:
            path = root / "recipes" / recipe / "models" / NAME
            if path.is_symlink():
                if path.resolve() != target:
                    raise ValueError(f"Unexpected symlink destination: {path}")
                links.append(path)
            elif path.exists():
                originals.append(path)
        for path in ([target] if target.exists() else []) + originals:
            if not path.is_file():
                raise ValueError(f"Expected a regular file: {path}")
            with path.open("rb") as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != SHA256:
                    raise ValueError(f"Checksum mismatch: {path}")
        if not target.exists():
            if not originals:
                raise ValueError("No BF16 source found; run normal model preparation")
            originals.pop(0).rename(target)
        for path in originals + links:
            path.unlink()
        print(f"Verified shared BF16 projector: {target}")


if __name__ == "__main__":
    try:
        migrate(Path(os.environ.get("LLM_RECIPES_HOME", "~/llm-recipes")).expanduser().resolve())
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
