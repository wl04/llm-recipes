# Implementation

<!-- Describe the current implementation and remove authoring comments. -->

## Image and dependencies

Identify the image-build inputs, base image digest, upstream revisions, and dependency locks. Describe the build command and architecture selection.

## Model preparation

Identify the model lock and conversion settings. List the expected prepared model directories and how preparation is validated before serving.

## Serving and storage

`config/launch.json` identifies the API-server adapter, inference engine, image, and launch defaults. The recipe directory supplies its identifier. The shared launcher discovers these manifests, validates options, and manages named Docker instances. Native server configuration stays in `config/`.

Document the serving entry point, native configuration file, GPU selection, host/container paths, and read-only or writable mounts. Describe persistent logs and runtime caches.

`scripts/launcher.py` in the repository root provides discovery, command planning, and process operations. `scripts/launch.py` provides the CLI. Instances carry Docker labels recording the recipe, API-server adapter, engine, and instance name.

## Measurement helpers

List the recipe's generation and workload commands, what they measure, and how to record results in dated experiment folders.

---

[Recipe](recipe.md) · [Setup](setup.md)
