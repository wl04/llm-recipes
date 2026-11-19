# Strata runtime

The shared runtime uses Strata's HIP engine and its own API server, with a CPU vision encoder. It targets `gfx1201`, including the RX 9070 XT. Recipes provide the model lock, native `strata.json`, Pi metadata, and an external data-directory name.

## Build and check

From the repository root, on Ubuntu x86_64 with Docker and AMD `/dev/kfd` and `/dev/dri` devices:

```bash
python3 scripts/build_runtime.py strata --check
```

Lower `--max-jobs` if compiler memory use is excessive. The image check exercises binary startup, API imports, and a HIP kernel on the selected GPU. Success ends with `Strata binaries, API imports, and HIP kernel: PASS`.

[`versions.lock.json`](../../runtimes/strata/container/versions.lock.json) pins AMD's ROCm development image and exact Strata and llama.cpp revisions. Source archives are verified before extraction. Python dependencies use hashes; Ubuntu dependencies use a dated snapshot. Strata uses vendored GGML and HIP kernels with MMQ prefill enabled. The separate CPU vision executable uses llama.cpp mtmd at the locked revision; portable CPU builds use AVX2.

The image name and API-server/engine pairing are declared in [`runtime.json`](../../runtimes/strata/runtime.json). Reuse the image while its lock matches; rebuild after changing build inputs or pins. Preparation and serving check the image's lock against this runtime's lock.

## Try Strata v0.2.16

