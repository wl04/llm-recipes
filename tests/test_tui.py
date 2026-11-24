"""Headless dashboard and process-lifecycle tests."""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import replace
from pathlib import Path

import launcher
import pytest
import tui
from launcher import LaunchOptions, Recipe
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Input,
    Link,
    OptionList,
    Select,
    Static,
    Switch,
    TabbedContent,
)

RECIPE = Recipe(
    name="alpha",
    directory=Path("/r/alpha/001-2026-11-14-baseline"),
    runtime="strata",
    runtime_directory=Path("/r"),
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


@pytest.mark.parametrize(
    ("failures", "expected"),
    [(0, "ok"), (1, "1 fail"), (2, "2 fail")],
)
def test_doctor_badge_summarizes_failures(failures: int, expected: str) -> None:
    assert tui.doctor_badge(failures) == expected


def test_main_authenticates_before_opening_dashboard(monkeypatch: pytest.MonkeyPatch) -> None:
    authenticated = False

    def authenticate() -> None:
        nonlocal authenticated
        authenticated = True

    def run(app: tui.LlmRecipesApp) -> None:
        assert authenticated

    monkeypatch.setattr(tui, "refresh_sudo_ticket", authenticate, raising=False)
    monkeypatch.setattr(tui.LlmRecipesApp, "run", run)
    assert tui.main() == 0


def test_start_records_facts_after_container_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[str] = []
    monkeypatch.setattr(tui, "gpu_groups", list)
    monkeypatch.setattr(tui, "prepare_start", lambda *args: None)
    monkeypatch.setattr(
        launcher,
        "record_start_facts",
        lambda recipe, options, **kwargs: recorded.append(kwargs["container_id"]),
    )
    monkeypatch.setattr(
        launcher,
        "_capture_quiet",
        lambda command: subprocess.CompletedProcess(command, 0, "true sha256:accepted", ""),
    )

    def execute(command: list[str]) -> int:
        assert not recorded
        Path(command[command.index("--cidfile") + 1]).write_text("abc123")
        return 0

    monkeypatch.setattr(tui, "execute", execute)
    monkeypatch.setattr(tui, "load_instances", list)

    async def scenario() -> None:
        app = make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            app._recipes = {"alpha": RECIPE}
            app._fill_recipes(app._recipes)
            app.action_start_selected()
            await pilot.pause()
            await pilot.press("enter")
            await asyncio.wait_for(app.workers.wait_for_complete(), timeout=5)
            await pilot.pause()
            assert recorded == ["abc123"]
            assert "Started alpha" in str(app.query_one("#status", Static).render())

    asyncio.run(scenario())


@pytest.mark.parametrize("close_app", [False, True])
def test_logs_reaps_quiet_process_when_closed(
    monkeypatch: pytest.MonkeyPatch, close_app: bool
) -> None:
    import sys

    async def scenario() -> None:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-u",
            "-c",
            "import time; print('ready'); time.sleep(60)",
            stdout=asyncio.subprocess.PIPE,
        )
        started = asyncio.Event()

        async def start(instance: str) -> asyncio.subprocess.Process:
            started.set()
            return process

        monkeypatch.setattr(tui, "start_log_process", start)
        app = make_app()
        try:
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(tui.LogStreamScreen("alpha"))
                await asyncio.wait_for(started.wait(), timeout=5)
                if not close_app:
                    await pilot.press("escape")
                    await asyncio.wait_for(process.wait(), timeout=5)
            await asyncio.wait_for(process.wait(), timeout=5)
            assert process.returncode is not None
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    asyncio.run(scenario())


def test_doctor_updates_recipe_badge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tui, "load_doctor", lambda recipe: (3, 0))

    async def scenario() -> None:
        app = make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            app._recipes = {"alpha": RECIPE}
            app._fill_recipes(app._recipes)
            worker = app._check_doctor("alpha")
            await asyncio.wait_for(worker.wait(), timeout=5)
            await pilot.pause()
            assert app.query_one("#recipe-table", DataTable).get_cell("alpha", "doctor") == "ok"

    asyncio.run(scenario())


def test_load_instances_reports_docker_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    monkeypatch.setattr(
        "tui.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 1, "", "daemon unavailable"),
    )
    with pytest.raises(RuntimeError, match="daemon unavailable"):
        tui.load_instances()


def test_execute_avoids_interactive_sudo_and_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command == ["sudo", "-n", "docker", "stop", "example"]
        assert kwargs["capture_output"] is True
        return subprocess.CompletedProcess(command, 1, "", "credentials expired")

    monkeypatch.setattr("tui.subprocess.run", run)
    with pytest.raises(RuntimeError, match="credentials expired"):
        tui.execute(["sudo", "docker", "stop", "example"])


