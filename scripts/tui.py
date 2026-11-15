#!/usr/bin/env python3
"""Terminal dashboard over the launcher: recipes, instances, doctor, and logs.

Part of the optional ``tui`` extra (``uv pip install -e '.[tui]'``). All host
effects go through the small IO functions below, so the UI can be tested with
fakes and the launcher stays free of presentation concerns.
"""

import os
import subprocess
from collections import deque
from pathlib import Path
from typing import ClassVar

import paths
from doctor import diagnose
from launcher import (
    Recipe,
    discover_recipes,
    gpu_groups,
    instances_command,
    lifecycle_command,
    parse_instances,
    prepare_start,
    resolve_launch_options,
    run_command,
    start_command,
)

try:
    from textual import work
    from textual.app import App, ComposeResult
    from textual.containers import VerticalScroll
    from textual.screen import ModalScreen
    from textual.widgets import DataTable, Footer, Header, Static, TabbedContent, TabPane
except ModuleNotFoundError as import_error:  # pragma: no cover - depends on extra
    raise SystemExit(
        "The TUI requires the optional extra: uv pip install -e '.[tui]'"
    ) from import_error

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODELS = paths.data_home()
LOG_HISTORY = 500


def load_recipes() -> dict[str, Recipe]:
    """Discover launchable recipes from the repository."""
    return discover_recipes(ROOT / "recipes")


def load_instances() -> list[dict[str, str]]:
    """List running managed instances; empty when Docker reports none."""
    listing = subprocess.run(instances_command(), check=False, capture_output=True, text=True)
    if listing.returncode != 0:
        return []
    return parse_instances(listing.stdout)


def load_doctor(recipe: Recipe) -> tuple[int, int]:
    """Run read-only recipe diagnostics; return (check_count, failure_count)."""
    findings = diagnose(recipe, DEFAULT_MODELS)
    return len(findings), sum(1 for item in findings if item.status == "FAIL")


def doctor_badge(failures: int) -> str:
    """Render the doctor result as a compact table cell."""
    return "ok" if failures == 0 else f"{failures} fail"


def execute(command: list[str]) -> int:
    """Run a launcher command with inherited streams."""
    return run_command(command)


def start_log_process(instance: str) -> subprocess.Popen[str]:
    """Start following instance logs with stderr folded into stdout."""
    return subprocess.Popen(
        lifecycle_command("logs", instance, follow=True),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


class LogStreamScreen(ModalScreen[None]):
    """Live instance log output; closes on Escape."""

    CSS = """
    LogStreamScreen { align: center middle; }
    #log-frame { width: 95%; height: 90%; border: thick $panel; }
    #log-box { height: 1fr; }
    """
    BINDINGS: ClassVar = [("escape", "dismiss()", "Close")]

    def __init__(self, instance: str) -> None:
        super().__init__()
        self.instance = instance
        self._lines: deque[str] = deque(maxlen=LOG_HISTORY)

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="log-frame"):
            yield Static("", id="log-box", markup=False)

    def on_mount(self) -> None:
        self.stream_logs()

    @work(thread=True, exclusive=True)
    def stream_logs(self) -> None:
        process = start_log_process(self.instance)
        try:
            stream = process.stdout
            if stream is None:
                return
            for line in stream:
                self._lines.append(line.rstrip())
                self.app.call_from_thread(self._redraw)
        finally:
            process.terminate()

    def _redraw(self) -> None:
        self.query_one("#log-box", Static).update("\n".join(self._lines))
        self.query_one("#log-frame", VerticalScroll).scroll_end(animate=False)

    def on_dismiss(self) -> None:
        self.workers.cancel_all()


