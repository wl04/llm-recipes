# llm-recipes project instructions

## Repository structure

- `recipes/<recipe>/` contains a recipe entry page (`recipe.md`) and numbered experiment folders (`NNN-YYYY-MM-DD-description`) with `profile.yaml`, generated `configuration.md`, authored `summary.md`, and imported run data where present: `results.json` for a baseline experiment, `session-results.json` for a coding session.
- Container recipes include `setup.md` and `config/` (runtime selection, native settings, model locks, Pi metadata). Shared `runtimes/<runtime>/` directories own `runtime.json`, `container/` build inputs, and `scripts/` for preparation, serving, and checks. Runtime guides live under `docs/runtimes/`, client setup under `docs/clients/`, and the terminal-dashboard plan under `docs/plans/`.
- `scripts/launch.py` provides the launcher CLI and `scripts/tui.py` the optional terminal dashboard, which runs from the checkout with the pinned `textual` development dependency ([dashboard plan](plans/tui-dashboard.md)). `scripts/launcher.py` provides recipe discovery, validation, command planning, and process operations shared by interfaces; it writes each instance's `facts.json` from deterministic host facts (`scripts/host_facts.py`). `scripts/paths.py` defines the machine roots and `scripts/install.py` installs the serving snapshot and migrates the data root (see [machine roots](#machine-roots-and-cutover)).
- `scripts/doctor.py` provides read-only host/configuration/preparation diagnostics for `launch.py doctor`. Docker inspection is bounded and noninteractive; diagnostics must not launch containers or mutate model files.
- `scripts/baseline/` provides the baseline runner's result contract (`schema.py`), OpenAI-compatible request and stream handling (`api.py`), client statistics (`stats.py`), vision-check scoring (`vision.py`), results and coding-session rendering (`report.py`, `session.py`), and engine request-log parsing (`engine_log.py`). It also provides telemetry readers (`sources.py`, `monitor.py`), sampling (`sampler.py`), the run record and aggregation (`rawlog.py`, `aggregate.py`), the workload suite (`workloads.py`, `functional.py`), host preflight (`host.py`), the container lifecycle (`lifecycle.py`) and settle detection (`phases.py`), the runner (`runner.py`), run import into experiment folders (`importer.py`), prompt-driven recipe setup (`guided.py`), and the command line (`cli.py`, started with `scripts/run_baseline.py`). See the [baseline contract](baseline.md).
- `scripts/generate_configurations.py` generates configuration guides and recipe experiment indexes from `recipes/*/*/profile.yaml`. Its `--check` mode leaves files untouched and exits with code 1 when generated content is outdated. It also renders an experiment's optional `results.json` into the marked results block of its `summary.md`.
- `templates/recipe/` contains recipe and experiment templates. `templates/container/` contains container recipe setup and launch-manifest templates; `templates/runtime/` and `templates/runtime-guide.md` describe shared runtimes. [Authoring guide](authoring.md) describes how to use them.
- `tests/` contains CPU-only pytest tests that run without Docker, GPUs, or model-weight downloads.

## Launcher conventions

- Discover launchable recipes through `recipes/*/config/launch.json`. The recipe directory name supplies the recipe identifier.
- Keep API-server adapters and inference engines distinct. Supported adapter/engine combinations are `tabbyapi` / `exllamav3` and `strata` / `strata`.
- The launch manifest selects the runtime, port, context, drafting, and vision defaults; each recipe's model data folder is `recipes/<recipe-id>/` under the data root, derived from the recipe directory name. The runtime descriptor declares the adapter, engine, and image. Native server settings remain in their own configuration file; dated profiles record the settings used for an experiment.
- Keep recipe discovery, validation, and command planning separate from argument parsing and presentation. Process execution returns an exit status so another interface can reuse the same operations.
- Follow the public behavior documented in the [launcher guide](launcher.md), including instance identity, mounts, persistent logs, and process lifecycle.
- Keep client options, defaults, mounts, and operational-script output formats stable unless the task changes their contract. Commit formatting changes separately from behavior changes.

## Development dependencies and checks

Use Python 3.12 or later, as specified in `pyproject.toml`. Install the pinned development dependencies into the repository virtual environment:

```bash
uv venv .venv
uv pip install -p .venv -r dev-requirements.txt
```

Development dependencies are separate from container runtime dependencies in `runtimes/<runtime>/container/requirements.lock`.

Run the same CPU-only checks locally and in CI:

```bash
bash scripts/check.sh
```

The script runs Ruff lint and formatting checks, mypy, pytest, generated-document checks, and ShellCheck. The workflow is `.github/workflows/check.yml`. If ShellCheck is unavailable locally, the script skips shell checks with a warning; CI installs it.

`pyproject.toml` defines the exact mypy targets and external-import exceptions. Strict checking covers the generator, launcher modules, the ExLlamaV3 runtime helpers, and tests. The two runtimes carry same-named helper modules that import siblings by name, so `check.sh` checks `runtimes/strata` in its own mypy invocation; run `bash scripts/check.sh` rather than a bare `mypy` to cover both.

After editing profiles or adding results, follow [generation instructions](authoring.md#generate-configuration-guides) and commit profiles with generated Markdown. Preserve generated-section markers. Update templates and the authoring guide when changing structure or conventions.

## Machine roots and cutover

Serving runs from the installed snapshot `~/.llm-recipes/app` (`LLM_RECIPES_RUNTIME` prefix; its own venv and `llm-recipes` / `llm-recipes-baseline` shims symlinked into `~/.local/bin`), never from the development checkout; `python3 scripts/install.py install` refreshes it. Keep `~/.local/bin` on `PATH` so the shims resolve. The data root is `~/llm-recipes` (`LLM_RECIPES_HOME`): `recipes/<recipe-id>/` model data, `.cache/`, `baselines/`, `logs/<instance>/` with each instance's `facts.json`.

The cutover runs once per machine: stop all instances from a system terminal, run `python3 scripts/install.py migrate-data` (dry run), then the same command with `--apply`, and start instances again via `llm-recipes`. Never run the cutover from a coding agent — the model backend serving the current session is among the data it moves.

## Workstation validation

Run GPU/Docker checks only when explicitly invoked on the target workstation: image builds, `check_image.py`, server startup, and generation checks. Follow the recipe's `setup.md`. Report CPU validation separately from GPU behavior verified on the workstation.

---

[All recipes](../README.md) · [Authoring](authoring.md) · [Launcher](launcher.md)
