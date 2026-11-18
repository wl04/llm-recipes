#!/usr/bin/env python3
"""Terminal dashboard for recipes, instances, diagnostics, and logs."""

import asyncio
import os
import subprocess
import sys
from collections import deque
from pathlib import Path
from typing import ClassVar

import paths
from doctor import diagnose
from launcher import (
    VISION_MODES,
    LaunchOptions,
    Recipe,
    discover_recipes,
    gpu_groups,
    instance_name,
    instances_command,
    lifecycle_command,
    parse_instances,
    prepare_start,
    refresh_sudo_ticket,
    resolve_launch_options,
    start_command,
    start_with_facts,
    validate_options,
)
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODELS = paths.data_home()
LOG_HISTORY = 500


def load_recipes() -> dict[str, Recipe]:
    """Discover launchable recipes from the repository."""
    return discover_recipes(ROOT / "recipes")


def load_instances() -> list[dict[str, str]]:
    """List running managed instances; empty when Docker reports none."""
    listing = subprocess.run(
        noninteractive(instances_command()), check=False, capture_output=True, text=True, timeout=15
    )
    if listing.returncode != 0:
        raise RuntimeError(listing.stderr.strip() or "Docker instance listing failed")
    return parse_instances(listing.stdout)


def load_doctor(recipe: Recipe) -> tuple[int, int]:
    """Run read-only recipe diagnostics; return (check_count, failure_count)."""
    findings = diagnose(recipe, DEFAULT_MODELS)
    return len(findings), sum(1 for item in findings if item.status == "FAIL")


def doctor_badge(failures: int) -> str:
    """Render the doctor result as a compact table cell."""
    return "ok" if failures == 0 else f"{failures} fail"


def noninteractive(command: list[str]) -> list[str]:
    """Prevent password prompts inside the dashboard."""
    return ["sudo", "-n", *command[1:]] if command[:2] == ["sudo", "docker"] else command


