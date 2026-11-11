# llm-recipes project instructions

## Repository structure

- `recipes/<recipe>/` contains a recipe entry page (`recipe.md`) and dated experiment folders with `profile.yaml`, generated `configuration.md`, and authored `summary.md`.
- Container recipes also include `setup.md`, optional `implementation.md`, `config/` (launch manifest, native server settings, model locks), `container/` (image-build inputs and dependency locks), and `scripts/` (model preparation, serving, and measurement helpers).
- `scripts/launch.py` provides the launcher CLI. `scripts/launcher.py` provides recipe discovery, validation, command planning, and process operations shared by interfaces.
- `scripts/generate_configurations.py` generates configuration guides and recipe experiment indexes from `recipes/*/*/profile.yaml`. Its `--check` mode leaves files untouched and exits with code 1 when generated content is outdated.
- `templates/recipe/` contains recipe and experiment templates. `templates/container/` contains optional container setup, implementation, and launch-manifest templates. [Authoring guide](authoring.md) describes how to use them.
- `tests/` contains CPU-only pytest tests that run without Docker, GPUs, or model-weight downloads.

## Launcher conventions

- Discover launchable recipes through `recipes/*/config/launch.json`. The recipe directory name supplies the recipe identifier.
- Keep API-server adapters and inference engines distinct. Supported adapter/engine combinations are `tabbyapi` / `exllamav3` and `strata` / `strata`.
- The launch manifest declares the adapter, engine, image, port, context, drafting, and vision defaults. Native server settings remain in their own configuration file; dated profiles record the settings used for an experiment.
- Keep recipe discovery, validation, and command planning separate from argument parsing and presentation. Process execution returns an exit status so another interface can reuse the same operations.
- Follow the public behavior documented in the [launcher guide](launcher.md), including instance identity, mounts, persistent logs, and process lifecycle.
- Keep client options, defaults, mounts, and operational-script output formats stable unless the task changes their contract. Commit formatting changes separately from behavior changes.

## Development dependencies and checks

Use Python 3.12 or later, as specified in `pyproject.toml`. Install the pinned development dependencies into the repository virtual environment:

```bash
uv venv .venv
uv pip install -p .venv -r dev-requirements.txt
```

Development dependencies are separate from container runtime dependencies in each recipe's `container/requirements.lock`.

Run the same CPU-only checks locally and in CI:

```bash
bash scripts/check.sh
```

The script runs Ruff lint and formatting checks, mypy, pytest, and ShellCheck. The workflow is `.github/workflows/check.yml`. If ShellCheck is unavailable locally, the script skips shell checks with a warning; CI installs it.

`pyproject.toml` defines the exact mypy targets and external-import exceptions. Strict checking covers the generator, launcher modules, selected recipe preparation/serving helpers, and tests.

Check generated documentation separately before committing:

```bash
.venv/bin/python scripts/generate_configurations.py --check
```

After editing profiles or adding results, regenerate and check:

```bash
.venv/bin/python scripts/generate_configurations.py
.venv/bin/python scripts/generate_configurations.py --check
```

Commit profiles and their generated Markdown together. Preserve generated-section markers and keep authored text outside those sections. Update templates and usage instructions when changing recipe structure or authoring conventions.

## Workstation validation

Run GPU/Docker checks only when explicitly invoked on the target workstation: image builds, `check_image.py`, server startup, and generation checks. Follow the recipe's `setup.md`. Report CPU validation separately from GPU behavior verified on the workstation.

---

[All recipes](../README.md) · [Authoring](authoring.md) · [Launcher](launcher.md)