class LlmRecipesApp(App[None]):
    """Recipe dashboard with doctor badges and a live instance list."""

    CSS = """
    #status { height: 1; dock: bottom; }
    """
    BINDINGS: ClassVar = [
        ("s", "start_selected", "Start recipe"),
        ("x", "stop_selected", "Stop instance"),
        ("l", "show_logs", "Show logs"),
        ("r", "refresh_all", "Refresh"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._recipes: dict[str, Recipe] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="status")
        with TabbedContent():
            with TabPane("Recipes", id="recipes"):
                yield DataTable(id="recipe-table")
            with TabPane("Instances", id="instances"):
                yield DataTable(id="instance-table")
        yield Footer()

    def on_mount(self) -> None:
        self._setup_tables()
        self.refresh_all()
        self.set_interval(10, self._tick)

    def _setup_tables(self) -> None:
        recipes = self.query_one("#recipe-table", DataTable)
        recipes.add_columns("Recipe", "Runtime", "Engine", "Port", "Doctor")
        instances = self.query_one("#instance-table", DataTable)
        instances.add_columns("Instance", "Recipe", "Status", "Ports")
        for table in (recipes, instances):
            table.cursor_type = "row"

    def _tick(self) -> None:
        self.load_instances()

    def refresh_all(self) -> None:
        self.load_recipes()
        self.load_instances()

    def _status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    @work(thread=True, exclusive=True)
    def load_recipes(self) -> None:
        try:
            recipes = load_recipes()
        except Exception as error:  # noqa: BLE001 - the status bar reports worker failures
            self.call_from_thread(self._status, f"Recipe discovery failed: {error}")
            return
        self._recipes = recipes
        self.call_from_thread(self._fill_recipes, recipes)
        for recipe in recipes.values():
            self._check_doctor(recipe.name)

    def _fill_recipes(self, recipes: dict[str, Recipe]) -> None:
        table = self.query_one("#recipe-table", DataTable)
        selected = table.cursor_row
        table.clear(columns=False)
        for recipe in recipes.values():
            table.add_row(
                recipe.name,
                recipe.runtime,
                recipe.engine,
                str(recipe.port),
                "checking…",
                key=recipe.name,
            )
        if selected is not None and selected < table.row_count:
            table.move_cursor(row=selected)

    @work(thread=True)
    def _check_doctor(self, name: str) -> None:
        recipe = self._recipes[name]
        try:
            _, failures = load_doctor(recipe)
        except Exception as error:  # noqa: BLE001 - the status bar reports worker failures
            self.call_from_thread(self._status, f"Doctor failed for {name}: {error}")
            badge = "error"
        else:
            badge = doctor_badge(failures)

        def apply_badge() -> None:
            table = self.query_one("#recipe-table", DataTable)
            if name in table.rows:
                table.update_cell(name, "Doctor", badge)

        self.call_from_thread(apply_badge)

    @work(thread=True, exclusive=True)
    def load_instances(self) -> None:
        try:
            instances = load_instances()
        except Exception as error:  # noqa: BLE001 - the status bar reports worker failures
            self.call_from_thread(self._status, f"Instance listing failed: {error}")
            return
        self.call_from_thread(self._fill_instances, instances)

    def _fill_instances(self, instances: list[dict[str, str]]) -> None:
        table = self.query_one("#instance-table", DataTable)
        selected = table.cursor_row
        table.clear(columns=False)
        for record in instances:
            table.add_row(
                record["instance"],
                record["recipe"],
                record["status"],
                record["ports"],
                key=record["instance"],
            )
        if selected is not None and selected < table.row_count:
            table.move_cursor(row=selected)

    def _selected_name(self, selector: str) -> str | None:
        """Return the key of the focused row in the addressed table."""
        table = self.query_one(selector, DataTable)
        if table.cursor_row is None or table.cursor_row >= table.row_count:
            return None
        return table.ordered_rows[table.cursor_row].key.value

    def action_start_selected(self) -> None:
        name = self._selected_name("#recipe-table")
        if name is not None:
            self.start_instance(name)

    @work(thread=True, exclusive=True)
    def start_instance(self, name: str) -> None:
        recipe = self._recipes.get(name)
        if recipe is None:
            self.call_from_thread(self._status, f"Unknown recipe: {name}")
            return
        try:
            options = resolve_launch_options(
                recipe,
                name=name,
                models=DEFAULT_MODELS,
                logs=paths.logs_dir(DEFAULT_MODELS, name),
                context=None,
                draft=None,
                vision=None,
                port=None,
                detached=True,
            )
            command = start_command(
                recipe, options, groups=gpu_groups(), uid=os.getuid(), gid=os.getgid()
            )
            prepare_start(recipe, options)
            status = execute(command)
        except Exception as error:  # noqa: BLE001 - the status bar reports worker failures
            self.call_from_thread(self._status, f"Start {name} failed: {error}")
            return
        message = f"Started {name}" if status == 0 else f"Start {name} exited with {status}"
        self.call_from_thread(self._status, message)
        self.load_instances()

    def action_stop_selected(self) -> None:
        name = self._selected_name("#instance-table")
        if name is not None:
            self.stop_instance(name)

    @work(thread=True, exclusive=True)
    def stop_instance(self, name: str) -> None:
        status = execute(lifecycle_command("stop", name))
        result = f"Stopped {name}" if status == 0 else f"Stop {name} exited with {status}"
        self.call_from_thread(self._status, result)
        self.load_instances()

    def action_show_logs(self) -> None:
        name = self._selected_name("#instance-table")
        if name is not None:
            self.push_screen(LogStreamScreen(name))


def main() -> int:
    LlmRecipesApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
