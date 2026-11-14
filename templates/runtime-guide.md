# Runtime name

<!-- Copy to docs/runtimes/<runtime>.md. Describe current behavior and remove these instructions. -->

## Build and check

State supported OS/GPU architecture and prerequisites. Link to `runtimes/<runtime>/container/` build inputs, source/dependency locks, and `runtime.json`. Provide build and image-check commands, and explain when a rebuild is required.

## Model preparation

Describe the preparation helper, model lock schema, verification, resumability, retry behavior, and prepared file layout. Recipe setup pages supply runnable commands, model-specific conversion choices, and resource requirements.

## Serving

Describe how `/runtime/scripts/serve.py --recipe /recipe` reads native settings, validates prepared files, and starts the API server. Document engine-specific overrides, GPU selection, file logs, and retention. Link the launcher guide for common mounts and lifecycle behavior.

## Baseline and clients

Describe how the [baseline runner](../baseline.md) uses this server: readiness, request fields (token limit, thinking control), the token-count route, usage and cached-token reporting, and where engine timings come from. Mention any ad hoc check helpers in one line. Describe engine-specific reasoning support. Link to shared Pi setup for installation and metadata alignment; recipe-specific provider configuration belongs in each recipe.

---

[All recipes](../../README.md) · [Launcher](../launcher.md) · [Authoring](../authoring.md)
