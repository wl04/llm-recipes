# Strata implementation

## Image

[`container/versions.lock.json`](container/versions.lock.json) records AMD's ROCm 10.1.0 development image digest and exact Strata and llama.cpp revisions. Source archives are verified with SHA-256 before extraction. Python runtime and build tools use wheel hashes; distribution dependencies use the Ubuntu snapshot dated 2026-11-11.

The engine uses Strata's vendored GGML and HIP kernels compiled for `gfx1201`, with MMQ prefill enabled. The separate CPU vision executable uses llama.cpp's mtmd code at the revision selected by Strata. Portable CPU builds use an AVX2 baseline.

## Serving

[`config/launch.json`](config/launch.json) selects the `strata` API-server adapter and `strata` engine. [`scripts/serve.py`](scripts/serve.py) derives a temporary native configuration from [`config/strata.json`](config/strata.json), validates prepared paths, checks the GPU, and starts `serve.server`.

The native configuration selects IQ3_XXS, automatic expert caching and prefill, INT8 K/V, 32,768 GPU-resident KV cells, and MTP with four draft tokens. CPU vision uses the BF16 multimodal projector. Model files and preparation outputs are external mounts. These settings describe the serving target; workstation measurements are pending.

The launcher mounts model and recipe directories read-only, and cache/log directories writable. Strata receives an unlimited memory-lock allowance, 2 GB shared memory, and a 120-second stop timeout. Its API binds inside the container, with Docker publishing only to host loopback. Offline mode disables external fetches; local API authentication is disabled.

The wrapper relays output to Docker and `server.log`, forwards interrupt/termination signals, and preserves the server exit status. Engine and vision messages share `engine.log`.

## Validation

Repository tests cover adapter selection, native options, missing artifacts, log forwarding, and archive verification. The workstation image check exercises binary startup and a HIP kernel. Model loading, generation, and image requests require prepared model artifacts and subsequent workstation checks.

---

[Recipe](recipe.md) · [Build and check](setup.md) · [Launcher](../../docs/launcher.md)
