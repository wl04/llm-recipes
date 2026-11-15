"""Regression tests for scripts/generate_configurations.py."""

import json
import os
import sys
from pathlib import Path
from typing import Any

import generate_configurations as gen
import pytest
import yaml
from baseline import schema
from baseline_data import sample_results

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
    (result / "summary.md").write_text("# 001 · 2026-01-01 — Test\n\nObservations.\n")
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
    (broken / "profile.yaml").write_text(
        broken_profile + "\nsettings:\n  Request policy: temperature 1\n"
    )
    (broken / "summary.md").write_text("# 001 · 2026-01-02 — Other\n")
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
    data["settings"] = {
        "serving": {"max_batch_size": 0, "gpu_offload": None},
        "thinking": {"enabled": False, "control": ""},
        "notes": "   ",
    }
    profile.write_text(yaml.safe_dump(data))

    exit_code = run_main(monkeypatch, tmp_path)

    assert exit_code == 0
    document = configuration_path(tmp_path).read_text()
    assert "| Maximum batch size | 0 |" in document
    assert "| Thinking enabled | False |" in document
    assert "Notes" not in document
    assert "GPU offload" not in document
    assert "Thinking control" not in document


def test_update_index_orders_same_day_experiments_by_sequence_and_links_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe = write_recipe_tree(tmp_path)
    second = recipe / "002-2026-01-01-second"
    second.mkdir()
    (second / "profile.yaml").write_text(PROFILE.format(caption=CAPTION))
    (second / "summary.md").write_text("# 002 · 2026-01-01 — Second\n")
    (second / "configuration.md").write_text(CONFIGURATION)

    exit_code = run_main(monkeypatch, tmp_path)

    assert exit_code == 0
    index = (recipe / "recipe.md").read_text()
    assert index.index("002 · 2026-01-01 — Second") < index.index("001 · 2026-01-01 — Test")
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


RESULTS_START = "<!-- BEGIN GENERATED RESULTS -->"
RESULTS_END = "<!-- END GENERATED RESULTS -->"
BASELINE_SUMMARY = (
    "# 002 · 2026-01-02 — Baseline\n\nAuthored intro.\n\n"
    + RESULTS_START
    + "\n\n"
    + RESULTS_END
    + "\n\n## Observations\n\nAuthored observations.\n"
)


def write_baseline_experiment(root: Path, summary: str = BASELINE_SUMMARY) -> Path:
    write_recipe_tree(root)
    result = root / "recipes" / SLUG / "002-2026-01-02-baseline"
    result.mkdir()
    (result / "profile.yaml").write_text(PROFILE.format(caption=CAPTION))
    (result / "configuration.md").write_text(CONFIGURATION)
    (result / "summary.md").write_text(summary)
    (result / "results.json").write_text(schema.dump_results(sample_results()))
    return result


def test_main_renders_results_into_summary_and_preserves_authored_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = write_baseline_experiment(tmp_path)

    exit_code = run_main(monkeypatch, tmp_path)

    summary = (result / "summary.md").read_text()
    assert exit_code == 0
    assert "## Baseline results" in summary
    assert "| context-8k |" in summary
    assert "Authored intro." in summary
    assert "Authored observations." in summary


def test_main_check_mode_is_idempotent_after_results_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_baseline_experiment(tmp_path)
    run_main(monkeypatch, tmp_path)

    assert run_main(monkeypatch, tmp_path, "--check") == 0


def test_main_check_mode_reports_stale_results_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = write_baseline_experiment(tmp_path)
    run_main(monkeypatch, tmp_path)
    document = sample_results()
    document["cases"][0]["metrics"]["input_tokens"]["value"] = 9000
    (result / "results.json").write_text(schema.dump_results(document))
    before = (result / "summary.md").read_text()

    exit_code = run_main(monkeypatch, tmp_path, "--check")

    assert exit_code == 1
    assert (result / "summary.md").read_text() == before


def test_main_fails_when_results_exist_but_summary_has_no_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_baseline_experiment(tmp_path, summary="# 002 · 2026-01-02 — Baseline\n")

    assert run_main(monkeypatch, tmp_path) == 2


def test_main_fails_when_results_json_violates_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = write_baseline_experiment(tmp_path)
    (result / "results.json").write_text('{"schema_version": 1}')

    assert run_main(monkeypatch, tmp_path) == 2


def test_main_fails_when_results_json_is_not_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = write_baseline_experiment(tmp_path)
    (result / "results.json").write_text("not json")

    assert run_main(monkeypatch, tmp_path) == 2


def test_main_validates_results_before_writing_any_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = write_baseline_experiment(tmp_path)
    (result / "results.json").write_text("{}")
    original = configuration_path(tmp_path).read_text()

    run_main(monkeypatch, tmp_path)

    assert configuration_path(tmp_path).read_text() == original


def test_render_links_results_data_when_experiment_has_results(tmp_path: Path) -> None:
    result = write_baseline_experiment(tmp_path)

    assert "[Results data](results.json)" in gen.render(result)