def execute(command: list[str]) -> int:
    """Capture command output so it cannot overwrite the dashboard."""
    result = subprocess.run(noninteractive(command), capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Command exited with {result.returncode}")
    return result.returncode


async def start_log_process(instance: str) -> asyncio.subprocess.Process:
    """Follow logs without blocking the UI event loop."""
    return await asyncio.create_subprocess_exec(
        *noninteractive(lifecycle_command("logs", instance, follow=True)),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
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

    @work(exclusive=True)
    async def stream_logs(self) -> None:
        process = await start_log_process(self.instance)
        try:
            if process.stdout is None:
                return
            while line := await process.stdout.readline():
                self._lines.append(line.decode(errors="replace").rstrip())
                self._redraw()
        finally:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=2)
                except TimeoutError:
                    process.kill()
                    await asyncio.wait_for(process.wait(), timeout=2)
            else:
                await process.wait()

    def _redraw(self) -> None:
        self.query_one("#log-box", Static).update("\n".join(self._lines))
        self.query_one("#log-frame", VerticalScroll).scroll_end(animate=False)

    def on_unmount(self) -> None:
        self.workers.cancel_all()


def launch_recipe(recipe: Recipe, options: LaunchOptions) -> str | None:
    """Start a detached instance and return any launch metadata warning."""
    command = start_command(recipe, options, groups=gpu_groups(), uid=os.getuid(), gid=os.getgid())
    prepare_start(recipe, options)
    status, warning = start_with_facts(recipe, options, command, execute)
    if status:
        raise RuntimeError(f"Docker start exited with {status}")
    return warning


class LaunchScreen(ModalScreen[tuple[LaunchOptions, str | None]]):
    """Edit the options for one launch."""

    AUTO_FOCUS = "#launch-start"
    BINDINGS: ClassVar = [("escape", "cancel", "Cancel")]
    CSS = """
    LaunchScreen { align: center middle; }
    #launch-dialog {
        width: 96%;
        max-width: 80;
        height: auto;
        max-height: 96%;
        padding: 0 1;
        border: round $accent;
        background: $surface;
    }
    #launch-title { height: auto; text-style: bold; }
    #launch-fields { height: auto; max-height: 18; }
    .launch-row { height: auto; align-vertical: middle; }
    .launch-row Label { width: 17; }
    .launch-row Input, .launch-row Select { width: 1fr; }
    #launch-preview, #launch-error { height: auto; }
    #launch-error { color: $error; }
    #launch-buttons { height: 3; }
    #launch-buttons Button { min-width: 8; margin-right: 1; }
    """

    def __init__(self, recipe: Recipe, models: Path) -> None:
        super().__init__()
        self.recipe = recipe
        self.models = models
        self._starting = False

    def compose(self) -> ComposeResult:
        recipe = self.recipe
        vision_labels = {"off": "Off", "on": "GPU", "cpu": "CPU"}
        with Vertical(id="launch-dialog"):
            yield Static(f"Launch {recipe.name}", id="launch-title", markup=False)
            with VerticalScroll(id="launch-fields"):
                with Horizontal(classes="launch-row"):
                    yield Label("Instance name")
                    yield Input(recipe.name, id="launch-name", compact=True)
                with Horizontal(classes="launch-row"):
                    yield Label("Context tokens")
                    yield Input(
                        str(recipe.context), type="integer", id="launch-context", compact=True
                    )
                with Horizontal(classes="launch-row"):
                    yield Label("Drafting")
                    yield Switch(recipe.draft == "on", id="launch-draft")
                with Horizontal(classes="launch-row"):
                    yield Label("Vision")
                    yield Select(
                        [(vision_labels[value], value) for value in VISION_MODES[recipe.adapter]],
                        value=recipe.vision,
                        allow_blank=False,
                        id="launch-vision",
                        compact=True,
                    )
                with Horizontal(classes="launch-row"):
                    yield Label("Host port")
                    yield Input(str(recipe.port), type="integer", id="launch-port", compact=True)
                yield Static("", id="launch-preview", markup=False)
                yield Static("", id="launch-error", markup=False)
            with Horizontal(id="launch-buttons"):
                yield Button("Start", variant="primary", id="launch-start")
                yield Button("Reset defaults", id="launch-reset")
                yield Button("Cancel", id="launch-cancel")

    def on_mount(self) -> None:
        self._update_preview()

    def _field(self, name: str) -> Input:
        return self.query_one(f"#launch-{name}", Input)

    def _number(self, field: str, label: str) -> int:
        try:
            return int(self._field(field).value)
        except ValueError as error:
            raise ValueError(f"{label} must be a whole number") from error

    def _options(self) -> LaunchOptions:
        name = instance_name(self._field("name").value.strip())
        options = resolve_launch_options(
            self.recipe,
            name=name,
            models=self.models,
            logs=paths.logs_dir(self.models, name),
            context=self._number("context", "Context"),
            draft="on" if self.query_one("#launch-draft", Switch).value else "off",
            vision=str(self.query_one("#launch-vision", Select).value),
            port=self._number("port", "Host port"),
            detached=True,
        )
        validate_options(options, self.recipe.adapter)
        return options

    def _update_preview(self) -> None:
        try:
            options = self._options()
        except ValueError:
            text = f"Model root: {self.models}\nEnter valid launch options to preview the address."
        else:
            text = (
                f"API: http://127.0.0.1:{options.port}/v1\n"
                f"Model root: {options.models}\nLogs: {options.logs}"
            )
        self.query_one("#launch-preview", Static).update(text)

    def on_input_changed(self) -> None:
        self._update_preview()

    def action_cancel(self) -> None:
        if not self._starting:
            self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self._starting:
            return
        if event.button.id == "launch-cancel":
            self.action_cancel()
        elif event.button.id == "launch-reset":
            recipe = self.recipe
            self._field("name").value = recipe.name
            self._field("context").value = str(recipe.context)
            self._field("port").value = str(recipe.port)
            self.query_one("#launch-draft", Switch).value = recipe.draft == "on"
            self.query_one("#launch-vision", Select).value = recipe.vision
            self.query_one("#launch-error", Static).update("")
        elif event.button.id == "launch-start":
            error_box = self.query_one("#launch-error", Static)
            try:
                options = self._options()
            except ValueError as error:
                error_box.update(str(error))
                error_box.scroll_visible()
                return
            self._set_starting(True)
            error_box.update("Starting container…")
            error_box.scroll_visible()
            self._start(options)

    def _set_starting(self, starting: bool) -> None:
        self._starting = starting
        for widget in self.query("Input, Switch, Select, Button"):
            widget.disabled = starting

    @work
    async def _start(self, options: LaunchOptions) -> None:
        try:
            warning = await asyncio.to_thread(launch_recipe, self.recipe, options)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            self._set_starting(False)
            self.query_one("#launch-start", Button).focus()
            error_box = self.query_one("#launch-error", Static)
            error_box.update(str(error))
            error_box.scroll_visible()
        else:
            self.dismiss((options, warning))


class LlmRecipesApp(App[None]):
    """Recipe dashboard with doctor badges and a live instance list."""

    CSS = """
    #status { height: auto; min-height: 1; max-height: 3; dock: bottom; }
    """
    BINDINGS: ClassVar = [
        ("s", "start_selected", "Configure launch"),
        ("x", "stop_selected", "Stop instance"),
        ("l", "show_logs", "Show logs"),
        ("r", "refresh_all", "Refresh"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._recipes: dict[str, Recipe] = {}
        self._instance_to_select: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="status", markup=False)
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
        recipes.add_columns("Recipe", "Runtime", "Engine", "Port")
        recipes.add_column("Doctor", key="doctor")
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

    @work(thread=True, exclusive=True, group="load_recipes")
    def load_recipes(self) -> None:
        try:
            recipes = load_recipes()
        except Exception as error:  # noqa: BLE001 - the status bar reports worker failures
            self.call_from_thread(self._status, f"Recipe discovery failed: {error}")
            return
        self._recipes = recipes
        self.call_from_thread(self._fill_recipes, recipes)
        for recipe in recipes.values():
            self.call_from_thread(self._check_doctor, recipe.name)

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
                table.update_cell(name, "doctor", badge)

        self.call_from_thread(apply_badge)

    @work(thread=True, exclusive=True, group="load_instances")
    def load_instances(self) -> None:
        try:
            instances = load_instances()
        except Exception as error:  # noqa: BLE001 - the status bar reports worker failures
            self.call_from_thread(self._status, f"Instance listing failed: {error}")
            return
        self.call_from_thread(self._fill_instances, instances)

    def _fill_instances(self, instances: list[dict[str, str]]) -> None:
        table = self.query_one("#instance-table", DataTable)
        selected = self._selected_name("#instance-table")
        preferred = self._instance_to_select
        table.clear(columns=False)
        for record in instances:
            table.add_row(
                record["instance"],
                record["recipe"],
                record["status"],
                record["ports"],
                key=record["instance"],
            )
        if preferred is not None and preferred in table.rows:
            selected = preferred
            self._instance_to_select = None
        if selected is not None and selected in table.rows:
            table.move_cursor(row=table.get_row_index(selected))

    def _selected_name(self, selector: str) -> str | None:
        """Return the key of the focused row in the addressed table."""
        table = self.query_one(selector, DataTable)
        if table.cursor_row is None or table.cursor_row >= table.row_count:
            return None
        return table.ordered_rows[table.cursor_row].key.value

    def action_start_selected(self) -> None:
        if self.query_one(TabbedContent).active != "recipes":
            return
        name = self._selected_name("#recipe-table")
        if name is not None and (recipe := self._recipes.get(name)) is not None:
            self.push_screen(LaunchScreen(recipe, DEFAULT_MODELS), self._launch_finished)

    def _launch_finished(self, result: tuple[LaunchOptions, str | None] | None) -> None:
        if result is None:
            return
        options, warning = result
        message = f"Started {options.name}\nModel loading: http://127.0.0.1:{options.port}/v1"
        if warning:
            message += f" · {warning}"
        self._status(message)
        self._instance_to_select = options.name
        self.query_one(TabbedContent).active = "instances"
        self.query_one("#instance-table", DataTable).focus()
        self.load_instances()

    def action_stop_selected(self) -> None:
        name = self._selected_name("#instance-table")
        if name is not None:
            self.stop_instance(name)

    @work(thread=True, exclusive=True, group="stop_instance")
    def stop_instance(self, name: str) -> None:
        try:
            status = execute(lifecycle_command("stop", name))
        except (OSError, RuntimeError) as error:
            self.call_from_thread(self._status, f"Stop {name} failed: {error}")
            return
        result = f"Stopped {name}" if status == 0 else f"Stop {name} exited with {status}"
        self.call_from_thread(self._status, result)
        self.call_from_thread(self.load_instances)

    def action_show_logs(self) -> None:
        name = self._selected_name("#instance-table")
        if name is not None:
            self.push_screen(LogStreamScreen(name))


def main() -> int:
    try:
        refresh_sudo_ticket()
    except (OSError, ValueError) as error:
        print(f"tui: {error}", file=sys.stderr)
        return 1
    LlmRecipesApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
