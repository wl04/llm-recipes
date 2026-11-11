# Strata implementation

## Image

[`container/versions.lock.json`](container/versions.lock.json) records AMD's ROCm 10.1.0 development image digest and exact Strata and llama.cpp revisions. Source archives are verified with SHA-256 before extraction. Python runtime and build tools use wheel hashes; distribution dependencies use the Ubuntu snapshot dated 2026-11-11.

The engine uses Strata's vendored GGML and HIP kernels compiled for `gfx1201`, with MMQ prefill enabled. The separate CPU vision executable uses llama.cpp's mtmd code at the revision selected by Strata. Portable CPU builds use an AVX2 baseline.

## Model preparation

[`config/models.lock.json`](config/models.lock.json) pins the ISTA-DASLab model shards and BF16 projector by revision, byte size, and SHA-256, using the metadata shipped in the pinned Strata source. MTP uses the original Qwen checkpoint revision and per-tensor hashes enforced by that source's `mtp_fetch.py`.

[`scripts/prepare_models.py`](scripts/prepare_models.py) runs inside the prepared image with a writable external model mount and the host user's UID. It calls upstream `iq_pack.py`, `mtp_fetch.py`, `mtp_pack.py`, and `mtp_rt.py`; the target experts retain their native IQ3_XXS representation, and MTP experts are converted to Q2_0. The default `draft_vocab.bin` is copied from the pinned source.

Downloads use partial files and verify full hashes before publication. A filesystem lock prevents simultaneous preparation commands. Serving requires a completion record matching the model and image locks. Preparation runs while the serving instance is stopped.

## Serving

[`config/launch.json`](config/launch.json) selects the `strata` API-server adapter and `strata` engine. [`scripts/serve.py`](scripts/serve.py) derives a temporary native configuration from [`config/strata.json`](config/strata.json), validates prepared paths, checks the GPU, and starts `serve.server`.

The native configuration selects IQ3_XXS, automatic expert caching and prefill, INT8 K/V, 32,768 GPU-resident KV cells, and MTP with four draft tokens. CPU vision uses the BF16 multimodal projector. Model files and preparation outputs are external mounts. These settings describe the serving target; workstation measurements are pending.

The launcher mounts model and recipe directories read-only, and cache/log directories writable. Strata receives an unlimited memory-lock allowance, 2 GB shared memory, and a 120-second stop timeout. Its API binds inside the container, with Docker publishing only to host loopback. Offline mode disables external fetches; local API authentication is disabled.

The wrapper relays output to Docker and `server.log`, forwards interrupt/termination signals, and preserves the server exit status. Engine and vision messages share `engine.log`.

## Pi compatibility

The Pi provider example uses its default OpenAI chat-completions behavior. The pinned Strata frontend accepts `max_completion_tokens`, streamed chat, tool calls/results, embedded images, and `reasoning_effort`. The explicit `off: none` mapping disables thinking, and `xhigh: xhigh` exposes that selection in Pi. Strata reads the thinking toggle from `chat_template_kwargs`; Pi's top-level `qwen` thinking format is therefore not selected.

References: [Strata frontend](https://github.com/Niko1221/Strata/blob/dbb2d168cffa8cf793d9325358809d5263c7c6b0/serve/frontend.py), [Pi adapter inspected](https://github.com/badlogic/pi-mono/blob/63ea042ce5bfe5c0eabcebaf084a9e24989e83c7/packages/ai/src/api/openai-completions.ts). End-to-end Pi behavior is pending workstation validation.

## Validation

Repository tests cover adapter selection, native options, missing artifacts, log forwarding, and archive verification. The workstation image check exercises binary startup and a HIP kernel. Model loading, generation, and image requests require prepared model artifacts and subsequent workstation checks.

---

[Recipe](recipe.md) · [Build and check](setup.md) · [Launcher](../../docs/launcher.md)
