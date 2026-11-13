# Adding recipes and results

Copy `templates/recipe/` to `recipes/<model-format-hardware-memory>/`. Choose a descriptive lowercase folder name, such as `qwen3.8-27b-gguf-rx-9070-xt-16-gb-vram`.

```text
recipes/<model-format-hardware-memory>/
  recipe.md
  NNN-YYYY-MM-DD-description/
    configuration.md
    summary.md
    profile.yaml
```

1. Set `id` in `profile.yaml` using the naming rule below; the configuration title is generated from it. An overview in `configuration.md` is optional. Keep the generated-section markers in place.
2. Name the experiment folder `NNN-YYYY-MM-DD-description`: a three-digit sequence within the recipe, result date, and lowercase hyphen-separated workload or variant. Start at `001` and assign the next number for each new experiment, including those on the same day. Continue numbering across dates and keep assigned numbers fixed.
3. Fill in `profile.yaml` with the hardware, software, model, and effective settings used for that result. Use `null` for unknown values. Record the client in `software.harness`, the API server in `software.server`, and the inference engine in `software.engine`, with their versions or revisions.
4. Fill in `summary.md` with the workload, statistics, memory measurements, and observations. Use the title `# NNN · YYYY-MM-DD — Workload / variant`, matching the folder number and date. Within the report, number sessions #1, #2, and so on. Remove unused sections.
5. Generate the configuration section using the commands below, and regenerate the experiment table in `recipe.md`. Add one root catalog row per recipe, linking to `recipe.md`.

For another result, copy the three files from `templates/recipe/NNN-YYYY-MM-DD-description/` into a new numbered result folder. The existing result remains a snapshot of its configuration.

Write a brief current-state description in `recipe.md` and keep its experiment markers. The generator builds its experiment table from report titles, ordered by folder number descending, and links to each configuration and summary. For container recipes, add a prominent setup link and a footer link to the shared runtime guide.

For example, three experiments in one recipe can be:

```text
001-2026-11-12-initial-checks/
002-2026-11-12-vision-1024/
003-2026-11-12-coding-medium/
```

Folders sort by sequence in GitHub and file browsers; the recipe index shows the highest number first. The suffix identifies the workload or configuration variant. Keep changing status such as “current” out of folder names.

## Container recipes

Copy `templates/container/` into the recipe alongside the base template. Select an existing shared runtime in `config/launch.json` and provide model locks, native server settings, and Pi metadata.

```text
recipes/<model-format-hardware-memory>/
  recipe.md
  setup.md
  config/
    launch.json
    models.lock.json
    <native-server-config>
    pi.models.json
  NNN-YYYY-MM-DD-description/
    profile.yaml
    configuration.md
    summary.md

runtimes/<runtime>/
  runtime.json
  container/
  scripts/

docs/runtimes/<runtime>.md
```

A runtime owns the image reference, API-server/engine pairing, build locks, and reusable scripts. A recipe selects the runtime and supplies model artifacts, preparation settings, native serving configuration, client metadata, and external data-directory names. Keep weights and conversion working files outside Git. Strata preparation uses the recipe's `data_directory`; ExLlamaV3 model locks define the target, draft, and work folders below that directory. Native serving paths must agree with the prepared paths.

Keep `setup.md` focused on model-specific capacity, preparation and launch commands, readiness, checks, and a link to its Pi configuration. Runtime guides own build instructions, preparation/retry behavior, engine-specific capabilities, and file logs. The launcher guide owns common mounts and lifecycle controls; the Pi guide owns installation and client metadata alignment. Keep runnable commands in each recipe; link shared explanations. Shared scripts take `--recipe` explicitly. Each API check accepts a model identifier; avoid model-specific defaults in shared code.

For a new runtime, use `templates/runtime/` for its descriptor and `templates/runtime-guide.md` for its guide. Pin the base image digest, source revisions, and build dependencies. Keep engine-specific preparation and native settings in that runtime's integration. Follow [launcher conventions](launcher.md#shared-runtimes).

