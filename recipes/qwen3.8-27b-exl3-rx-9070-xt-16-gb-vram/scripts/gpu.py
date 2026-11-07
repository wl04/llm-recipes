#!/usr/bin/env python3
"""Select the recipe GPU for scripts that run from /recipe/scripts."""

from collections.abc import Sequence

GPU_NAME = "RX 9070 XT"


def select_device(names: Sequence[str]) -> int:
    """Return the index of the single visible GPU whose name contains GPU_NAME.

    Raises:
        RuntimeError: when zero or more than one visible GPU matches.
    """
    matches = [index for index, name in enumerate(names) if GPU_NAME in name]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {GPU_NAME}, found {matches}")
    return matches[0]
