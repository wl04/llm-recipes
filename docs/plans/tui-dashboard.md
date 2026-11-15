# Plan: TUI dashboard

An optional terminal dashboard over the launcher: recipes, instances, logs, and eventually
baseline runs. The CLI contract is the product; the TUI is sugar over it and replaceable.

## Constraints

- **Textual** is an **optional extra**, never a hard dependency:
  `[project.optional-dependencies] tui = ["textual>=8.2,<9"]`. Nothing in `check.sh` starts the
  GUI. `scripts/tui.py` imports Textual lazily, `tests/test_tui.py` skips when Textual is
  absent, and `textual` is pinned in `dev-requirements.txt` so CI exercises the real package.
- Maintenance rests on one maintainer (Textual's company wound down its stewardship):
  the pinned range holds, and nothing outside `scripts/tui.py` may import Textual.

## Architecture guarantees

The TUI consumes the launcher through these contracts.

1. Machine-readable output: `list`, `ps`, `status`, and `doctor` accept `--json`;
   the TUI consumes JSON, never parses prose tables.
2. Operations callable in-process: the pure builders (`start_command`,
   `lifecycle_command`) and exit-status `run_command` are imported from `launcher.py`;
   the TUI never shells out to `launch.py`, which stays a thin argparse presentation
   with no import-time side effects.
3. No interactive prompts inside library functions — the guided interview injects
   `_ask`/`_progress` callables (`guided.guide(...)`), so the TUI can supply
   widget-backed callables; the upfront `sudo -v` model keeps subprocesses prompt-free.
4. Long-running output (`logs --follow`, baseline runs) is consumable from worker
   threads via streamed stdout.

## Dashboard surface

- Recipe list with per-recipe doctor badges (async checks, no UI freeze).
- Instance dashboard: running instances from `ps --json`, start/stop of the selected
  instance in worker threads, and a streamed `logs --follow` modal.
- Headless test pattern: a `SilentApp` subclass overriding `refresh_all()`, so the
  suite verifies behavior without a running Textual pilot loop.

## Not yet built

- Baseline run launcher: recipe and suite selection, the guided interview rendered as
  forms (via injected `_ask`/`_progress`), and run progress from streamed stdout.
- Recent-runs view over the run directories under the data home, feeding
  `run_baseline.py import` for baselines and `run_baseline.py session --create` for
  coding sessions — the dashboard ends by opening the created experiment for review,
  not by reimplementing them.

## Risks

- Textual API drift inside the pinned range: the app keeps to the stable widget and
  `work` APIs already used by `scripts/tui.py`; new screens extend, not rewrite.
- A frozen worker thread can strand a started container: every start/stop action
  reports its exit status in the status bar, and the CLI remains the fallback at any
  point.
