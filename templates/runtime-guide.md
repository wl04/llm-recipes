# Runtime name

<!-- Copy to docs/runtimes/<runtime>.md. Describe current behavior and remove these instructions. -->

## Build and check

State supported OS/GPU architecture and prerequisites. Link to `runtimes/<runtime>/container/` build inputs, source/dependency locks, and `runtime.json`. For a runtime with per-recipe release pins, put the concrete `python3 scripts/build_runtime.py <runtime> --recipe <recipe-id> --check` command in each recipe setup page. Otherwise use `python3 scripts/build_runtime.py <runtime> --check`. Set the descriptor’s image tag to the pinned source release (or nearest release, commit count and Git SHA). Include the API server revision when pinned separately. Use a distinct tag when comparing builds of the same sources, such as a ROCm or patch variant.

For runtimes supported by the shared upgrader, link to [upgrade a container runtime](../launcher.md#upgrade-a-container-runtime).

## Model preparation

Describe the preparation helper, model lock schema, verification, resumability, retry behavior, and prepared file layout. Recipe setup pages supply runnable commands, model-specific conversion choices, and resource requirements.

## Serving

Describe how `/runtime/scripts/serve.py --recipe /recipes/<recipe-id>` reads native settings, validates prepared files, and starts the API server. Document engine-specific overrides, GPU selection, file logs, and retention. Link the launcher guide for common mounts and lifecycle behavior.

## Baseline and clients

Link to the [baseline guide](../baseline.md) and shared Pi setup where needed. Document engine-specific steps here only when the shared guides do not cover them. Put runnable baseline commands and Pi provider details in the recipe setup.

---

[All recipes](../../README.md) · [Launcher](../launcher.md) · [Authoring](../authoring.md)
