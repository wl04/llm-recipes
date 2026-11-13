# Strata runtime

The shared runtime uses Strata's HIP engine and its own API server, with a CPU vision encoder. It targets `gfx1201`, including the RX 9070 XT. Recipes provide the model lock, native `strata.json`, Pi metadata, and an external data-directory name.

## Build and check

From the repository root, on Ubuntu x86_64 with Docker and AMD `/dev/kfd` and `/dev/dri` devices:

```bash
sudo docker build --progress=plain --build-arg MAX_JOBS=4 \
  -t llm-recipes/strata-rdna4:probe runtimes/strata/container
sudo docker run --rm --device=/dev/kfd --device=/dev/dri \
  llm-recipes/strata-rdna4:probe
```

Lower `MAX_JOBS` if compiler memory use is excessive. The image check exercises binary startup, API imports, and a HIP kernel on the selected GPU. Success ends with `Strata binaries, API imports, and HIP kernel: PASS`.

[`versions.lock.json`](../../runtimes/strata/container/versions.lock.json) pins AMD's ROCm development image and exact Strata and llama.cpp revisions. Source archives are verified before extraction. Python dependencies use hashes; Ubuntu dependencies use a dated snapshot. Strata uses vendored GGML and HIP kernels with MMQ prefill enabled. The separate CPU vision executable uses llama.cpp mtmd at the locked revision; portable CPU builds use AVX2.

The image name and API-server/engine pairing are declared in [`runtime.json`](../../runtimes/strata/runtime.json). Reuse the image while its lock matches; rebuild after changing build inputs or pins. Preparation and serving check the image's lock against this runtime's lock.

## Preparation

Run the preparation command in the recipe's setup guide with that recipe directory and external models root.

The helper mounts the recipe and runtime read-only and the external models directory writable, running as the host UID. The recipe's `config/launch.json` supplies `data_directory`; its `models.lock.json` pins shard revisions, sizes and SHA-256 hashes, the projector, MTP source, and pack conversion options. Each recipe has its own `prepared.json` under its data directory.

Downloads resume through `.part` files and are verified before publication. Rerun after interruption. Preparation uses upstream `iq_pack.py`, `mtp_fetch.py`, `mtp_pack.py`, and `mtp_rt.py`. The packer discovers every shard from the first shard's filename. A lock with `pack.compat_bf16: true` enables upstream compatibility conversion and records it in `packs/iq3_xxs/conversions.json`; experts retain their published formats. MTP tensors are verified at the pinned checkpoint revision and converted according to the model lock. A filesystem lock prevents concurrent preparation of the same data directory. Stop the serving instance before preparing its files.

Prepared files under `data_directory`:

```text
models/              # Published GGUF shards and projector
packs/iq3_xxs/       # Native pack, tokenizer, optional conversion report
mtp/                 # Verified source, converted GGUF and rt/ runtime
prepared.json        # Completion record matching model and runtime locks
```

## Serving

The [launcher](../launcher.md#shared-runtimes) provides the mounts and entry point. The Strata adapter adds unlimited memory locking, 2 GB shared memory, and a 120-second stop timeout.

The serving helper checks the completion receipt against the selected model and runtime locks, checks all shard sizes and required artifacts, selects the RX 9070 XT, and creates a temporary native configuration. `--context`, `--draft`, and `--vision cpu|off` override that recipe's defaults. The GPU-resident KV setting is capped at 32,768 cells by this integration. The API is published on host loopback; offline mode disables external fetching. Readiness is `/health`.

`server.log` retains API console output; `engine.log` contains engine and vision messages. Both append in the selected host log directory and survive container removal. Rotate them while the server is stopped. The wrapper forwards stop signals and preserves the server exit status.

## Checks and clients

Use `runtimes/strata/scripts/check_generation.py` with `text`, `tools`, `vision`, or `long`, and an explicit `--model` matching the selected recipe. `--base-url` defaults to `http://127.0.0.1:8080`. The checks use temperature zero and disable thinking. The long check counts input through the Anthropic endpoint before generation; keep input plus output below the configured context. The long check reserves 128 output tokens by default. Inspect image answers against the input screenshot; record measured results using the [authoring guide](../authoring.md). Each recipe's setup guide supplies exact commands.

Pi uses OpenAI-compatible chat completions. The frontend supports streaming, tool calls/results, embedded images, and `max_completion_tokens`. `low` and `medium` reasoning map directly; `high` and `xhigh` map to the model's `xhigh`. `off: none` disables thinking; `minimal` also disables it in this revision. See [Pi setup](../clients/pi.md) for installation and client configuration.

---

[All recipes](../../README.md) · [Launcher](../launcher.md) · [Authoring](../authoring.md)
