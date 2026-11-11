# Using the templates

Copy `templates/recipe/` to `recipes/<model-format-hardware-memory>/`. Choose a descriptive lowercase folder name, such as `qwen3.8-27b-gguf-rx-9070-xt-16-gb-vram`.

```text
recipes/<model-format-hardware-memory>/
  recipe.md
  YYYY-MM-DD/
    configuration.md
    summary.md
    profile.yaml
```

1. Set `id` in `profile.yaml` using the naming rule below; the configuration title is generated from it. An overview in `configuration.md` is optional. Keep the generated-section markers in place.
2. Rename `YYYY-MM-DD` to the result date. For multiple configurations on one date, add a suffix such as `2026-11-02-mtp-on`.
3. Fill in `profile.yaml` with the hardware, software, model, and effective settings used for that result. Use `null` for unknown values.
4. Fill in `summary.md` with the workload, statistics, memory measurements, and observations. Keep one date in the title and number sessions #1, #2, and so on. Remove unused sections.
5. Generate the configuration section using the commands below, and regenerate the experiment table in `recipe.md`. Add one root catalog row per recipe, linking to `recipe.md`.

For another result, copy the three files from `templates/recipe/YYYY-MM-DD/` into a new dated result folder. The existing result remains a snapshot of its configuration.

Write a brief current-state description in `recipe.md` and keep its experiment markers. The generator builds its experiment table from dated report titles and links to each configuration and summary. For container recipes, add a prominent setup link and an implementation footer link when available.

## Container recipes

Keep `setup.md` at the recipe level, alongside the dated experiment folders. Put native serving settings and model revision locks in `config/`, image-build inputs in `container/`, and preparation/serving scripts in `scripts/`. Structure `setup.md` as a practical guide: prerequisites, image build, model preparation, launch, client setup, and daily operation (including stopping and reading logs). Lead with the working launch configuration and keep installation checks short. Pin the base image digest, upstream revisions, and build dependencies used by the recipe.

Store model weights and conversion working files outside the repository and mount them into the container. Include the external directory and mount commands in `setup.md`.

Use an optional recipe-level `implementation.md` for current build mechanics, dependency locks, conversion settings, storage mounts, configuration flow, and measurement helpers. Describe the current implementation; keep measured observations in dated `summary.md` files. Link setup and implementation documents to each other in their footers.

Link `setup.md` from `recipe.md` and from the configuration and summary footers.

## Repository checks

From the repository root, create a virtual environment and install the pinned development dependencies:

```bash
uv venv .venv
uv pip install -p .venv -r dev-requirements.txt
```

Run the CPU-only checks (ruff lint and format, mypy, pytest, shellcheck):

```bash
bash scripts/check.sh
```

The same command runs in CI (`.github/workflows/check.yml`). If `shellcheck` is not installed, `check.sh` skips the shell step with a warning. GPU and Docker verification is documented per recipe in `setup.md` and is not part of this check suite.

## Shared launcher

[`scripts/launch.py`](../scripts/launch.py) provides `list`, `start`, `ps`, `status`, `logs`, and `stop` commands for discovered container recipes. Run `python3 scripts/launch.py start <recipe> --help` for launch options. It uses the host Python 3 standard library and `sudo docker`.

Native engine configuration stays in the recipe. The launcher owns Docker lifecycle and host mounts; the recipe entry point validates native settings and starts its server. Launchable recipes contain `config/launch.json`; the parent recipe directory supplies the recipe identifier. The manifest declares `adapter`, `engine`, `image`, `port`, `context`, `draft`, and `vision`. All fields are required and checked. The current supported combination is `tabbyapi` / `exllamav3`; copy the existing manifest for another prepared recipe using that combination. Native server settings remain in their own configuration file. Result profiles remain dated observations.

`start <recipe> --name <instance>` chooses a recipe and an optional instance name. The default instance name is the recipe directory name. `status`, `logs`, and `stop` take instance names; `ps` lists running instances through Docker labels. Logs default to `$XDG_STATE_HOME/llm-recipes/<instance>` (or `~/.local/state/llm-recipes/<instance>`). Distinct instances need distinct names and available host ports; use `--port` to select a port. Names use lowercase letters, digits, dots, dashes, and underscores and start with a letter or digit.

Implement a serving adapter before registering a new API server. Desktop recipes use their application's launch flow.

Changes to the launcher can be checked without a GPU:

```bash
bash scripts/check.sh
```

## Generate configuration guides

Shared experiment templates live in `templates/recipe/`. The [generator](../scripts/generate_configurations.py) turns their completed profiles into configuration guides and updates recipe experiment tables.

Generate the guides, then check that they are current:

```bash
.venv/bin/python scripts/generate_configurations.py
.venv/bin/python scripts/generate_configurations.py --check
```

Edit the result profiles to change configuration details. The generator renders each result's `profile.yaml` into the marked section of the `configuration.md` in the same folder. Each result has its own guide and report. Text outside the markers stays editable. YAML key order controls table order. Store explanatory notes as YAML values; YAML comments are not rendered.

Run generation after editing a profile or adding a result. Commit the YAML and generated Markdown together. `--check` exits unsuccessfully when the generated section needs updating and leaves files untouched.

On Windows, use `.venv\Scripts\python.exe` in place of `.venv/bin/python`.

## Display labels

Each profile has a `labels` mapping for readable field names and section headings. Keys are dotted YAML paths, for example `hardware.memory.dedicated_vram_gib: Dedicated VRAM (GB)`. Labels affect the generated guide; values stay in their existing fields.

When adding a setting, add its label too, for example `settings.Context length: Context length (tokens)`. The generator reports missing labels instead of displaying internal field paths. Keep units in labels where useful. The labels mapping itself is omitted from the generated guide.

The profile identifier supplies the generated document title. Both Markdown documents end with links to their companions: configuration guides link to Recipe, Results, and Profile YAML; summaries link to Recipe, Configuration, and Profile YAML. When a recipe has `setup.md`, use these footers:

- Configuration: `[Recipe](../recipe.md) · [Results](summary.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml)`
- Summary: `[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml)`

The generator adds the Build and run link automatically when `setup.md` exists in the recipe folder. Update the authored summary footer to match. Recipes without `setup.md` link to Recipe and their two companion files. The configuration footer is generated. Record speculative decoding under `settings` alongside the other inference settings.

## Recipe identity and folder name

Use four parts in `id`, separated by ` / `:

```yaml
id: Qwen3.8-27B / GGUF / RX 9070 XT / 16 GB VRAM
```

The parts are model family and size, model format, graphics adapter or laptop/chip name, and memory capacity/type. Use `VRAM` for dedicated graphics memory and `unified memory` for shared CPU/GPU memory. Keep quantization and harness versions in their fields so results can compare those settings.

The folder name is derived by lowercasing the parts, replacing runs of characters other than letters, digits, periods, and hyphens with a hyphen, trimming outer hyphens from each part, and joining the parts with hyphens. The example becomes `qwen3.8-27b-gguf-rx-9070-xt-16-gb-vram`.

All results in a recipe use the same `id`. The generator checks the folder name and identifiers before writing. Different hardware or memory capacities belong in separate recipe folders.

Use GB for hardware capacities in captions and display labels. YAML `_gib` keys retain binary capacity values; GB is the hardware display convention, not a numeric conversion. Keep the units reported by measurement tools, such as MiB, in result statistics.

The generated guide omits null values, blank strings, empty lists/mappings, and sections containing only empty values. Numeric zero and boolean false remain visible.
