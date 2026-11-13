# Runtime name

<!-- Copy to docs/runtimes/<runtime>.md. Describe current behavior and remove these instructions. -->

## Build and check

State supported OS/GPU architecture and prerequisites. Link to `runtimes/<runtime>/container/` build inputs, source/dependency locks, and `runtime.json`. Provide build and image-check commands, and explain when a rebuild is required.

## Model preparation

Document the shared helper's explicit recipe argument, model lock schema, conversion settings, verification, resumability, and external paths. Recipe setup pages supply concrete model identifiers and resource requirements.

## Serving

Describe how `/runtime/scripts/serve.py --recipe /recipe` reads native settings, validates prepared files, and starts the API server. Document supported launch overrides, GPU selection, mounts, logs, and stop behavior.

## Checks and clients

Describe the reusable generation checks and their required model argument. Link to shared Pi installation instructions; recipe-specific provider configuration belongs in each recipe.

---

[All recipes](../../README.md) · [Launcher](../launcher.md) · [Authoring](../authoring.md)