def test_render_omits_results_data_link_without_results(tmp_path: Path) -> None:
    recipe = write_recipe_tree(tmp_path)

    assert "results.json" not in gen.render(recipe / "001-2026-01-01-test")


def test_update_summary_fills_the_placeholder_title_from_the_folder_name(tmp_path: Path) -> None:
    summary = BASELINE_SUMMARY.replace(
        "# 002 · 2026-01-02 — Baseline", "# NNN · YYYY-MM-DD — Baseline"
    )
    result = write_baseline_experiment(tmp_path, summary)

    _, _, rendered = gen.update_summary(result)

    assert rendered.startswith("# 002 · 2026-01-02 — Baseline\n")


def test_update_summary_describes_a_variant_from_the_rest_of_the_folder_name(
    tmp_path: Path,
) -> None:
    summary = BASELINE_SUMMARY.replace(
        "# 002 · 2026-01-02 — Baseline", "# NNN · YYYY-MM-DD — Baseline"
    )
    result = write_baseline_experiment(tmp_path, summary)
    renamed = result.parent / "003-2026-01-03-baseline-draft-off"
    result.rename(renamed)

    _, _, rendered = gen.update_summary(renamed)

    assert rendered.startswith("# 003 · 2026-01-03 — Baseline draft off\n")


def test_update_summary_replaces_a_title_edited_by_hand(tmp_path: Path) -> None:
    summary = BASELINE_SUMMARY.replace("— Baseline", "— My custom title")
    result = write_baseline_experiment(tmp_path, summary)

    _, _, rendered = gen.update_summary(result)

    assert rendered.startswith("# 002 · 2026-01-02 — Baseline\n")
    assert "My custom title" not in rendered
    assert "Authored intro." in rendered


def test_update_summary_uses_the_profile_title_for_custom_wording(tmp_path: Path) -> None:
    summary = BASELINE_SUMMARY.replace(
        "# 002 · 2026-01-02 — Baseline", "# NNN · YYYY-MM-DD — Baseline"
    )
    result = write_baseline_experiment(tmp_path, summary)
    profile = result / "profile.yaml"
    profile.write_text(profile.read_text() + "title: Long coding session in Pi\n")

    _, _, rendered = gen.update_summary(result)

    assert rendered.startswith("# 002 · 2026-01-02 — Long coding session in Pi\n")


def test_render_does_not_show_the_profile_title_as_a_setting(tmp_path: Path) -> None:
    result = write_baseline_experiment(tmp_path)
    profile = result / "profile.yaml"
    profile.write_text(profile.read_text() + "title: Long coding session in Pi\n")

    configuration = gen.render(result)

    assert "Long coding session in Pi" not in configuration


def test_update_summary_fails_when_the_first_line_is_not_a_title(tmp_path: Path) -> None:
    summary = BASELINE_SUMMARY.replace("# 002 · 2026-01-02 — Baseline", "Intro without a title")
    result = write_baseline_experiment(tmp_path, summary)

    with pytest.raises(ValueError, match="report title"):
        gen.update_summary(result)


def test_main_replaces_a_stale_summary_title_for_a_hand_written_experiment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe = write_recipe_tree(tmp_path)
    summary = recipe / "001-2026-01-01-test" / "summary.md"
    summary.write_text("# 001 · 2025-12-31 — Stale wording\n\nObservations.\n")

    assert run_main(monkeypatch, tmp_path) == 0

    assert summary.read_text().startswith("# 001 · 2026-01-01 — Test\n")


