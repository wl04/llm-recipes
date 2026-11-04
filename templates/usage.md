# Using the templates

Copy `templates/recipe/` to `recipes/<model-format-hardware-memory>/`. Choose a descriptive lowercase folder name, such as `qwen3.8-27b-gguf-rx-9070-xt-16-gb-vram`.

```text
recipes/<model-format-hardware-memory>/
  YYYY-MM-DD/
    configuration.md
    summary.md
    profile.yaml
```

1. Set `id` in `profile.yaml` using the naming rule below; the configuration title is generated from it. An overview in `configuration.md` is optional. Keep the generated-section markers in place.
2. Rename `YYYY-MM-DD` to the result date. For multiple configurations on one date, add a suffix such as `2026-11-02-mtp-on`.
3. Fill in `profile.yaml` with the hardware, software, model, and effective settings used for that result. Use `null` for unknown values.
4. Fill in `summary.md` with the workload, statistics, memory measurements, and observations. Keep one date in the title and number sessions #1, #2, and so on. Remove unused sections.
5. Generate the configuration section using the commands below, and add links to this result’s configuration and summary to the root catalog.

For another result, copy the three files from `templates/recipe/YYYY-MM-DD/` into a new dated result folder. The existing result remains a snapshot of its configuration.

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

Edit the result profiles to change configuration details. The generator renders each result's `profile.yaml` into the marked section of the `configuration.md` in the same folder. Each result has its own guide and report. Text outside the markers stays editable. YAML key order controls table order. Store explanatory notes as YAML values; YAML comments are not rendered.

Run generation after editing a profile or adding a result. Commit the YAML and generated Markdown together. `--check` exits unsuccessfully when the generated section needs updating and leaves files untouched.

On Windows, use `.venv\Scripts\python.exe` in place of `.venv/bin/python`. The [generator](../scripts/generate_configurations.py) and its [dependency file](../scripts/requirements.txt) are included in the repository.

## Display labels

Each profile has a `labels` mapping for readable field names and section headings. Keys are dotted YAML paths, for example `hardware.memory.dedicated_vram_gib: Dedicated VRAM (GB)`. Labels affect the generated guide; values stay in their existing fields.

When adding a setting, add its label too, for example `settings.Context length: Context length (tokens)`. The generator reports missing labels instead of displaying internal field paths. Keep units in labels where useful. The labels mapping itself is omitted from the generated guide.

The profile identifier supplies the generated document title. Generated guides show a prominent results link above each configuration and small profile links at the bottom. The results link uses the report title without its date prefix. Record speculative decoding under `settings` alongside the other inference settings.

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
