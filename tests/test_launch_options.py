"""Resolution of launch options from recipe defaults and explicit overrides."""

from pathlib import Path

from launcher import discover_recipes, resolve_launch_options

ROOT = Path(__file__).resolve().parents[1]
RECIPE = discover_recipes(ROOT / "recipes")[
    "qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram"
]


def test_resolve_launch_options_uses_recipe_defaults_for_unset_values(tmp_path: Path) -> None:
    options = resolve_launch_options(
        RECIPE, name="baseline", models=tmp_path, logs=tmp_path / "logs", detached=True
    )

    assert (options.context, options.draft, options.vision, options.port) == (
        131072,
        "on",
        "cpu",
        8080,
    )
    assert (options.name, options.models, options.logs, options.detached) == (
        "baseline",
        tmp_path,
        tmp_path / "logs",
        True,
    )


def test_resolve_launch_options_prefers_explicit_values(tmp_path: Path) -> None:
    options = resolve_launch_options(
        RECIPE,
        name="baseline",
        models=tmp_path,
        logs=tmp_path,
        context=32768,
        draft="off",
        vision="off",
        port=9000,
    )

    assert (options.context, options.draft, options.vision, options.port) == (
        32768,
        "off",
        "off",
        9000,
    )
