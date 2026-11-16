#!/usr/bin/env python3
"""Print the container arguments that grant AMD GPU access, one argument per line.

Shell entry points consume this so they share `launcher`'s device and group rule.
"""

import sys

from launcher import gpu_access_args, gpu_groups


def main() -> int:
    try:
        arguments = gpu_access_args(gpu_groups())
    except ValueError as error:
        print(f"gpu_access: {error}", file=sys.stderr)
        return 2
    for argument in arguments:
        print(argument)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
