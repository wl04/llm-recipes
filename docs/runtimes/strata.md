# Strata runtime

The shared runtime uses Strata's HIP engine and its own API server, with a CPU vision encoder. It targets `gfx1201`, including the RX 9070 XT. Recipes provide the model lock, native `strata.json`, Pi metadata, and a data directory derived from the recipe folder name.

[Upgrade Strata on the RX 9070 XT](#upgrade-strata-on-the-rx-9070-xt)

## Build and check

From the repository root, on Ubuntu x86_64 with Docker and AMD `/dev/kfd` and `/dev/dri` devices:

```bash
python3 scripts/build_runtime.py strata --check
```

Lower `--max-jobs` if compiler memory use is excessive. The image check exercises binary startup, API imports, and a HIP kernel on the selected GPU. Success ends with `Strata binaries, API imports, and HIP kernel: PASS`.

[`versions.lock.json`](../../runtimes/strata/container/versions.lock.json) pins AMD's ROCm development image and exact Strata and llama.cpp revisions. Source archives are verified before extraction. Python dependencies use hashes; Ubuntu dependencies use a dated snapshot. Strata uses vendored GGML and HIP kernels with MMQ prefill enabled. The separate CPU vision executable uses llama.cpp mtmd at the locked revision; portable CPU builds use AVX2.

The builder, preparation helper, launcher and baseline runner default to `llm-recipes/strata-rdna4:v0.2.13-95-gdbb2d168` from [runtime.json](../../runtimes/strata/runtime.json). Reuse your existing image for this checkout. Rebuild when its inputs change. Preparation and serving verify the runtime lock embedded in the image.

## Preparation

Run the preparation command from the recipe’s setup guide with the same models root used for serving (default `~/llm-recipes`). Stop the instance before preparing its files. Preparation resumes partial downloads, verifies the locked hashes, builds the pack and Q2_0 MTP draft, and writes a receipt matching the model and runtime locks. For Unsloth, `pack.compat_bf16` records converted tensors in `packs/iq3_xxs/conversions.json`; experts retain their published formats.

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

The [baseline runner](../baseline.md) checks the served model at `/v1/models`, sizes prompts through `/v1/messages/count_tokens`, and reads cached tokens from streamed usage. It matches `engine.log` completion records to requests for prefill, decode and draft acceptance.

Pi uses OpenAI-compatible chat completions. The frontend supports streaming, tool calls/results, embedded images, and `max_completion_tokens`. `low` and `medium` reasoning map directly; `high` and `xhigh` map to the model's `xhigh`. `off: none` disables thinking; `minimal` also disables it in this revision. See [Pi setup](../clients/pi.md) for installation and client configuration.

## Upgrade Strata on the RX 9070 XT

Use this guide to try a Strata release with Qwen3.8-Flash-Next Unsloth UD-IQ3_XXS and Pi. The worked candidate is **v0.2.17 / engine 0.1.63 / ROCm 10.2**. The checked-in Docker build still targets **engine 0.1.59.1 / ROCm 10.1**. Complete the source integration in step 2 before building the candidate.

### 1. Select the release and preserve the reference

Start at the repository root on the workstation. Use a clean reference checkout and a fresh worktree for the candidate. Set the tag once per upgrade. Choose a fresh candidate data directory dedicated to this trial.

```bash
tag=v0.2.17
recipe=qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram
reference=$(git rev-parse --show-toplevel)
candidate="${reference}-strata-${tag}"
models_root="${LLM_RECIPES_HOME:-$HOME/llm-recipes}"
candidate_root="${models_root}-strata-${tag}"
git worktree add -b "strata-${tag}" "$candidate" HEAD
```

Keep the reference checkout, its versioned image, and the original models root together for comparison and rollback. Run the remaining steps in the same Bash shell so the path variables stay available.

### 2. Pin the inputs and port the integration

Resolve the tag to its commit, including annotated tags. Hash the **commit-addressed** archive used by the Docker fetcher. Check the engine version in the tagged source. For a ROCm change, resolve the official image tag and verify the digest supports Linux amd64. [Upstream releases](https://github.com/Niko1221/Strata/releases) · [AMD image tags](https://hub.docker.com/r/rocm/dev-ubuntu-24.04/tags)

```bash
cd "$candidate"
(
  set -euo pipefail
  revision=$(curl -fsSL "https://api.github.com/repos/Niko1221/Strata/commits/$tag" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])')
  echo "$revision"
  curl -fsSL "https://codeload.github.com/Niko1221/Strata/tar.gz/$revision" | sha256sum
)
sudo docker buildx imagetools inspect rocm/dev-ubuntu-24.04:10.2.0-full
```

| Candidate input | Verified v0.2.17 value |
| --- | --- |
| Strata source | [12d491da4a6904eb49aaa6f2f63ec4b1a17582e3](https://github.com/Niko1221/Strata/commit/12d491da4a6904eb49aaa6f2f63ec4b1a17582e3) |
| Source archive SHA-256 | `52fc7f215b1e4f38a2ac7659dd0e32a9bc34cd211444c30814da8ad6d6ebc1db` |
| ROCm base | `rocm/dev-ubuntu-24.04:10.2.0-full` at `sha256:21801c0ba1bc4aba31f81ab11fe576c43daa7f2c7f42bac7baaa4d2f75273f86` |
| Engine and target | 0.1.63, HIP `gfx1201` |

Update the Strata revision and archive hash in [versions.lock.json](../../runtimes/strata/container/versions.lock.json), plus the base tag and digest when changing ROCm. Set `engine_version` and `engine_source_version` in [runtime.json](../../runtimes/strata/runtime.json) to the engine version and source release. Set the descriptor’s image tag to the candidate release (here `llm-recipes/strata-rdna4:v0.2.17`); each checkout then builds and launches its own version by default. For a second build of the same release, use the builder’s `--tag v0.2.17-rocm10.2` option and pass the full image name `--runtime-image llm-recipes/strata-rdna4:v0.2.17-rocm10.2` to preparation, doctor, start and baseline run. Keep model, projector and MTP locks fixed for the comparison.

For each release, check its CMake targets, server imports, preparation tools and effective launch arguments against the candidate checkout. The port from the current pin to **v0.2.17** needs these edits:

- In the Dockerfile build HIP from `engine/` and CPU vision from `terminal/tools/vision/`. Remove the legacy MMQ option and vision’s external `LLAMA_DIR`. Keep the llama.cpp pin while pack preparation uses its GGUF Python library. [Engine build](https://github.com/Niko1221/Strata/blob/v0.2.17/engine/CMakeLists.txt) · [Vision build](https://github.com/Niko1221/Strata/blob/v0.2.17/terminal/tools/vision/CMakeLists.txt)
- Point the image probe, Python search path, server and preparation tools at the `terminal/` layout. Verify the expert profile, draft vocabulary and MTP fetcher locations. Check that the fetcher’s pinned MTP revision matches the model lock. [Serving helper](../../runtimes/strata/scripts/serve.py) · [Preparation helper](../../runtimes/strata/scripts/prepare_models.py)
- Map launcher draft on/off to native `drafting: mtp/off` and keep `--spec 0` for off. Write the resolved `--kv-resident` value to both `args` and `user_args` so VRAM fitting respects the cap at shorter contexts. Test both drafting modes and a shorter context. [Draft policy](https://github.com/Niko1221/Strata/blob/v0.2.17/terminal/strata_control/drafting.py) · [VRAM fitting](https://github.com/Niko1221/Strata/blob/v0.2.17/terminal/strata_control/vram_fit.py)

### 3. Build and prepare the candidate

Set up the [checkout development environment](../project-instructions.md#development-dependencies-and-checks) in both worktrees used for baseline runs. Run these commands there. A separate models root keeps each pack and its `prepared.json` paired with the runtime lock that produced it. On filesystems without reflinks, allow about 78 GiB for the copied Unsloth model files, plus room for the new pack and image.

```bash
cd "$candidate"
bash scripts/check.sh
python3 scripts/build_runtime.py strata --check
mkdir -p "$candidate_root/recipes/$recipe/models"
cp -a --reflink=auto "$models_root/recipes/$recipe/models/." \
  "$candidate_root/recipes/$recipe/models/"
python3 runtimes/strata/scripts/prepare_models.py --recipe "recipes/$recipe" \
  --models "$candidate_root"
python3 scripts/launch.py doctor "$recipe" --models "$candidate_root"
```

### 4. Measure the upgrade

Stop the active server. Run the same suite from each checkout with the same model, sampling, MTP, CPU vision at 1,024 image tokens, and INT8 KV with 32,768 resident cells. For **v0.2.17**, leave `STRATA_ROUTE_TAIL_SKIP` unset on the candidate (default off). For a matched comparison, temporarily set `"env": {"STRATA_ROUTE_TAIL_SKIP": "0"}` in the reference recipe’s native config, preserving other environment entries. If importing the reference run, import it from that checkout before restoring the native config so the recorded hashes match. Baseline 002 used suite v2; use suite v3 on both arms for comparable returning-turn measurements.

```bash
(cd "$reference" && .venv/bin/python scripts/run_baseline.py run "$recipe" \
  --models "$models_root" --context 131072 --draft on --vision cpu)
(cd "$candidate" && .venv/bin/python scripts/run_baseline.py run "$recipe" \
  --models "$candidate_root" --context 131072 --draft on --vision cpu)
```

Compare cold prefill, warm time to first visible output at the same replay tier, decode, draft acceptance, peak RAM/VRAM, and swap during startup. Repeat in alternating order if differences are within run variability. For interactive checks, run `scripts/launch.py start` in the candidate checkout with the same recipe and models root. At Pi medium effort, test a multiline edit containing literal `</parameter>`, a tool result followed by another call, and retrieval of an early instruction in a long conversation. Check the edited file and the standard vision screenshot. Returning turns matter here. The [recorded Pi session](../../recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/003-2026-11-15-coding/summary.md) reused about 97% of its prompt tokens.

**v0.2.17 tuning.** Keep automatic expert caching, WMMA, PCIe miss split and PLE placement. Keep Q2_0 MTP at `--spec 4 --spec-min-p 0.5`. The upstream 47 GiB resident budget applies to larger Unsloth quants. Rank 7 tail skipping changed output on gfx1201. Trial it separately only if decode warrants it, checking the engine’s missed-experts-skipped counter and Pi edit fidelity. For a cold-prefill regression, record the loaded hipBLASLt version and tuning table. The shipped gfx1201 table for 1.5.0 was calibrated on a nightly build. To separate engine and ROCm effects, compare the same candidate source on both base images. [Release measurements](https://github.com/Niko1221/Strata/releases/tag/v0.2.17) · [RDNA4 defaults](https://github.com/Niko1221/Strata/blob/v0.2.17/docs/AMD_HIP.md#rdna4-gfx1201)

**Optional memory tuning.** If returning turns are limited by KV reads, compare 32,768, 65,536 and 131,072 resident cells at fixed context. The serving helper currently caps residency at 32,768, so first implement and test a recipe-configurable cap in the candidate worktree. Track expert-cache slots and hits alongside KV reads, latency, swap and 120K retrieval. Trial `--kv k8v4` separately if memory remains limiting. Recheck upstream status before considering [CPU IQ kernels](https://github.com/Niko1221/Strata/pull/6085) or [q4u32 KV](https://github.com/Niko1221/Strata/pull/6176).

### 5. Adopt or roll back

Import the successful candidate run from the matching candidate checkout before editing the measured inputs. The [baseline import](../baseline.md#import-a-baseline-run) generates its dated profile and reports. Keep a candidate that gives a repeatable benefit on your workload with working Pi tools, retrieval and vision. Stop the active instance, then start the candidate or return to the reference:

```bash
# Candidate
(cd "$candidate" && python3 scripts/launch.py start "$recipe" --models "$candidate_root")

# Reference
(cd "$reference" && python3 scripts/launch.py start "$recipe" --models "$models_root")
```

For a shared rollout, merge the validated integration and lock, then refresh the installed launcher from the merged checkout with `python3 scripts/install.py install`. Start with `llm-recipes start "$recipe" --models "$candidate_root"` to reuse the tested image and prepared candidate data. Keep the original models root for rollback.

### 6. Clean up the container trial

**After adopting the candidate**, keep its image and `$candidate_root`: the installed launcher uses them for serving. Once the integration and experiment are merged and the installed launcher works, remove the development worktree using the Git commands below.

**After rolling back**, stop the candidate instance before starting the reference. Import any baseline you want to keep from the matching worktree and save any trial logs you need. To reclaim space from a discarded v0.2.17 trial, remove its specific image tag and dedicated data directory:

```bash
sudo docker image rm llm-recipes/strata-rdna4:v0.2.17
if [[ -n ${models_root:-} && -n ${tag:-} && ${candidate_root:-} == "${models_root}-strata-${tag}" ]]; then
  du -sh -- "$candidate_root" && rm -rI -- "$candidate_root"
fi
```

For another release or build variant, substitute its actual candidate image tag. Keep the original models root, which also holds other recipes and baseline reports.

**Remove the worktree** once you have finished using it. Commit anything you want to retain, including imported results. Review the status before removal. The local branch retains committed work and can be deleted after it is merged.

```bash
cd "${reference:?}"
git -C "${candidate:?}" status --short
git worktree remove "$candidate"
# After merging the candidate into the reference branch:
git branch -d "strata-${tag:?}"
```

### Optional upstream package trial

Use this for a quick functional check before porting the Docker build. The upstream launcher selects its own preparation and placement defaults. Run in a separate shell using the release tag selected in step 1.

Stop the recipe container to free the GPU. Use a fresh trial directory and a copy of the prepared Unsloth GGUFs and projector. Set `models_root` to the data root that contains your `recipes/` folder. On filesystems without reflinks, the copy needs about 78 GiB, plus space for packages and preparation.

```bash
tag=v0.2.17
models_root="${LLM_RECIPES_HOME:-$HOME/llm-recipes}"
recipe=qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram
trial=$(mktemp -d "$HOME/strata-${tag}.XXXXXX")
feed=https://github.com/Niko1221/Strata/releases/download/$tag
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

Keep the same shell open for the trial commands. Confirm the startup identifies the selected engine version on the RX 9070 XT, MTP and CPU vision. Run `curl -fsS http://127.0.0.1:8082/v1/models` for the model ID. Use that ID and `http://127.0.0.1:8082/v1` in a separate local Pi provider. The upstream launcher selects its own defaults and preparation outputs, so use these results as a functional check. To discard the package trial, stop it from the same trial shell. The directory contains the copied GGUFs, prepared model, installer and isolated Strata state. After cleanup, close that shell to clear its exported paths.

```bash
if [[ -n ${tag:-} && ${trial:-} == "$HOME/strata-${tag}."?????? ]]; then
  "$trial/bin/strata" launch --stop && rm -rI -- "$trial"
fi
```

---

[All recipes](../../README.md) · [Launcher](../launcher.md) · [Authoring](../authoring.md)