@pytest.mark.parametrize(("adapter", "vision"), [("strata", "cpu"), ("tabbyapi", "on")])
def test_launch_form_reuses_validated_options_and_retains_edits_after_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, adapter: str, vision: str
) -> None:
    launched: list[LaunchOptions] = []
    recipe = replace(RECIPE, adapter=adapter)

    def launch(selected: Recipe, options: LaunchOptions) -> str | None:
        assert selected == recipe
        launched.append(options)
        if len(launched) == 1:
            raise RuntimeError("port is already allocated")
        return None

    monkeypatch.setattr(tui, "DEFAULT_MODELS", tmp_path)
    monkeypatch.setattr(tui, "launch_recipe", launch)
    monkeypatch.setattr(
        tui,
        "load_instances",
        lambda: [
            INSTANCE_RECORD,
            {**INSTANCE_RECORD, "instance": "coding"},
        ],
    )

    async def scenario() -> None:
        app = make_app()
        async with app.run_test(size=(80, 24)) as pilot:
            app._recipes = {recipe.name: recipe}
            app._fill_recipes(app._recipes)
            await pilot.press("s")
            form = app.screen
            form.query_one("#launch-start", Button).active_effect_duration = 0
            assert form.query_one("#launch-context", Input).value == str(recipe.context)
            form.query_one("#launch-name", Input).value = "coding"
            form.query_one("#launch-context", Input).value = "12345"
            await pilot.click("#launch-start")
            assert not launched
            assert "multiple of 256" in str(form.query_one("#launch-error", Static).render())

            context = form.query_one("#launch-context", Input)
            context.focus()
            await pilot.press("down", "end", "enter")
            assert context.value == "262144"
            assert context.has_focus
            await pilot.press("ctrl+shift+a", "6", "5", "7", "9", "2")
            assert context.value == "65792"
            await pilot.press("enter", "escape")
            assert app.screen is form
            assert context.value == "65792"
            await pilot.click("#context-arrow")
            menu = form.query_one("#context-presets", OptionList)
            assert menu.display
            await pilot.click("#context-arrow")
            assert not menu.display
            await pilot.click("#context-arrow")
            await pilot.press("home", "down", "enter")
            assert context.value == "65536"
            form.query_one("#launch-port", Input).value = "8081"
            form.query_one("#launch-draft", Switch).value = False
            assert bool(form.query("#launch-api-monitor")) == (adapter == "strata")
            if adapter == "strata":
                monitor = form.query_one("#launch-api-monitor", Checkbox)
                assert not monitor.value
                monitor.value = True
            form.query_one("#launch-vision", Select).value = vision
            await pilot.pause()
            assert "127.0.0.1:8081/v1" in str(form.query_one("#launch-preview", Static).render())

            await pilot.click("#launch-start")
            await asyncio.wait_for(app.workers.wait_for_complete(), timeout=5)
            assert app.screen is form
            assert form.query_one("#launch-port", Input).value == "8081"
            assert "port is already allocated" in str(
                form.query_one("#launch-error", Static).render()
            )

            await pilot.click("#launch-start")
            await asyncio.wait_for(app.workers.wait_for_complete(), timeout=5)
            await pilot.pause()
            assert app.screen is not form
            assert app.query_one(TabbedContent).active == "instances"
            assert app._selected_name("#instance-table") == "coding"
            assert "127.0.0.1:8081/v1" in str(app.query_one("#status", Static).render())

    asyncio.run(scenario())
    assert (
        launched
        == [
            LaunchOptions(
                "coding",
                tmp_path,
                tmp_path / "logs/coding",
                65536,
                "off",
                vision,
                8081,
                True,
                api_monitor=adapter == "strata",
            )
        ]
        * 2
    )


def test_launch_form_resets_defaults_and_escape_cancels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched: list[LaunchOptions] = []
    monkeypatch.setattr(tui, "launch_recipe", lambda recipe, options: launched.append(options))

    async def scenario() -> None:
        app = make_app()
        async with app.run_test(size=(80, 24)) as pilot:
            app._recipes = {RECIPE.name: RECIPE}
            app._fill_recipes(app._recipes)
            await pilot.press("s")
            form = app.screen
            form.query_one("#launch-name", Input).value = "custom"
            form.query_one("#launch-port", Input).value = "8081"
            form.query_one("#launch-context", Input).value = "196608"
            await pilot.click("#launch-reset")
            assert form.query_one("#launch-context", Input).value == str(RECIPE.context)
            assert form.query_one("#launch-name", Input).value == RECIPE.name
            assert form.query_one("#launch-port", Input).value == str(RECIPE.port)
            await pilot.press("escape")
            assert app.screen is not form

    asyncio.run(scenario())
    assert not launched


def test_instance_dashboard_links_follow_selected_published_port() -> None:
    async def scenario() -> None:
        app = make_app()
        async with app.run_test() as pilot:
            strata = replace(OTHER_RECIPE, adapter="strata", port=8080)
            app._fill_recipes({RECIPE.name: RECIPE, strata.name: strata})
            records = [
                {**INSTANCE_RECORD, "instance": "one", "ports": "127.0.0.1:8081->5000/tcp"},
                {
                    **INSTANCE_RECORD,
                    "instance": "two",
                    "recipe": strata.name,
                    "ports": "127.0.0.1:8082->8080/tcp",
                },
            ]
            app.query_one(TabbedContent).active = "instances"
            app._fill_instances(records)
            await pilot.pause()
            link = app.query_one("#instance-dashboard", Link)
            assert link.display
            assert link.url == "http://127.0.0.1:8081/ui/status"
            app.query_one("#instance-table", DataTable).move_cursor(row=1)
            await pilot.pause()
            assert link.url == "http://127.0.0.1:8082/"
            app._fill_instances([])
            await pilot.pause()
            assert not link.display

    asyncio.run(scenario())