Link `setup.md` from `recipe.md` and from configuration and summary footers. Record exact engine/server revisions and image identity in each measured profile. A shared runtime update must not rewrite historical version fields. Repository commits preserve earlier build inputs; profiles retain the identities used for those results.

## Shared guides

Use the [launcher guide](launcher.md) for container commands, instance naming, and launch-manifest fields. Follow [Pi setup](clients/pi.md) for client installation and the recipe's setup page for its provider configuration.

Install the pinned development dependencies using [development setup](project-instructions.md#development-dependencies-and-checks) before running the generator. Run the repository checks described there after changing code or templates.

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

## Revision links

Use full commit URLs for source revisions in profiles, for example:

```yaml
software:
  revision: https://github.com/Niko1221/Strata/commit/dbb2d168cffa8cf793d9325358809d5263c7c6b0
model:
  revision: https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/commit/ed59f92082b1e93c0e96d60a8b11aab089b52f09
```

Add the corresponding display labels, such as `software.revision: Strata revision` and `model.revision: Model revision`. The generator renders HTTP(S) values as clickable links and displays commit URLs using the first eight characters of the hash. The link retains the complete revision. Release version strings remain plain text. Build and model lock files retain the raw revisions consumed by preparation scripts.

### Releases and container image tags

When an upstream release tag points to the recorded commit, store its release URL in the version field and keep the commit URL separately. For annotated tags, compare the peeled commit (`refs/tags/<tag>^{}`). Verify the release page exists. For example, ExLlamaV3's recorded commit matches `v1.6.6`:

```yaml
software:
  engine_version: https://github.com/turboderp-org/exllamav3/releases/tag/v1.6.6
  engine_version_note: https://github.com/turboderp-org/exllamav3/commit/bd1f519172406a9560bd5c90e61000691bb69a07
```

The generator displays the release tag as link text. A version reported by the application remains a version string until an exact release match is verified. Record links during profile preparation; generation works offline.

For container profiles, record the tag used at preparation alongside the pinned image reference:

```yaml
software:
  base_image_tag: https://hub.docker.com/r/rocm/dev-ubuntu-24.04/tags?name=10.1.0-full
  base_image: rocm/dev-ubuntu-24.04@sha256:5ed1362ea542a928651e4c710b44024ebe98870f74159cb70f0265aec8ef0abe
labels:
  software.base_image_tag: Base image tag at preparation
  software.base_image: Pinned base image
```

Docker Hub tag links display as `repository:tag`. Tags can move; the full digest identifies the image used. Tag pages provide image metadata, while the profile and build lock retain the recorded digest. These fields apply to container recipes.

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

The parts are model family and size, model format, graphics adapter or laptop/chip name, and memory capacity/type. Use `VRAM` for dedicated graphics memory and `unified memory` for shared CPU/GPU memory. Keep quantization and harness versions in their fields. For independently maintained quantizations, qualify the format part with provider and quantization, for example `GGUF ISTA IQ3_XXS` or `GGUF Unsloth UD-IQ3_XXS`, to give each recipe a distinct identity.

The folder name is derived by lowercasing the parts, replacing runs of characters other than letters, digits, periods, and hyphens with a hyphen, trimming outer hyphens from each part, and joining the parts with hyphens. The example becomes `qwen3.8-27b-gguf-rx-9070-xt-16-gb-vram`.

All results in a recipe use the same `id`. The generator checks the folder name and identifiers before writing. Different hardware or memory capacities belong in separate recipe folders. Different model families or independently maintained quantizations also receive separate recipes; sampling, context, and vision changes normally remain experiments.

Use GB for hardware capacities in captions and display labels. YAML `_gib` keys retain binary capacity values; GB is the hardware display convention, not a numeric conversion. Keep the units reported by measurement tools, such as MiB, in result statistics.

The generated guide omits null values, blank strings, empty lists/mappings, and sections containing only empty values. Numeric zero and boolean false remain visible.


---

[All recipes](../README.md) · [Launcher](launcher.md) · [Development](project-instructions.md)