def test_main_check_mode_fails_on_a_stale_summary_title(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_baseline_experiment(tmp_path)
    run_main(monkeypatch, tmp_path)
    summary = tmp_path / "recipes" / SLUG / "002-2026-01-02-baseline" / "summary.md"
    summary.write_text(summary.read_text().replace("— Baseline", "— Renamed"))

    assert run_main(monkeypatch, tmp_path, "--check") == 1


def test_main_check_is_current_after_one_generation_that_filled_a_placeholder_title(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = BASELINE_SUMMARY.replace(
        "# 002 · 2026-01-02 — Baseline", "# NNN · YYYY-MM-DD — Baseline"
    )
    write_baseline_experiment(tmp_path, summary)

    run_main(monkeypatch, tmp_path)

    assert run_main(monkeypatch, tmp_path, "--check") == 0
    index = (tmp_path / "recipes" / SLUG / "recipe.md").read_text()
    assert "002 · 2026-01-02 — Baseline" in index


CANONICAL_SETTINGS: dict[str, object] = {
    "serving": {
        "context_length_tokens": 131072,
        "speculative_decoding": "MTP",
        "custom_gdn_gate": "fp8",
    },
    "sampling": {
        "presence_penalty": 0.0,
        "top_k": 20,
        "temperature": 1.0,
        "min_p": 0.0,
    },
    "thinking": {"control": "reasoning_effort=none", "enabled": False},
    "requests": {"endpoint": "/v1/chat/completions", "concurrency": 1},
    "notes": "Functional checks run at temperature 0.",
}


def write_settings_profile(
    tmp_path: Path,
    settings: dict[str, object],
    labels: dict[str, object] | None = None,
) -> Path:
    recipe = write_recipe_tree(tmp_path)
    result = recipe / "001-2026-01-01-test"
    profile = result / "profile.yaml"
    data = yaml.safe_load(profile.read_text())
    data["settings"] = settings
    if labels is not None:
        data["labels"] = labels
    profile.write_text(yaml.safe_dump(data))
    return result


def test_render_sampling_mode_as_single_row(tmp_path: Path) -> None:
    result = write_settings_profile(
        tmp_path, {"sampling": {"mode": "conservative"}}
    )

    document = gen.render(result)

    sampling = document[document.index("## Sampling") :]
    assert "| Mode | conservative |" in sampling
    assert "| Temperature" not in sampling
    assert "## Thinking" not in document


def test_render_uses_registry_labels_and_canonical_order_for_sampling_keys(
    tmp_path: Path,
) -> None:
    result = write_settings_profile(tmp_path, CANONICAL_SETTINGS)

    document = gen.render(result)

    sampling = document[document.index("## Sampling") : document.index("## Thinking")]
    assert (
        sampling.index("| Temperature | 1 |")
        < sampling.index("| Top K | 20 |")
        < sampling.index("| Min P | 0 |")
        < sampling.index("| Presence penalty | 0 |")
    )


def test_render_orders_setting_sections_regardless_of_yaml_key_order(
    tmp_path: Path,
) -> None:
    result = write_settings_profile(tmp_path, CANONICAL_SETTINGS)

    document = gen.render(result)

    positions = [
        document.index(title)
        for title in (
            "## Serving",
            "## Sampling",
            "## Thinking",
            "## Requests",
            "## Experiment notes",
        )
    ]
    assert positions == sorted(positions)
    assert document.index("Functional checks run at temperature 0.") > positions[-1]


def test_render_orders_serving_rows_by_registry_then_alphabetically(
    tmp_path: Path,
) -> None:
    result = write_settings_profile(
        tmp_path,
        {
            "serving": {
                "custom_gdn_gate": "fp8",
                "context_length_tokens": 131072,
                "another_custom_key": "on",
            }
        },
    )

    document = gen.render(result)

    serving = document[document.index("## Serving") : document.index("\n---\n")]
    assert (
        serving.index("Context length (tokens)")
        < serving.index("Another Custom Key")
        < serving.index("Custom Gdn Gate")
    )


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        (
            {"sampling": {"top_k": 20, "temp": 1.0}},
            "unknown key 'temp' in settings.sampling",
        ),
        ({"thinking": {"effort": "high"}}, "unknown key 'effort' in settings.thinking"),
        ({"requests": {"api_key": "x"}}, "unknown key 'api_key' in settings.requests"),
        ({"Request policy": "temperature 1"}, "not allowed"),
        ({"serving": {"Top K": 20}}, "must be snake_case"),
        ({"serving": {"vision": {"enabled": True}}}, "must not nest"),
        ({"notes": ["a", "b"]}, "notes must be a single string"),
    ],
)
def test_main_rejects_profiles_violating_the_settings_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings: dict[str, object], message: str
) -> None:
    write_settings_profile(tmp_path, settings)

    with pytest.raises(ValueError, match=message):
        gen.render(tmp_path / "recipes" / SLUG / "001-2026-01-01-test")
    assert run_main(monkeypatch, tmp_path) == 2


def test_render_derives_title_case_label_for_engine_specific_serving_key(
    tmp_path: Path,
) -> None:
    result = write_settings_profile(tmp_path, {"serving": {"custom_gdn_gate": "fp8"}})

    assert "| Custom Gdn Gate | fp8 |" in gen.render(result)


def test_render_label_override_wins_over_registry(tmp_path: Path) -> None:
    result = write_settings_profile(
        tmp_path,
        {"sampling": {"top_k": 20}},
        labels={"sampling.top_k": "Top-K override"},
    )

    assert "| Top-K override | 20 |" in gen.render(result)


def test_render_adds_workload_suite_row_from_results_json(tmp_path: Path) -> None:
    result = write_baseline_experiment(tmp_path)

    assert "| Workload suite | 1 |" in gen.render(result)


def test_render_warns_when_profile_sampling_duplicates_results_json_policy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = write_settings_profile(
        tmp_path,
        {"sampling": {"temperature": 1.0, "top_k": 20, "min_p": 0.0}},
    )
    document = {
        "suite_version": "1",
        "policy": {"performance": {"temperature": 1.0, "top_k": 20, "min_p": 0.0}},
    }
    (result / "results.json").write_text(json.dumps(document))
    gen.render(result)

    assert "duplicate policy.performance" in capsys.readouterr().err


def test_render_omits_setting_sections_without_values(tmp_path: Path) -> None:
    result = write_settings_profile(tmp_path, {"serving": {"chunk_size": 1024}, "sampling": {}})

    document = gen.render(result)

    assert "## Sampling" not in document
    assert "## Thinking" not in document
