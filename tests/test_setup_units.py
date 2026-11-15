"""Unit convention for hand-written and generated prose.

Measured sizes use binary units; decimal GB is reserved for vendor
capacities (``16 GB VRAM``) and explicitly decimal labels
(``0.932 GB (decimal, ...)``). Dated planning records under
``docs/plans/`` describe the moment they were written and are excluded.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NUMBERED_GB = re.compile(r"\b\d[\d.,]*\s*GB\b")
ALLOWED_TAILS = (" VRAM", " RAM", " (decimal")

SCANNED_DIRECTORIES = ("recipes", "templates", "docs")
EXCLUDED_PREFIXES = (Path("docs") / "plans",)


def violations(text: str) -> list[str]:
    """Return one-line descriptions of decimal GB usages outside the whitelist."""
    found = []
    for match in NUMBERED_GB.finditer(text):
        if text[match.end() : match.end() + 10].startswith(ALLOWED_TAILS):
            continue
        line = text.count("\n", 0, match.start()) + 1
        excerpt = text[match.start() :].splitlines()[0]
        found.append(f"line {line}: {excerpt}")
    return found


def scanned_files() -> list[Path]:
    files = []
    for directory in SCANNED_DIRECTORIES:
        for path in sorted((ROOT / directory).rglob("*.md")):
            relative = path.relative_to(ROOT)
            if any(relative.is_relative_to(excluded) for excluded in EXCLUDED_PREFIXES):
                continue
            files.append(path)
    return files


class UnitsInRepositoryMarkdown(unittest.TestCase):
    def test_detector_flags_measured_gb(self) -> None:
        self.assertEqual(
            violations("for 83.63 GB of target shards\n"),
            ["line 1: 83.63 GB of target shards"],
        )

    def test_detector_allows_vendor_and_decimal_labels(self) -> None:
        self.assertEqual(
            violations("16 GB VRAM, 64 GB RAM, 0.932 GB (decimal, weights), 20 GiB, MiB\n"),
            [],
        )

    def test_repository_markdown_uses_binary_units_for_measurements(self) -> None:
        offenders = []
        for path in scanned_files():
            for violation in violations(path.read_text(encoding="utf-8")):
                offenders.append(f"{path.relative_to(ROOT)}: {violation}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
