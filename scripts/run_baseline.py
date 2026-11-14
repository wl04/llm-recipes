#!/usr/bin/env python3
"""Run the unified baseline against a running server; see docs/baseline.md."""

import sys

from baseline.cli import main

if __name__ == "__main__":
    sys.exit(main())
