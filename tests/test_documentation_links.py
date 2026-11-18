"""Check that relative links in checked-in Markdown documents resolve."""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
EXCLUDED_DIRECTORIES = {".git", ".venv", "__pycache__", "node_modules"}
INLINE_CODE = re.compile(r"`+[^`]*`+")
LINK = re.compile(r"\[[^\]]*\]\(<?([^)>\s]+)")
HEADING = re.compile(r"^#{1,6}\s+(.*)")
LINK_TEXT = re.compile(r"\[([^\]]*)\]\([^)]*\)")
PLACEHOLDER = re.compile(r"[<>]")
EXPERIMENT_FOLDER = re.compile(r"^\d{3}-")
TEMPLATE_PLACEHOLDER_FOLDER = "NNN-YYYY-MM-DD-description"


def documents() -> list[Path]:
    """Every Markdown document that ships with the repository."""
    found = []
    for path in sorted(ROOT.rglob("*.md")):
        if not EXCLUDED_DIRECTORIES & set(path.relative_to(ROOT).parts):
            found.append(path)
    return found


def first(mapping: dict[str, Path], label: str) -> Path:
    for path in sorted(mapping.values()):
        return path
    raise AssertionError(f"no {label} to read templates as")


LAUNCHABLE_RECIPES = {
    path.name: path for path in (ROOT / "recipes").iterdir() if (path / "config").is_dir()
}
RUNTIME_GUIDES = {
    path.name: path
    for path in (ROOT / "docs" / "runtimes").glob("*.md")
    if path.name != "README.md"
}


def experiment_directories(recipe: Path) -> dict[str, Path]:
    return {
        path.name: path
        for path in recipe.iterdir()
        if path.is_dir() and EXPERIMENT_FOLDER.match(path.name)
    }


SAMPLE_RECIPE = first(LAUNCHABLE_RECIPES, "launchable recipe")
SAMPLE_EXPERIMENT = first(experiment_directories(SAMPLE_RECIPE), "experiment folder").name
SAMPLE_RUNTIME_GUIDE = first(RUNTIME_GUIDES, "runtime guide")


def reading_position(document: Path) -> Path:
    """Where a template is read from; every other document is read in place.

    Templates describe a recipe or a runtime guide, so their relative links resolve
    from that future location rather than from ``templates/``.
    """
    if TEMPLATES not in document.parents:
        return document
    if document.name == "runtime-guide.md":
        return SAMPLE_RUNTIME_GUIDE
    relative = [
        SAMPLE_EXPERIMENT if part == TEMPLATE_PLACEHOLDER_FOLDER else part
        for part in document.relative_to(TEMPLATES).parts[1:]
    ]
    position = SAMPLE_RECIPE.joinpath(*relative)
    return position if position.exists() else SAMPLE_RECIPE / SAMPLE_EXPERIMENT / document.name


def prose(text: str) -> list[str]:
    """Document lines outside fenced code blocks, with inline code removed."""
    lines: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            lines.append(INLINE_CODE.sub("", line))
    return lines


def targets(document: Path) -> list[tuple[str, Path]]:
    """Relative link targets of a document with the file each one must resolve to."""
    base = reading_position(document)
    found = []
    for line in prose(document.read_text()):
        for match in LINK.finditer(line):
            target = match.group(1)
            if PLACEHOLDER.search(target):
                continue
            if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
                continue
            path = target.split("#", 1)[0]
            found.append((target, document if not path else (base.parent / path).resolve()))
    return found


def heading_slugs(text: str) -> set[str]:
    """Anchor names a reader can link to inside a document, as GitHub renders them."""
    slugs: set[str] = set()
    seen: dict[str, int] = {}
    for line in text.splitlines():
        match = HEADING.match(line)
        if not match:
            continue
        title = LINK_TEXT.sub(r"\1", match.group(1)).replace("`", "")
        slug = re.sub(r"[^\w\s-]", "", title.strip().lower(), flags=re.UNICODE).replace(" ", "-")
        slugs.add(slug if seen.setdefault(slug, 0) == 0 else f"{slug}-{seen[slug]}")
        seen[slug] += 1
    return slugs


@pytest.mark.parametrize("document", documents(), ids=lambda path: str(path.relative_to(ROOT)))
def test_relative_link_target_exists_in_the_repository(document: Path) -> None:
    missing = [target for target, path in targets(document) if not path.exists()]

    assert not missing, f"{document.relative_to(ROOT)} links to missing files: {missing}"


@pytest.mark.parametrize("document", documents(), ids=lambda path: str(path.relative_to(ROOT)))
def test_link_anchor_matches_a_heading_in_the_linked_document(document: Path) -> None:
    slugs: dict[Path, set[str]] = {}
    broken = []
    for target, path in targets(document):
        _, _, anchor = target.partition("#")
        if not anchor:
            continue
        if path not in slugs:
            slugs[path] = heading_slugs(path.read_text()) if path.exists() else set()
        if anchor not in slugs[path]:
            broken.append(target)

    assert not broken, f"{document.relative_to(ROOT)} links to unknown anchors: {broken}"


@pytest.mark.parametrize("in_template", [False, True], ids=["document", "template"])
def test_targets_resolves_fragment_against_source_when_link_is_same_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, in_template: bool
) -> None:
    if in_template:
        monkeypatch.setattr(sys.modules[__name__], "TEMPLATES", tmp_path)
    document = tmp_path / "guide.md"
    document.write_text("[Broken anchor](#missing)\n")

    resolved = targets(document)

    assert resolved == [("#missing", document)]
