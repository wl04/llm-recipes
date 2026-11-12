# Implementation

<!-- Describe the current implementation and remove authoring comments. -->

## Image and dependencies

Identify the image-build inputs, base image tag and digest, upstream revisions, and dependency locks. Link verified matching releases and image tags using the [profile reference conventions](../../docs/authoring.md#releases-and-container-image-tags). Describe the build command and architecture selection.

## Model preparation

Identify the model lock and conversion settings. List the expected prepared model directories and how preparation is validated before serving.

## Serving and storage

Identify the API-server adapter and inference engine selected by `config/launch.json`. Link to the [launcher guide](../../docs/launcher.md) for common lifecycle behavior.

Document the recipe's serving entry point, native configuration file, GPU selection, host/container paths, and read-only or writable mounts. Describe server-specific logging and runtime caches.

## Measurement helpers

List the recipe's generation and workload commands, what they measure, and how to record results in dated experiment folders.

---

[Recipe](recipe.md) · [Setup](setup.md)
