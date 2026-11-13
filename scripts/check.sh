#!/usr/bin/env bash
# CPU-only checks: ruff (lint + format), mypy, pytest, and ShellCheck.
# Same command locally and in CI: bash scripts/check.sh
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

# Prefer the repository virtualenv; fall back to tools on PATH (CI).
tool() {
    local name=$1
    shift
    if [[ -x ".venv/bin/$name" ]]; then
        ".venv/bin/$name" "$@"
    else
        "$name" "$@"
    fi
}

tool ruff check .
tool ruff format --check .
tool mypy
tool pytest
tool python scripts/generate_configurations.py --check

if command -v shellcheck >/dev/null; then
    shellcheck runtimes/exllamav3-tabbyapi/scripts/prepare-models.sh
else
    echo "shellcheck not installed; skipping shell checks" >&2
fi
