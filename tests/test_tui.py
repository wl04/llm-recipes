"""Headless tests for the recipe TUI.

The app fetches host data in threaded workers; the scheduler itself is not
exercised here. Tests disable the background refresh and drive the
synchronous fill, selection, and status methods directly — that is the
app's own logic; workers only move IO calls off the UI thread.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

pytest.importorskip("textual")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import tui
from launcher import Recipe
from textual.widgets import DataTable, Static

RECIPE = Recipe(
    name="alpha",
    directory=Path("/r/alpha/001-2026-11-14-baseline"),
    runtime="strata",
    runtime_directory=Path("/r"),
    data_directory="alpha",
    adapter="tabbyapi",
    engine="Strata",
    image="image:tag",
    port=5000,
    context=8192,
    draft="on",
    vision="off",
)

OTHER_RECIPE = Recipe(
    name="beta",
    directory=Path("/r/beta/001-2026-11-14-baseline"),
    runtime="tabbyapi",
    runtime_directory=Path("/r"),
    data_directory="beta",
    adapter="tabbyapi",
    engine="TabbyAPI",
    image="image:tag",
    port=5001,
    context=8192,
    draft="off",
    vision="off",
)

INSTANCE_RECORD = {
    "instance": "strata-alpha",
    "recipe": "alpha",
    "status": "running",
    "ports": "5005->5000/tcp",
}


class SilentApp(tui.LlmRecipesApp):
    """Skips the automatic background refresh so tests stay deterministic."""

    def refresh_all(self) -> None:
        pass


def make_app() -> SilentApp:
    return SilentApp()


def test_fill_recipes_renders_one_row_per_recipe_with_pending_doctor() -> None:
    async def scenario() -> None:
        app = make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            app._fill_recipes({"alpha": RECIPE})
            table = app.query_one("#recipe-table", DataTable)
            assert table.row_count == 1
            row = table.get_row_at(0)
            assert row[0] == "alpha"
            assert row[1] == "strata"
            assert row[3] == "5000"
            assert row[4] == "checking…"

    asyncio.run(scenario())


def test_fill_recipes_replaces_rows_and_keeps_cursor_within_bounds() -> None:
    async def scenario() -> None:
        app = make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            app._fill_recipes({"alpha": RECIPE})
            table = app.query_one("#recipe-table", DataTable)
            table.move_cursor(row=0)
            app._fill_recipes({"beta": OTHER_RECIPE})
            assert table.row_count == 1
            assert table.ordered_rows[0].key == "beta"
            assert table.cursor_row == 0

    asyncio.run(scenario())


def test_selected_recipe_name_reports_cursor_row_or_none() -> None:
    async def scenario() -> None:
        app = make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app._selected_name("#recipe-table") is None
            app._fill_recipes({"alpha": RECIPE})
            app.query_one("#recipe-table", DataTable).move_cursor(row=0)
            assert app._selected_name("#recipe-table") == "alpha"

    asyncio.run(scenario())


def test_fill_instances_renders_status_and_ports() -> None:
    async def scenario() -> None:
        app = make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            app._fill_instances([INSTANCE_RECORD])
            table = app.query_one("#instance-table", DataTable)
            assert table.row_count == 1
            row = table.get_row_at(0)
            assert row[0] == "strata-alpha"
            assert row[2] == "running"
            assert row[3] == "5005->5000/tcp"

    asyncio.run(scenario())


def test_stop_selected_without_focused_row_does_not_run_any_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def execute(command: list[str]) -> int:
        calls.append(command)
        return 0

    monkeypatch.setattr(tui, "execute", execute)

    async def scenario() -> None:
        app = make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            app._fill_instances([])
            app.action_stop_selected()
            await pilot.pause()
            assert calls == []

    asyncio.run(scenario())


def test_start_selected_without_focused_row_does_not_run_any_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def execute(command: list[str]) -> int:
        calls.append(command)
        return 0

    monkeypatch.setattr(tui, "execute", execute)

    async def scenario() -> None:
        app = make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            app._fill_recipes({})
            app.action_start_selected()
            await pilot.pause()
            assert calls == []

    asyncio.run(scenario())


def test_status_updates_status_line() -> None:
    async def scenario() -> None:
        app = make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            app._status("Started alpha")
            await pilot.pause()
            assert "Started alpha" in str(app.query_one("#status", Static).render())

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("failures", "expected"),
    [(0, "ok"), (1, "1 fail"), (2, "2 fail")],
)
def test_doctor_badge_summarizes_failures(failures: int, expected: str) -> None:
    assert tui.doctor_badge(failures) == expected
