# Plan: TUI dashboard

A terminal dashboard over the launcher: recipes, instances, logs, and eventually baseline
runs. One installation provides both CLI commands and the interactive dashboard.

## Priority and dependencies

Start with the [installer, launcher, and reporting reliability plan](installer-launcher-and-reporting.md#implementation-order).
Complete its items 1–4 before implementing this plan's installation and command integration
alongside reliability item 5. That work delivers the existing dashboard through `llm-recipes tui`.

Defer the baseline-launcher and recent-runs screens below until the reliability plan is
complete. They are separate feature work, not prerequisites for shipping the installed TUI.

## Constraints

- `python3 scripts/install.py install` installs the serving snapshot and a pinned Textual
  dependency. `llm-recipes tui` opens the dashboard from that snapshot, using the same recipe
  discovery, machine roots, and launcher operations as the CLI.
- Keep Textual imports in the dashboard module; load it when the `tui` subcommand is selected.
  Standard CLI commands do not initialize the UI.
- CI installs the pinned dependency and exercises the dashboard with headless tests.

## Installation and command integration

- [ ] Include Textual in the normal runtime installation and align dependency declarations
      with the development pin. Remove the optional-extra installation contract.
- [ ] Add `llm-recipes tui` dispatch to the existing command, without another executable or
      installation flag. Obtain sudo credentials before entering the interactive screen.
- [ ] Verify the installed command works outside the checkout and uses installed recipes.
      Test command dispatch and a headless dashboard mount with the runtime dependencies.
- [ ] Update the README, launcher guide, project instructions, and applicable templates to
      use the installed command. Keep direct script execution as a development entry point.

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

- Textual API drift when updating the pinned version: the app keeps to the stable widget and
  `work` APIs already used by `scripts/tui.py`; new screens extend, not rewrite.
- A frozen worker thread can strand a started container: every start/stop action
  reports its exit status in the status bar, and the CLI remains the fallback at any
  point.