The [upstream Linux Terminal package](https://github.com/Niko1221/Strata/releases/tag/v0.2.16) supports a standalone trial of engine 0.1.62. Use the trial to check startup, CPU vision, and Pi tool calls. Follow the [evaluation plan](../plans/strata-rx-9070-xt-evaluation.md#1-engine-0162-and-native-cpu-vision) for the controlled container comparison.

Stop the recipe container to free the GPU. Use a fresh trial directory and a copy of the prepared Unsloth GGUFs and projector. Set `models_root` to the data root that contains your `recipes/` folder. On filesystems without reflinks, the copy needs about 78 GiB, plus space for packages and preparation.

```bash
models_root="${LLM_RECIPES_HOME:-$HOME/llm-recipes}"
recipe=qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram
trial=$(mktemp -d "$HOME/strata-v0.2.16.XXXXXX")
feed=https://github.com/Niko1221/Strata/releases/download/v0.2.16
models="$models_root/recipes/$recipe/models"

mkdir -p "$trial/gguf"
cp -a --reflink=auto "$models/UD-IQ3_XXS/." "$trial/gguf/"
cp -a --reflink=auto "$models/mmproj-Qwen3.8-Flash-Next-BF16.gguf" "$trial/gguf/"

export XDG_DATA_HOME="$trial/xdg-data" XDG_CONFIG_HOME="$trial/xdg-config"
export XDG_STATE_HOME="$trial/xdg-state" XDG_CACHE_HOME="$trial/xdg-cache"
export STRATA_DATA_DIR="$trial/strata" STRATA_BIN_DIR="$trial/bin"
export STRATA_PROFILE_DIR="$trial/profiles" STRATA_RUNTIME_DIR="$trial/runtime"
export STRATA_INSTALL_DIR="$trial/install"
curl -fL "$feed/install.sh" -o "$trial/install.sh"
STRATA_FEED="$feed" sh "$trial/install.sh"

"$trial/bin/strata" launch --feed "$feed" --backend amd \
  --model-path "$trial/gguf" --data-dir "$trial/model-data" \
  --family unsloth --model UD-IQ3_XXS --context 131072 --kv int8 \
  --parallel 1 --drafting mtp --vision cpu --tune skip \
  --access local --port 8082 --yes --no-tui
```

Keep the same shell open for the trial commands. Confirm the startup identifies engine 0.1.62 on the RX 9070 XT, MTP and CPU vision. Run `curl -fsS http://127.0.0.1:8082/v1/models` for the model ID. Use that ID and `http://127.0.0.1:8082/v1` in a separate local Pi provider. The upstream launcher selects its own defaults and preparation outputs, so use these results as a functional check. Stop the trial with `"$trial/bin/strata" launch --stop`.

## Compare a candidate runtime

Keep the baseline checkout, `:probe` tag, and prepared models untouched. Find `software.running_image_id` in the baseline experiment's `profile.yaml` and tag **that ID**, not the current `:probe`. For example, for experiment `002`:

```bash
baseline_id=sha256:afe7c1bff2f14085879a86bfcdc5729996a66beac14edee40207c08e255feca6
sudo docker image tag "$baseline_id" llm-recipes/strata-rdna4:baseline-002
```

If Docker cannot find that ID, rebuild from the matching inputs and record the new image ID. Use a separate worktree when the candidate changes the runtime lock or its integration. Build from that checkout with a candidate tag:

```bash
image=llm-recipes/strata-rdna4:candidate
recipe=qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram
python3 scripts/build_runtime.py strata --tag candidate --check
```

Use a separate data root because `prepared.json` matches the runtime lock. Seed the candidate with the published model shards and projector. The preparation command verifies those bytes and writes a candidate pack and receipt. Copying needs space for the model unless the filesystem supports reflinks.

```bash
models_root="${LLM_RECIPES_HOME:-$HOME/llm-recipes}"
candidate_root="$HOME/llm-recipes-strata-candidate"
mkdir -p "$candidate_root/recipes/$recipe/models"
cp -a --reflink=auto "$models_root/recipes/$recipe/models/." \
  "$candidate_root/recipes/$recipe/models/"
python3 runtimes/strata/scripts/prepare_models.py --recipe "recipes/$recipe" \
  --models "$candidate_root" --runtime-image "$image"
python3 scripts/launch.py doctor "$recipe" --models "$candidate_root" --runtime-image "$image"
```

Stop the active server before running the candidate. Run the checkout’s tools so the selected image, integration, and lock match. The [baseline runner](../baseline.md) starts and stops the candidate and records its actual image ID.

```bash
python3 scripts/run_baseline.py run "$recipe" --models "$candidate_root" \
  --runtime-image "$image" --context 131072 --draft on --vision cpu
```

For an interactive trial, pass the same image and models options to `scripts/launch.py start`. Use the original checkout, image and data root to return to the reference.

## Preparation

Run the preparation command in the recipe’s setup guide. Pass the same models root to preparation and serving. The preparation script takes an explicit `--models` path and falls back to `~/llm-recipes` when it is omitted.

The helper mounts the recipe and runtime read-only and the external models directory writable, running as the host UID. The recipe's data folder is `recipes/<recipe-id>` under the models root, derived from the recipe folder name; `models.lock.json` pins shard revisions, sizes and SHA-256 hashes, the projector, MTP source, and pack conversion options. Each recipe has its own `prepared.json` in its data folder.

Downloads resume through `.part` files and are verified before publication. Rerun after interruption. Preparation uses upstream `iq_pack.py`, `mtp_fetch.py`, `mtp_pack.py`, and `mtp_rt.py`. The packer discovers every shard from the first shard's filename. A lock with `pack.compat_bf16: true` enables upstream compatibility conversion and records it in `packs/iq3_xxs/conversions.json`; experts retain their published formats. MTP tensors are verified at the pinned checkpoint revision and converted according to the model lock. A filesystem lock prevents concurrent preparation of the same data directory. Stop the serving instance before preparing its files.

Prepared files under the recipe's data folder:

```text
models/              # Published GGUF shards and projector
packs/iq3_xxs/       # Native pack, tokenizer, optional conversion report
mtp/                 # Verified source, converted GGUF and rt/ runtime
prepared.json        # Completion record matching model and runtime locks
```

## Serving

The [launcher](../launcher.md#shared-runtimes) provides the mounts and entry point. The Strata adapter adds unlimited memory locking, 2 GiB shared memory, and a 120-second stop timeout.

The serving helper checks the completion receipt against the selected model and runtime locks, checks all shard sizes and required artifacts, selects a single visible `gfx1201` device, and creates a temporary native configuration. `--context`, `--draft`, and `--vision cpu|off` override that recipe's defaults. The GPU-resident KV setting is capped at 32,768 cells by this integration. The API is published on host loopback; offline mode disables external fetching. Readiness is `/health`.

`server.log` retains API console output; `engine.log` contains engine and vision messages. Both append in the selected host log directory and survive container removal. Rotate them while the server is stopped. A baseline run points them at its own output directory. The wrapper forwards stop signals and preserves the server exit status.

## Baseline and clients

The [baseline runner](../baseline.md) is the way to check and measure a Strata recipe; the recipe's setup guide has the command. It relies on this server as follows:

- **Readiness:** `/health` answers once the server is up; the runner polls `/v1/models` until a model is listed, then checks that it is the expected one.
- **Requests:** OpenAI-compatible chat completions, streamed with `stream_options.include_usage`, limited with `max_completion_tokens`, and with thinking disabled through `reasoning_effort: none`.
- **Prompt sizing:** `POST /v1/messages/count_tokens` counts a prompt without running it, so no measured prompt warms the cache. Its count ran about 40 tokens above the usage the server reports at 8K input; the reports use the server's usage.
- **Cache:** usage reports cached input tokens.
- **Engine timings:** the engine log holds one line per completion, such as `strata serve: prompt 24 tokens = 0 reused + 24 read in 315 ms (76.3 tok/s), 120 generated in 1233 ms (97.3 tok/s), drafts accepted 86 of 94, 1 checkpoints`. The runner keeps the log in the run's `server-logs/` and matches the lines to its requests to report engine prefill and decode speed and draft acceptance.

Pi uses OpenAI-compatible chat completions. The frontend supports streaming, tool calls/results, embedded images, and `max_completion_tokens`. `low` and `medium` reasoning map directly; `high` and `xhigh` map to the model's `xhigh`. `off: none` disables thinking; `minimal` also disables it in this revision. See [Pi setup](../clients/pi.md) for installation and client configuration.

---

[All recipes](../../README.md) · [Launcher](../launcher.md) · [Authoring](../authoring.md)
