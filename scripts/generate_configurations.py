#!/usr/bin/env python3
"""Render configuration guides and recipe experiment indexes."""

import argparse
import html
import os
import re
import sys
from collections.abc import Generator, Mapping
from pathlib import Path
from urllib.parse import quote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- BEGIN GENERATED CONFIGURATIONS -->"
END = "<!-- END GENERATED CONFIGURATIONS -->"
INDEX_START = "<!-- BEGIN GENERATED EXPERIMENTS -->"
INDEX_END = "<!-- END GENERATED EXPERIMENTS -->"


def cell(value: object) -> str:
    if value is None:
        return "—"
    return html.escape(str(value)).replace("|", "&#124;").replace("\n", "<br>")


def value_cell(value: object) -> str:
    """Render URL values as links, abbreviating commit IDs only in display text."""
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        url = urlsplit(value)
        if url.netloc and not any(char.isspace() for char in value):
            commit = re.search(r"/commit/([0-9a-fA-F]{7,40})$", url.path)
            label = commit.group(1)[:8] if commit else value
            target = quote(value, safe=":/?#@!$&'*+,;=%~.-_")
            text = cell(label).replace("[", "&#91;").replace("]", "&#93;")
            return f"[{text}]({target})"
    return cell(value)


def empty(value: object) -> bool:
    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    if isinstance(value, (dict, list)):
        items = value.values() if isinstance(value, dict) else value
        return all(empty(item) for item in items)
    return False


def rows(
    data: Mapping[str, object], labels: Mapping[str, object], prefix: str = ""
) -> Generator[str, None, None]:
    for key, value in data.items():
        if empty(value):
            continue
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            yield from rows(value, labels, path)
            continue
        label = labels.get(path)
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"Missing display label for {path}")
        if isinstance(value, list):
            yield (
                f"| {cell(label)} | "
                + "<br>".join(value_cell(item) for item in value if not empty(item))
                + " |"
            )
        else:
            yield f"| {cell(label)} | {value_cell(value)} |"


def profile_identity(data: Mapping[str, object]) -> tuple[str, str]:
    caption = data.get("id")
    if not isinstance(caption, str):
        raise ValueError("Profile id must be Model / Format / Hardware / Memory")
    parts = caption.split(" / ")
    if len(parts) != 4 or any(not part.strip() for part in parts):
        raise ValueError(
            "Profile id must have four nonempty parts: Model / Format / Hardware / Memory"
        )
    slug = "-".join(re.sub(r"[^a-z0-9.-]+", "-", part.lower()).strip("-") for part in parts)
    return caption, slug


def render(result: Path) -> str:
    profile = result / "profile.yaml"
    data = yaml.safe_load(profile.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{profile}: expected a YAML mapping")
    caption, slug = profile_identity(data)
    if result.parent.name != slug:
        raise ValueError(f"{profile}: recipe folder must be {slug}")
    lines = [f"# {cell(caption)}", ""]
    labels = data.get("labels")
    if not isinstance(labels, dict):
        raise ValueError(f"{profile}: expected a labels mapping")
    for key, value in data.items():
        if key in {"labels", "id"} or empty(value):
            continue
        if isinstance(value, dict):
            title = labels.get(key)
            if not isinstance(title, str) or not title.strip():
                raise ValueError(f"Missing display label for {key}")
            lines += ["", f"## {cell(title)}", ""]
            section_rows = list(rows(value, labels, key))
        else:
            section_rows = list(rows({key: value}, labels))
        if section_rows:
            lines += ["", "| Setting | Value |", "|---|---|", *section_rows, ""]
    links = ["[Recipe](../recipe.md)", "[Results](summary.md)"]
    if (result.parent / "setup.md").is_file():
        links.append("[Build and run](../setup.md)")
    links.append("[Profile YAML](profile.yaml)")
    lines += ["---", "", " · ".join(links), ""]
    return "\n".join(lines).rstrip() + "\n"


def write_atomic(path: Path, content: str) -> None:
    """Write content through a temporary file, then atomically replace the document.

    A crash before the rename leaves the previous document intact; a leftover
    temporary file from an interrupted run is cleaned up on the next attempt.
    """
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def update(result: Path) -> tuple[Path, str, str]:
    path = result / "configuration.md"
    original = path.read_text()
    if original.count(START) != 1 or original.count(END) != 1:
        raise ValueError(f"{path}: expected exactly one pair of generated-section markers")
    before, rest = original.split(START)
    _, after = rest.split(END)
    return path, original, before + START + "\n\n" + render(result) + "\n" + END + after


def update_index(recipe: Path) -> tuple[Path, str, str]:
    path = recipe / "recipe.md"
    original = path.read_text()
    if original.count(INDEX_START) != 1 or original.count(INDEX_END) != 1:
        raise ValueError(f"{path}: expected exactly one pair of experiment markers")
    lines = ["## Experiments", "", "| Experiment | Configuration | Results |", "|---|---|---|"]
    for profile in sorted(recipe.glob("*/profile.yaml"), reverse=True):
        result = profile.parent
        summary = result / "summary.md"
        titles = [
            line[2:].strip() for line in summary.read_text().splitlines() if line.startswith("# ")
        ]
        if len(titles) != 1:
            raise ValueError(f"{summary}: expected one report title")
        if not (result / "configuration.md").is_file():
            raise ValueError(f"{result}: missing configuration.md")
        lines.append(
            f"| {cell(titles[0])} | "
            f"[Configuration]({result.name}/configuration.md) | "
            f"[Results]({result.name}/summary.md) |"
        )
    before, rest = original.split(INDEX_START)
    _, after = rest.split(INDEX_END)
    return (
        path,
        original,
        before + INDEX_START + "\n\n" + "\n".join(lines) + "\n\n" + INDEX_END + after,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Fail if generated content is stale; write nothing"
    )
    args = parser.parse_args()
    try:
        profiles = sorted((ROOT / "recipes").glob("*/*/profile.yaml"))
        changes = [update(p.parent) for p in profiles]
        changes += [update_index(recipe) for recipe in sorted({p.parent.parent for p in profiles})]
    except (ValueError, OSError, yaml.YAMLError) as exc:
        print(exc, file=sys.stderr)
        return 2
    stale = False
    for path, old, new in changes:
        if old != new:
            stale = True
            if args.check:
                print(f"Stale: {path.relative_to(ROOT)}")
            else:
                write_atomic(path, new)
                print(f"Updated: {path.relative_to(ROOT)}")
    return int(args.check and stale)


if __name__ == "__main__":
    sys.exit(main())
