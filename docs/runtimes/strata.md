# Strata runtime

Strata serves GGUF models through its own API on Ubuntu x86_64 with Docker and a gfx1201 GPU. Start with the setup guide for your model. Each guide gives the commands for its pinned image, weights, and Pi provider.

| Recipe | Pinned Strata build | Setup |
|---|---|---|
| Unsloth UD-IQ3_XXS | [v0.2.21](../../runtimes/strata/releases/v0.2.21/runtime.json) | [Build and run](../../recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/setup.md) |
| ISTA IQ3_XXS | [v0.2.21](../../runtimes/strata/releases/v0.2.21/runtime.json) | [Build and run](../../recipes/qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram/setup.md) |

## Build and check

To test a newer engine or ROCm image, follow [Upgrade a container runtime](../launcher.md#upgrade-a-container-runtime).

Docker needs access to `/dev/kfd` and `/dev/dri`. The recipe's build command reads its selected release lock and checks binary startup, API imports and a HIP kernel. If the compiler runs short of RAM, add `--max-jobs 2`.

The builder chooses the source layout from the runtime lock. CMake uses the physical upstream directories; `/opt/src/strata` is the runtime path. Vision configures before the HIP engine build, so an unsupported source layout or missing CMake dependency fails before compilation.

## Preparation

The data root defaults to `~/llm-recipes`. Set `LLM_RECIPES_HOME` before preparation and launch to use another location. Preparation verifies the published GGUF shards under `recipes/<recipe>/models/`. Recipes using the same pinned checkpoint share the verified BF16 MTP source under `.cache/strata/mtp/<repository>/<revision>/`.

Both Qwen3.8-Flash-Next recipes serve the same Q8_0 CPU projector under `<data root>/projectors/`. Preparation builds the quantizer from the image's pinned llama.cpp source on first use and checks the output against the model lock. It can add the projector to an existing preparation without repacking the model or regenerating MTP. The pinned BF16 source lives beside Q8_0 in `projectors/`.

Each recipe keeps its generated pack, tokenizer, Q2_0 draft and receipt in `recipes/<recipe>/prepared/<version>/`. Repeating preparation reuses a completed matching receipt and resumes partial downloads.

## Serving

The server publishes its API on loopback. `server.log` contains API output and `engine.log` contains engine and vision diagnostics. Both survive container removal under `<data root>/logs/<instance>/`. Baseline runs keep their own logs in the run directory. See the [launcher controls](../launcher.md#foreground-and-background-execution) and [baseline guide](../baseline.md).

Both recipes start with a GPU-resident KV window of 32,768 tokens. Strata can shrink this window at startup to fit available VRAM while keeping the requested context length. Imported profiles report the configured window.

To pin 40,960 tokens, set `"user_args": ["--kv-resident", "40960"]` in the recipe’s `config/strata.json`. If `user_args` already exists, append the flag and value to it. Remove the pair to restore automatic fitting. When using the installed launcher, run `python3 scripts/install.py install` after editing the checkout, then restart the instance.

## Upgrade Strata on the RX 9070 XT

For a release already selected on `main`, pull and reinstall with serving instances stopped. If you already prepared that build on this machine, you can start the recipe immediately. For a fresh machine, follow the recipe setup above.

```bash
git pull --ff-only
python3 scripts/install.py install
```

From the main checkout with the GPU free, select all installed Strata recipes or pass a single recipe ID:

```bash
python3 scripts/upgrade_runtime.py strata --release v0.2.23
```

The published GGUFs and the verified Q8_0 projector stay at their original paths. The candidate can reuse the projector without its BF16 source. ISTA and Unsloth retain separate target packs; recipes with the same MTP inputs can share the runtime payloads. The upgrader only needs source tensors or conversion intermediates for stages that cannot reuse a serving artifact.

Run the printed baseline for each recipe. Check text generation, nonzero MTP acceptance, CPU vision and the long-context workload. Follow the [launcher guide](../launcher.md#upgrade-a-container-runtime) to resume, adopt or roll back. Use `scripts/upgrade_strata.py` with its original tag and configuration to manage trials created by that entry point.

---

[All recipes](../../README.md) · [Launcher](../launcher.md) · [Authoring](../authoring.md)
