# Baseline runner

## Run a baseline

Use the installed command with a recipe ID from `llm-recipes list`:

```bash
llm-recipes-baseline run <recipe>
```

For a container recipe, stop other launcher instances and free the GPU first. The runner starts the server with the recipe defaults and stops it after the run. For a desktop recipe, load the model and start its API server first. The runner prompts for the connection and process details.

Managed runs ask for sudo credentials up front and renew the ticket without prompting while the suite runs. If cleanup cannot use sudo, the runner keeps the measurements and reports the container ID and manual stop command.

Results go to `~/llm-recipes/baselines/<recipe>/<date-time>/` by default. Ctrl+C keeps partial results. Use `llm-recipes-baseline run --help` for options.

To test a candidate worktree, run its script from the worktree root. For all checkout commands below, use Python 3.14 or later with the project dependencies available to `python3`. If you installed them in the repository virtual environment, activate it once with `source .venv/bin/activate`. [Development environment](project-instructions.md#development-dependencies-and-checks)

```bash
python3 scripts/run_baseline.py run <recipe>
```

## What a run measures

The suite checks text, tool calls and vision, then measures sustained coding output, uncached prompts from 8K to 120K tokens where context permits, conversation cache reuse, and a separate reasoning request. Performance cases request thinking off. Use `--request-extra` to override request settings. Coding throughput measures how quickly the model writes a response. Code correctness is unscored.

For comparisons, match the suite version, Python version, model settings and replay tier. The long prompts use the running interpreter’s standard-library source. Suite v3 tests conversation reuse at 64K when possible, then falls back to 32K or a short conversation.

## Reading results

Open `summary.md` for the checks, per-case medians and ranges, and resource use. `results.json` holds the measurements and configuration. The run directory also contains individual requests, resource samples and, for managed runs, server logs.

- **First output** measures time to the first streamed output. **First visible text** shows when the user sees an answer after any reasoning.
- **Decode speed** measures output tokens per second after the first output. **Cached input** shows how much of the prompt the server reports reusing.
- **Memory** is sampled during requests. The RAM column shows system-wide use and the VRAM column shows device use. Brief peaks can fall between samples.

To rebuild a run’s summary from its saved data:

```bash
python3 scripts/run_baseline.py render <run-dir>
```

## Import a baseline run

From the checkout whose recipe and runtime match the run, import the completed run directory:

```bash
python3 scripts/run_baseline.py import <run-dir>
```

This creates the numbered experiment, writes its profile and results, and updates the recipe index. Add `--suffix <slug>` to distinguish a configuration variant. If you edit the profile afterward, run `python3 scripts/generate_configurations.py`. Verify with `bash scripts/check.sh` before committing. [Experiment authoring guide](authoring.md)

## Report a coding session

To summarize a launched instance’s logs, run `python3 scripts/run_baseline.py session <instance>`. To save the session as a recipe experiment, run these commands from the repository root:

```bash
python3 scripts/run_baseline.py session <instance> --create <slug>
python3 scripts/generate_configurations.py
```

Add workload and observations to `summary.md` outside the generated sections. Use `--logs <directory>` to read external logs or `--experiment <folder>` to update an existing experiment. Time filters require timestamped logs.

---

[All recipes](../README.md) · [Authoring](authoring.md) · [Launcher](launcher.md)
