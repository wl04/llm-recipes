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
3. Fill in `profile.yaml` with the hardware, software, model, and effective settings used for that result, following the [profile structure](#experiment-profile). Use `null` for unknown values. Record the client in `software.harness`, the API server in `software.server`, and the inference engine in `software.engine`, with their versions or revisions.
4. Fill in `summary.md` with the workload, statistics, memory measurements, and observations. The generator owns the title line: it writes `# NNN · YYYY-MM-DD — Description` from the folder name, or from the `title` key in `profile.yaml` when you need different wording. Within the report, number sessions #1, #2, and so on. Remove unused sections.
5. Generate the configuration section using the commands below, and regenerate the experiment table in `recipe.md`. Add one root catalog row per recipe, linking to `recipe.md`.

For another result, copy the three files from `templates/recipe/NNN-YYYY-MM-DD-description/` into a new numbered result folder. The existing result remains a snapshot of its configuration.

A baseline experiment holds the output of the baseline runner instead of a hand-written statistics report. Name it `NNN-YYYY-MM-DD-baseline`, adding a suffix when its configuration differs from the recipe default. Copy `templates/recipe/baseline-summary.md` to `summary.md`, place the run's `results.json` beside it, and fill in `profile.yaml`. The generator writes the title from the folder name (or the profile `title` key) and renders `results.json` into the marked results block, so the report contains no hand-written prose; anything you add outside the markers is kept. `--check` fails when `results.json` or the title has changed but has not been regenerated. See the [baseline contract](baseline.md) for the result format.

A session experiment reports a real coding session against a launched instance instead of a hand-counted console log. Create the numbered folder with `summary.md` and `configuration.md` from the template, then run `python3 scripts/run_baseline.py session <instance> --experiment recipes/<recipe>/<NNN-...>`: it aggregates the instance's engine logs into `session-results.json`, writes the generated activity block into `summary.md`, and seeds `profile.yaml` from the instance `facts.json` and the sampler lines the engine echoed to its log. Keep only the narrative outside the markers. Strata logs carry no timestamps, so window filtering and the wall-clock span apply to TabbyAPI file logs; the report shows everything else as `unavailable`. See the [session report](baseline.md#report-a-coding-session).

Write a brief current-state description in `recipe.md` and keep its experiment markers. The generator builds its experiment table from report titles, ordered by folder number descending, and links to each configuration and summary. For container recipes, add a prominent setup link and a footer link to the shared runtime guide.

For example, three experiments in one recipe can be:

```text
001-2026-11-14-baseline/
002-2026-11-15-baseline-draft-off/
003-2026-11-16-coding-medium/
```

Folders sort by sequence in GitHub and file browsers; the recipe index shows the highest number first. The suffix identifies the workload or configuration variant. Keep changing status such as “current” out of folder names.

## Experiment profile

`profile.yaml` is the single source of truth for `configuration.md`, which is generated output between markers; edit the profile, never the generated block. Structure:

| Section | Content |
|---|---|
| `id` | Model / format / hardware / memory identity; must re-slug to the recipe folder name. |
| `hardware`, `os` | Measured host facts (CPU, RAM, GPU, driver). |
| `software` | Harness, engine, server, image pins, revisions. |
| `model` | Identity and quantization from the recipe locks. |
| `settings.serving` | Context, cache, drafting, vision — what the server was set to. |
| `settings.sampling` | `mode` preset name and/or explicit sampler parameters. |
| `settings.thinking` | Whether and how thinking was enabled. |
| `settings.requests` | Endpoint, streaming, output caps, concurrency. |
| `settings.notes` | The only free-text field; rendered last as "Experiment notes". |

Keys inside the `sampling`, `thinking`, and `requests` groups come from fixed whitelists — an unknown key is a generation error, so extend the generator's registry in a code change when the domain grows. Values already recorded by `results.json` (baseline sampling policy) must not be duplicated in the profile; the generator renders them from the run. A baseline experiment's whole profile comes from `run_baseline.py import`; a session experiment's from `run_baseline.py session` — hand-editing is then a deliberate correction, not the normal path.

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

A runtime owns the image reference, API-server/engine pairing, build locks, and reusable scripts. A recipe selects the runtime and supplies model artifacts, preparation settings, native serving configuration, and client metadata. Keep weights and conversion working files outside Git. Each recipe's model data lives under `<data home>/recipes/<recipe-id>/`, derived from the recipe folder name. Strata preparation writes its shards, packs, and MTP there; ExLlamaV3 model locks define the target, draft, and conversion folders inside it. Native serving paths must agree with the prepared paths.

Keep `setup.md` focused on model-specific capacity, preparation and launch commands, readiness, the baseline command, and a link to its Pi configuration. Runtime guides own build instructions, preparation/retry behavior, engine-specific capabilities, and file logs. The launcher guide owns common mounts and lifecycle controls; the Pi guide owns installation and client metadata alignment. Keep runnable commands in each recipe; link shared explanations. Shared scripts take `--recipe` explicitly. Each API check accepts a model identifier; avoid model-specific defaults in shared code.

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
```

The optional `labels` mapping overrides the built-in label for one path; see [Display labels](#display-labels).

Docker Hub tag links display as `repository:tag`. Tags can move; the full digest identifies the image used. Tag pages provide image metadata, while the profile and build lock retain the recorded digest. These fields apply to container recipes.

## Display labels

The generator owns a built-in label registry for every canonical profile path, so a profile needs no `labels` mapping for standard fields. The section headings are `Serving`, `Sampling`, `Thinking`, `Requests`, and `Experiment notes`. Add an optional `labels` mapping only to override one path for that experiment, for example `labels: {requests.max_output_tokens: Response length limit}`; keys are dotted paths within `settings`. Unknown dotted paths render from their key and are reported when generating, so extend the generator's registry in a code change when a new standard field appears. Keep units in labels where useful. The labels mapping itself is omitted from the generated guide.

The profile identifier supplies the generated document title. Both Markdown documents end with links to their companions: configuration guides link to Recipe, Results, and Profile YAML; summaries link to Recipe, Configuration, and Profile YAML. When a recipe has `setup.md`, use these footers:

- Configuration: `[Recipe](../recipe.md) · [Results](summary.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml)`
- Summary: `[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml)`

The generator adds the Build and run link automatically when `setup.md` exists in the recipe folder. Update the authored summary footer to match. Recipes without `setup.md` link to Recipe and their two companion files. The configuration footer is generated. Record speculative decoding under `settings.serving` alongside the other serving rows.

## Recipe identity and folder name

Use four parts in `id`, separated by ` / `:

```yaml
id: Qwen3.8-27B / GGUF / RX 9070 XT / 16 GB VRAM
```

The parts are model family and size, model format, graphics adapter or laptop/chip name, and memory capacity/type. Use `VRAM` for dedicated graphics memory and `unified memory` for shared CPU/GPU memory. Keep quantization and harness versions in their fields. For independently maintained quantizations, qualify the format part with provider and quantization, for example `GGUF ISTA IQ3_XXS` or `GGUF Unsloth UD-IQ3_XXS`, to give each recipe a distinct identity.

The folder name is derived by lowercasing the parts, replacing runs of characters other than letters, digits, periods, and hyphens with a hyphen, trimming outer hyphens from each part, and joining the parts with hyphens. The example becomes `qwen3.8-27b-gguf-rx-9070-xt-16-gb-vram`.

All results in a recipe use the same `id`. The generator checks the folder name and identifiers before writing. Different hardware or memory capacities belong in separate recipe folders. Different model families or independently maintained quantizations also receive separate recipes; sampling, context, and vision changes normally remain experiments.

Measured capacities use binary units: GiB and MiB in display labels and result statistics, matching the `_gib` keys and the `unit` fields in `results.json`. Use decimal GB only for vendor capacities in identifiers and product prose, such as `16 GB VRAM` in `id`; a deliberately decimal measurement stays explicitly labeled, such as `GB (decimal)`. Disk and memory requirements in setup guides are measurements too: state them in GiB and derive the figures from the byte sizes in `config/models.lock.json` or the prepare script's output, never from marketplace or file-manager displays.

The generated guide omits null values, blank strings, empty lists/mappings, and sections containing only empty values. Numeric zero and boolean false remain visible.


---

[All recipes](../README.md) · [Launcher](launcher.md) · [Development](project-instructions.md)
