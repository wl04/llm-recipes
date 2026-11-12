"""Regression tests for scripts/generate_configurations.py."""

import os
import sys
from pathlib import Path
from typing import Any

import generate_configurations as gen
import pytest
import yaml

CAPTION = "Test Model / FMT / Test GPU / 8 GB VRAM"
SLUG = "test-model-fmt-test-gpu-8-gb-vram"
START = "<!-- BEGIN GENERATED CONFIGURATIONS -->"
END = "<!-- END GENERATED CONFIGURATIONS -->"
INDEX_START = "<!-- BEGIN GENERATED EXPERIMENTS -->"
INDEX_END = "<!-- END GENERATED EXPERIMENTS -->"

PROFILE = """
id: {caption}
hardware:
  gpu: Test GPU
  cpu: Test CPU
labels:
  hardware: Hardware
  hardware.gpu: GPU
  hardware.cpu: CPU
"""

CONFIGURATION = "Authored overview.\n\n" + START + "\n\n" + END + "\n\nAuthored footer.\n"
RECIPE_PAGE = "# Test Recipe\n\n" + INDEX_START + "\n\n" + INDEX_END + "\n"


def write_recipe_tree(root: Path, recipe_name: str = SLUG) -> Path:
    recipe = root / "recipes" / recipe_name
    result = recipe / "001-2026-01-01-test"
    result.mkdir(parents=True)
    (recipe / "recipe.md").write_text(RECIPE_PAGE)
    (result / "profile.yaml").write_text(PROFILE.format(caption=CAPTION))
    (result / "summary.md").write_text("# 001 · 2026-01-01 — Test Run\n\nObservations.\n")
    (result / "configuration.md").write_text(CONFIGURATION)
    return recipe


def run_main(monkeypatch: pytest.MonkeyPatch, root: Path, *argv: str) -> int:
    monkeypatch.setattr(gen, "ROOT", root)
    monkeypatch.setattr(sys, "argv", ["generate_configurations.py", *argv])
    return gen.main()


def configuration_path(root: Path) -> Path:
    return root / "recipes" / SLUG / "001-2026-01-01-test" / "configuration.md"


def test_main_rewrites_stale_document_and_preserves_authored_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_recipe_tree(tmp_path)

    exit_code = run_main(monkeypatch, tmp_path)

    assert exit_code == 0
    document = configuration_path(tmp_path).read_text()
    assert "Authored overview." in document
    assert "Authored footer." in document
    assert f"# {CAPTION}" in document
    assert "| Test GPU |" in document


def test_main_check_mode_is_idempotent_after_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_recipe_tree(tmp_path)
    run_main(monkeypatch, tmp_path)

    exit_code = run_main(monkeypatch, tmp_path, "--check")

    assert exit_code == 0


def test_main_check_mode_fails_and_writes_nothing_when_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_recipe_tree(tmp_path)
    original = configuration_path(tmp_path).read_text()

    exit_code = run_main(monkeypatch, tmp_path, "--check")

    assert exit_code == 1
    assert configuration_path(tmp_path).read_text() == original
    assert not list((tmp_path / "recipes" / SLUG / "001-2026-01-01-test").glob("*.tmp"))


def test_main_rewrites_document_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_recipe_tree(tmp_path)
    path = configuration_path(tmp_path)
    original = path.read_text()

    def fail_replace(source: str, destination: str, **kwargs: Any) -> None:
        raise OSError("simulated crash")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated crash"):
        run_main(monkeypatch, tmp_path)

    assert path.read_text() == original
    assert not list(tmp_path.glob("recipes/**/*.tmp"))


def test_main_validates_all_profiles_before_writing_any_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_recipe_tree(tmp_path)
    broken_recipe = tmp_path / "recipes" / "other-model-fmt-test-gpu-8-gb-vram"
    broken = broken_recipe / "001-2026-01-02-other"
    broken.mkdir(parents=True)
    (broken_recipe / "recipe.md").write_text(RECIPE_PAGE)
    broken_profile = PROFILE.format(caption="Other Model / FMT / Test GPU / 8 GB VRAM")
    (broken / "profile.yaml").write_text(broken_profile.replace("  hardware.cpu: CPU\n", ""))
    (broken / "summary.md").write_text("# 001 · 2026-01-02 — Other Run\n")
    (broken / "configuration.md").write_text(CONFIGURATION)
    good_original = configuration_path(tmp_path).read_text()

    exit_code = run_main(monkeypatch, tmp_path)

    assert exit_code == 2
    assert configuration_path(tmp_path).read_text() == good_original


def test_main_fails_when_generated_markers_are_malformed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_recipe_tree(tmp_path)
    path = configuration_path(tmp_path)
    path.write_text(path.read_text().replace(END, ""))

    exit_code = run_main(monkeypatch, tmp_path)

    assert exit_code == 2


def test_main_fails_when_recipe_folder_mismatches_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_recipe_tree(tmp_path, recipe_name="wrong-folder-name")

    exit_code = run_main(monkeypatch, tmp_path)

    assert exit_code == 2


def test_main_fails_when_profile_yaml_is_malformed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_recipe_tree(tmp_path)
    (tmp_path / "recipes" / SLUG / "001-2026-01-01-test" / "profile.yaml").write_text(
        "::: not yaml :::"
    )

    exit_code = run_main(monkeypatch, tmp_path)

    assert exit_code == 2


