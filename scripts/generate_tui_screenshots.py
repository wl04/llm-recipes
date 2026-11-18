#!/usr/bin/env python3
"""Generate the documentation screenshots from the headless dashboard."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from textual.widgets import TabbedContent
from tui import LaunchScreen, LlmRecipesApp, load_recipes

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets/tui"
DEMO_MODELS = Path("/home/user/llm-recipes")
TERMINAL_SIZE = (100, 23)


class ScreenshotApp(LlmRecipesApp):
    """Render the dashboard with fixture data and no Docker polling."""

    TITLE = "llm-recipes"

    def refresh_all(self) -> None:
        pass

    def _tick(self) -> None:
        pass


async def capture() -> dict[str, str]:
    """Render the Instances tab and the Strata launch form."""
    recipes = load_recipes()
    example = next(recipe for recipe in recipes.values() if recipe.adapter == "tabbyapi")
    strata = next(recipe for recipe in recipes.values() if recipe.adapter == "strata")
    app = ScreenshotApp()
    app.theme = "textual-dark"
    app.animation_level = "none"
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        app._fill_recipes(recipes)
        app._fill_instances(
            [
                {
                    "instance": "coding",
                    "recipe": example.name,
                    "status": "Up 5 minutes",
                    "ports": f"127.0.0.1:{example.port}->{example.port}/tcp",
                }
            ]
        )
        tabs = app.query_one(TabbedContent)
        tabs.active = "instances"
        await pilot.pause()
        instances = app.export_screenshot(title="llm-recipes dashboard")

        tabs.active = "recipes"
        await pilot.pause()
        await app.push_screen(LaunchScreen(strata, DEMO_MODELS))
        await pilot.pause()
        launch = app.export_screenshot(title="llm-recipes launch settings")

    return {"dashboard.svg": instances, "launch-settings.svg": launch}


def main(argv: list[str] | None = None) -> int:
    """Write changed screenshots or report stale files without editing them."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report missing or stale screenshots")
    args = parser.parse_args(argv)
    # Textual and Rich read NO_COLOR separately. Capture the documentation theme in color.
    no_color = os.environ.pop("NO_COLOR", None)
    try:
        screenshots = asyncio.run(capture())
    finally:
        if no_color is not None:
            os.environ["NO_COLOR"] = no_color
    stale = []
    for name, svg in screenshots.items():
        path = OUTPUT / name
        content = ("\n".join(line.rstrip() for line in svg.splitlines()) + "\n").encode("utf-8")
        if path.is_file() and path.read_bytes() == content:
            continue
        if args.check:
            stale.append(path.relative_to(ROOT))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    if stale:
        for path in stale:
            print(f"Missing or stale screenshot: {path}", file=sys.stderr)
        print("Run .venv/bin/python scripts/generate_tui_screenshots.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
