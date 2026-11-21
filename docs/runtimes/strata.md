# Strata runtime

The shared runtime uses Strata's HIP engine and its own API server, with a CPU vision encoder. It targets `gfx1201`, including the RX 9070 XT. Recipes provide the model lock, native `strata.json`, Pi metadata, and a data directory derived from the recipe folder name.

[Upgrade Strata on the RX 9070 XT](#upgrade-strata-on-the-rx-9070-xt)

## Build and check

From the repository root, on Ubuntu x86_64 with Docker and AMD `/dev/kfd` and `/dev/dri` devices:

```bash
recipe=qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram
python3 scripts/build_runtime.py strata --recipe "$recipe" --check
```

Lower `--max-jobs` if compiler memory use is excessive. The image check exercises binary startup, API imports, and a HIP kernel on the selected GPU. Success ends with `Strata binaries, API imports, and HIP kernel: PASS`.

[`versions.lock.json`](../../runtimes/strata/container/versions.lock.json) pins AMD's ROCm development image and exact Strata and llama.cpp revisions. Source archives are verified before extraction. Python dependencies use hashes; Ubuntu dependencies use a dated snapshot. The CPU vision build uses a portable AVX2 baseline.

The shared [runtime descriptor](../../runtimes/strata/runtime.json) supplies the default image. For a recipe selecting `strata/releases/<version>`, build its pinned image with `python3 scripts/build_runtime.py strata --version <version> --check`. Preparation, serving and baseline runs follow the recipe selection. Reuse your existing image for this checkout. Rebuild when its inputs change. Preparation and serving verify the runtime lock embedded in the image.

## Preparation

With the serving instance stopped, run these commands from the repository root. Use the same models root for preparation and serving.

```bash
recipe=qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram
models_root="${LLM_RECIPES_HOME:-$HOME/llm-recipes}"
python3 runtimes/strata/scripts/prepare_models.py --recipe "recipes/$recipe" --models "$models_root"
```

Preparation resumes partial downloads, verifies the locked hashes, builds the pack and Q2_0 MTP draft, and writes a receipt matching the model and runtime locks. For Unsloth, `pack.compat_bf16` records converted tensors in `packs/iq3_xxs/conversions.json`; experts retain their published formats.

Strata shares the BF16 MTP source at `<models root>/.cache/strata/mtp/<repository>/<revision>/`. On first use it can import the tensors from a completed preparation, including another recipe or release with the same checkpoint pin. Import copies the raw tensors once (about 4.86 GiB for Qwen3.8-Flash-Next) and checks every file against the SHA-256 table in the selected engine. If no existing preparation can seed an empty cache, preparation downloads the pinned tensors. A corrupt published cache entry stops preparation with a verification error. Concurrent preparations share one fetch. Each recipe builds its own quantized draft from the verified source.

To reclaim raw tensor copies from older completed preparations, run these commands from the updated checkout after preparation finishes:

```bash
python3 tools/compact_strata_mtp.py          # Preview verified duplicates
python3 tools/compact_strata_mtp.py --apply  # Keep one shared source
```

Cleanup uses the checkout’s local Strata image offline. If the cache is empty, allow 4.86 GiB of temporary free space for the verified import. Each recipe keeps its generated draft, pack, tokenizer and receipt.

Prepared files under the recipe's data folder:

```text
models/              # Published GGUF shards and projector
prepared/<version>/
  packs/iq3_xxs/     # Native pack, tokenizer, optional conversion report
  mtp/               # Converted draft GGUF and rt/ runtime
  prepared.json      # Completion record matching model and runtime locks
```

### Existing v0.2.13 + 95 installations

For an existing top-level `packs/`, `mtp/` and `prepared.json`, run the [one-time migration](../../tools/migrate_strata_v0213.py) from the updated checkout. Use the same `LLM_RECIPES_HOME` as the launcher. Stop serving containers and finish or roll back locally adopted trials first.

```bash
python3 tools/migrate_strata_v0213.py          # Preview each local recipe
python3 tools/migrate_strata_v0213.py --apply
python3 scripts/install.py install
```

The utility verifies the locks and moves the three generated items to `prepared/v0.2.13-95-gdbb2d168/` by filesystem rename. Shared model files stay in place. If interrupted, repeat the preview and apply commands. After reinstalling, run `llm-recipes doctor <recipe-id>` for each recipe printed as verified. Fresh installations use the ordinary preparation command above.

## Serving

The [launcher](../launcher.md#shared-runtimes) provides the mounts and entry point. The Strata adapter adds unlimited memory locking, 2 GiB shared memory, and a 120-second stop timeout.

The serving helper checks the completion receipt against the selected model and runtime locks, checks all shard sizes and required artifacts, selects a single visible `gfx1201` device, and creates a temporary native configuration. `--context`, `--draft`, and `--vision cpu|off` override that recipe's defaults. The GPU-resident KV setting is capped at 32,768 cells by this integration. The API is published on host loopback; offline mode disables external fetching. Check startup and follow the logs from the checkout used for serving (Ctrl+C leaves a detached server running):

```bash
python3 scripts/launch.py start "$recipe" --models "$models_root" --detach
curl --retry 90 --retry-delay 2 --retry-all-errors -fsS http://127.0.0.1:8080/health
python3 scripts/launch.py logs "$recipe" --follow
python3 scripts/launch.py stop "$recipe"
```

`server.log` retains API console output; `engine.log` contains engine and vision messages. Both append in the selected host log directory and survive container removal. Rotate them while the server is stopped. A baseline run points them at its own output directory. The wrapper forwards stop signals and preserves the server exit status.

## Baseline and clients

The [baseline runner](../baseline.md) checks the served model at `/v1/models`, sizes prompts through `/v1/messages/count_tokens`, and reads cached tokens from streamed usage. It matches `engine.log` completion records to requests for prefill, decode and draft acceptance.

With the instance stopped, run the baseline from a checkout with the development dependencies installed:

```bash
.venv/bin/python scripts/run_baseline.py run "$recipe" --models "$models_root"
```

Pi uses OpenAI-compatible chat completions. The frontend supports streaming, tool calls/results, embedded images, and `max_completion_tokens`. `low` and `medium` reasoning map directly; `high` and `xhigh` map to the model's `xhigh`. `off: none` disables thinking; `minimal` also disables it in this revision. See [Pi setup](../clients/pi.md) for installation and client configuration.

## Upgrade Strata on the RX 9070 XT

Run these commands from your reference checkout. Set `LLM_RECIPES_HOME` if your existing models live outside `~/llm-recipes`. Stop the instance using the GPU before the image check. The script discovers Strata recipes with weights in your data home and prints their names. An incomplete local weight set is reported before the build. Catalog entries without local weights are skipped.

```bash
python3 scripts/upgrade_strata.py v0.2.18
```

The script resolves the upstream tag and ROCm Linux amd64 digest, checks upstream compatibility, and creates or resumes a sibling Git worktree. It compares the local image’s embedded build lock before running the HIP check. Matching inputs reuse the image, including an existing v0.2.18 build. A conflicting tag stops the command. Use `--prepare-only` to inspect the Git inputs before building or preparing data.

Each trial records its selected recipes so retries, adoption and cleanup use the same set. One image serves all selected recipes. The script reuses the published shards and projector under `recipes/<recipe>/models/` in the data home. Each trial prepares its pack, tokenizer, MTP files and receipt under `recipes/<recipe>/prepared/<version>/`. A completed matching preparation is reused.

The script prints launch and baseline commands for each selected recipe. Run one model at a time. Stop its interactive server before starting its baseline.

### Adopt and publish

```bash
python3 scripts/upgrade_strata.py v0.2.18 --adopt
```

Adoption verifies the prepared files and image, commits the selected recipe manifests and shared release pins together, and activates the worktree for those recipes. The script installs or refreshes the launcher if needed. The new selection applies on the next start. Keep the worktree while it is selected locally.

To share those exact inputs, push the adoption commit and merge the branch through your usual review workflow. The script prints the push command for your checkout:

```bash
git -C "$(git rev-parse --show-toplevel)-strata-v0.2.18" push -u origin strata-v0.2.18
```

After merging, other machines can pull, build the recipe’s selected image, prepare their models, and run `python3 scripts/install.py install`. Docker images and generated model data stay on each machine.

### Discard or roll back

Stop the candidate instance, then run:

```bash
python3 scripts/upgrade_strata.py v0.2.18 --delete
```

For a locally adopted trial, deletion verifies every active recipe’s predecessor before restoring their selections. It removes the trial worktree, verified image tag and version-specific preparation. Unmerged adoption commits remain available on the branch. Shared weights, original preparation, logs and baseline results remain available. Roll back multiple local adoptions newest first. If the reference checkout or installed defaults already select the published release, revert the selection in Git and refresh the installed launcher before deleting that release.

For later releases, substitute the new tag. The [upgrade configuration](../../runtimes/strata/upgrade.json) controls the base tag, build parallelism, extra Boolean engine CMake options and an optional image suffix. For two builds of one release, use distinct suffixes and pass the same `--config <file>` to prepare, adopt and delete each variant.

---

[All recipes](../../README.md) · [Launcher](../launcher.md) · [Baseline](../baseline.md)
