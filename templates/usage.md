# Using the templates

Copy `templates/recipe/` to `recipes/<model-harness>/`. Choose a descriptive lowercase folder name, such as `qwen3.8-27b-lmstudio-gguf`.

```text
recipes/<model-harness>/
  configuration.md
  results/
    YYYY-MM-DD/
      summary.md
      profile.yaml
```

1. Fill in `configuration.md` with a short overview. Keep the generated-section markers in place.
2. Rename `YYYY-MM-DD` to the result date. For multiple configurations on one date, add a suffix such as `2026-11-02-mtp-on`.
3. Fill in `profile.yaml` with the hardware, software, model, and effective settings used for that result. Use `null` for unknown values.
4. Fill in `summary.md` with the workload, statistics, memory measurements, and observations. Keep one date in the title and number sessions #1, #2, and so on. Remove unused sections.
5. Generate the configuration section using the commands below, and add the recipe to the root catalog.

For another result, copy the two files from `templates/recipe/results/YYYY-MM-DD/` into a new dated result folder. The existing result remains a snapshot of its configuration.

## Generate configuration guides

From the repository root, create a Python 3 virtual environment and install the pinned dependency:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements.txt
```

Generate the guides, then check that they are current:

```bash
.venv/bin/python scripts/generate_configurations.py
.venv/bin/python scripts/generate_configurations.py --check
```

Edit the result profiles to change configuration details. The generator renders every result profile in reverse folder-name order into the marked section of each recipe's `configuration.md`. Text outside the markers stays editable. YAML key order controls table order. Store explanatory notes as YAML values; YAML comments are not rendered.

Run generation after editing a profile or adding a result. Commit the YAML and generated Markdown together. `--check` exits unsuccessfully when the generated section needs updating and leaves files untouched.

On Windows, use `.venv\Scripts\python.exe` in place of `.venv/bin/python`. The [generator](../scripts/generate_configurations.py) and its [dependency file](../scripts/requirements.txt) are included in the repository.

## Display labels

Each profile has a `labels` mapping for readable field names and section headings. Keys are dotted YAML paths, for example `hardware.memory.dedicated_vram_gib: Dedicated VRAM (GiB)`. Labels affect the generated guide; values stay in their existing fields.

When adding a setting, add its label too, for example `settings.Context length: Context length (tokens)`. The generator reports missing labels instead of displaying internal field paths. Keep units in labels where useful. The labels mapping itself is omitted from the generated guide.