def test_render_omits_empty_values_and_keeps_zero_and_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_recipe_tree(tmp_path)
    profile = tmp_path / "recipes" / SLUG / "001-2026-01-01-test" / "profile.yaml"
    data = yaml.safe_load(profile.read_text())
    data["settings"] = {"Batch size": 0, "Streaming": False, "Notes": None, "Extra": []}
    data["labels"]["settings"] = "Inference settings"
    data["labels"]["settings.Batch size"] = "Batch size"
    data["labels"]["settings.Streaming"] = "Streaming"
    data["labels"]["settings.Notes"] = "Notes"
    data["labels"]["settings.Extra"] = "Extra"
    profile.write_text(yaml.safe_dump(data))

    exit_code = run_main(monkeypatch, tmp_path)

    assert exit_code == 0
    document = configuration_path(tmp_path).read_text()
    assert "| Batch size | 0 |" in document
    assert "| Streaming | False |" in document
    assert "Notes" not in document
    assert "Extra" not in document


def test_update_index_orders_same_day_experiments_by_sequence_and_links_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe = write_recipe_tree(tmp_path)
    second = recipe / "002-2026-01-01-second"
    second.mkdir()
    (second / "profile.yaml").write_text(PROFILE.format(caption=CAPTION))
    (second / "summary.md").write_text("# 002 · 2026-01-01 — Second Run\n")
    (second / "configuration.md").write_text(CONFIGURATION)

    exit_code = run_main(monkeypatch, tmp_path)

    assert exit_code == 0
    index = (recipe / "recipe.md").read_text()
    assert index.index("002 · 2026-01-01 — Second Run") < index.index("001 · 2026-01-01 — Test Run")
    assert "[Configuration](001-2026-01-01-test/configuration.md)" in index
    assert "[Results](002-2026-01-01-second/summary.md)" in index


def test_update_index_fails_when_result_is_missing_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_recipe_tree(tmp_path)
    (tmp_path / "recipes" / SLUG / "001-2026-01-01-test" / "configuration.md").unlink()

    exit_code = run_main(monkeypatch, tmp_path)

    assert exit_code == 2


def test_update_index_fails_when_summary_has_multiple_titles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_recipe_tree(tmp_path)
    summary = tmp_path / "recipes" / SLUG / "001-2026-01-01-test" / "summary.md"
    summary.write_text(summary.read_text() + "# Second title\n")

    exit_code = run_main(monkeypatch, tmp_path)

    assert exit_code == 2


def test_write_atomic_replaces_document_content(tmp_path: Path) -> None:
    path = tmp_path / "document.md"
    path.write_text("old")

    gen.write_atomic(path, "new")

    assert path.read_text() == "new"
    assert not path.with_name(path.name + ".tmp").exists()


def test_write_atomic_cleans_up_temporary_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "document.md"
    path.write_text("old")

    def fail_replace(source: str, destination: str, **kwargs: Any) -> None:
        raise OSError("simulated crash")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated crash"):
        gen.write_atomic(path, "new")

    assert path.read_text() == "old"
    assert not path.with_name(path.name + ".tmp").exists()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "https://github.com/owner/engine/commit/" + "a" * 40,
            "[aaaaaaaa](https://github.com/owner/engine/commit/" + "a" * 40 + ")",
        ),
        (
            "https://huggingface.co/owner/model/commit/" + "b" * 40,
            "[bbbbbbbb](https://huggingface.co/owner/model/commit/" + "b" * 40 + ")",
        ),
        (
            "https://example.com/releases/v1",
            "[https://example.com/releases/v1](https://example.com/releases/v1)",
        ),
        ("1.6.6", "1.6.6"),
    ],
)
def test_rows_renders_reference_links_with_readable_text(value: str, expected: str) -> None:
    assert list(gen.rows({"revision": value}, {"revision": "Revision"})) == [
        f"| Revision | {expected} |"
    ]


def test_rows_links_list_values_and_preserves_plain_values() -> None:
    assert list(
        gen.rows({"versions": ["https://example.com/v1", "unknown"]}, {"versions": "Versions"})
    ) == ["| Versions | [https://example.com/v1](https://example.com/v1)<br>unknown |"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "https://github.com/turboderp-org/exllamav3/releases/tag/v1.6.6",
            "[v1.6.6](https://github.com/turboderp-org/exllamav3/releases/tag/v1.6.6)",
        ),
        (
            "https://hub.docker.com/r/rocm/pytorch/tags?name=latest",
            "[rocm/pytorch:latest](https://hub.docker.com/r/rocm/pytorch/tags?name=latest)",
        ),
        (
            "https://hub.docker.com/r/rocm/dev-ubuntu-24.04/tags?name=10.1.0-full",
            "[rocm/dev-ubuntu-24.04:10.1.0-full](https://hub.docker.com/r/rocm/dev-ubuntu-24.04/tags?name=10.1.0-full)",
        ),
    ],
)
def test_rows_displays_release_and_image_tag_names(value: str, expected: str) -> None:
    assert list(gen.rows({"version": value}, {"version": "Version"})) == [
        f"| Version | {expected} |"
    ]
