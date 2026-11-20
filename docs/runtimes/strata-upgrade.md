# Upgrade Strata on the RX 9070 XT

Use this guide to try a Strata release with Qwen3.8-Flash-Next Unsloth UD-IQ3_XXS and Pi. The worked candidate is **v0.2.17 / engine 0.1.63 / ROCm 10.2**. The checked-in Docker build still targets **engine 0.1.59.1 / ROCm 10.1**. Complete the source integration in step 2 before building the candidate.

## 1. Select the release and preserve the reference

Start at the repository root on the workstation. Use a clean reference checkout and a fresh worktree for the candidate. Set the tag once per upgrade.

```bash
tag=v0.2.17
recipe=qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram
reference=$(git rev-parse --show-toplevel)
candidate="${reference}-strata-${tag}"
models_root="${LLM_RECIPES_HOME:-$HOME/llm-recipes}"
candidate_root="${models_root}-strata-${tag}"
image="llm-recipes/strata-rdna4:${tag}-candidate"
git worktree add -b "strata-${tag}" "$candidate" HEAD
```

Find the reference image ID in the matching experiment’s `profile.yaml` under `software.running_image_id`. Give that image a separate local tag. The example uses [Unsloth baseline 002](../../recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/002-2026-11-15-baseline/profile.yaml). If the image has been removed, rebuild from its matching inputs and record the resulting ID.

```bash
baseline_id=sha256:afe7c1bff2f14085879a86bfcdc5729996a66beac14edee40207c08e255feca6
reference_image="llm-recipes/strata-rdna4:reference-${baseline_id:7:12}"
sudo docker image tag "$baseline_id" "$reference_image"
```

## 2. Pin the inputs and port the integration

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

Update the Strata revision and archive hash in [versions.lock.json](../../runtimes/strata/container/versions.lock.json), plus the base tag and digest when changing ROCm. Set `engine_version` and `engine_source_version` in [runtime.json](../../runtimes/strata/runtime.json) to the engine version and source release. Keep model, projector and MTP locks fixed for the comparison.

For each release, check its CMake targets, server imports, preparation tools and effective launch arguments against the candidate checkout. The port from the current pin to **v0.2.17** needs these edits:

- In the Dockerfile build HIP from `engine/` and CPU vision from `terminal/tools/vision/`. Remove the legacy MMQ option and vision’s external `LLAMA_DIR`. Keep the llama.cpp pin while pack preparation uses its GGUF Python library. [Engine build](https://github.com/Niko1221/Strata/blob/v0.2.17/engine/CMakeLists.txt) · [Vision build](https://github.com/Niko1221/Strata/blob/v0.2.17/terminal/tools/vision/CMakeLists.txt)
- Point the image probe, Python search path, server and preparation tools at the `terminal/` layout. Verify the expert profile, draft vocabulary and MTP fetcher locations. Check that the fetcher’s pinned MTP revision matches the model lock. [Serving helper](../../runtimes/strata/scripts/serve.py) · [Preparation helper](../../runtimes/strata/scripts/prepare_models.py)
- Map launcher draft on/off to native `drafting: mtp/off` and keep `--spec 0` for off. Write the resolved `--kv-resident` value to both `args` and `user_args` so VRAM fitting respects the cap at shorter contexts. Test both drafting modes and a shorter context. [Draft policy](https://github.com/Niko1221/Strata/blob/v0.2.17/terminal/strata_control/drafting.py) · [VRAM fitting](https://github.com/Niko1221/Strata/blob/v0.2.17/terminal/strata_control/vram_fit.py)

## 3. Build and prepare the candidate

Create the [checkout development environment](../project-instructions.md#development-dependencies-and-checks) in the candidate worktree. Run these commands there. A separate models root keeps each pack and its `prepared.json` paired with the runtime lock that produced it. On filesystems without reflinks, allow about 78 GiB for the copied Unsloth model files, plus room for the new pack and image.

```bash
cd "$candidate"
bash scripts/check.sh
python3 scripts/build_runtime.py strata --tag "${tag}-candidate" --check
mkdir -p "$candidate_root/recipes/$recipe/models"
cp -a --reflink=auto "$models_root/recipes/$recipe/models/." \
  "$candidate_root/recipes/$recipe/models/"
python3 runtimes/strata/scripts/prepare_models.py --recipe "recipes/$recipe" \
  --models "$candidate_root" --runtime-image "$image"
python3 scripts/launch.py doctor "$recipe" --models "$candidate_root" --runtime-image "$image"
```

The image check exercises the binaries, API imports and HIP kernel. Preparation verifies the model bytes. Doctor checks the resulting installation.

## 4. Measure the upgrade

Stop the active server. Run the same suite from each checkout with the same model, sampling, MTP, CPU vision at 1,024 image tokens, and INT8 KV with 32,768 resident cells. For **v0.2.17**, leave `STRATA_ROUTE_TAIL_SKIP` unset on the candidate (default off). For a matched comparison, temporarily set `"env": {"STRATA_ROUTE_TAIL_SKIP": "0"}` in the reference recipe’s native config, preserving other environment entries. Restore your reference config after recording the run. Baseline 002 used suite v2; use suite v3 on both arms for comparable returning-turn measurements.

```bash
(cd "$reference" && .venv/bin/python scripts/run_baseline.py run "$recipe" \
  --models "$models_root" --runtime-image "$reference_image" --context 131072 --draft on --vision cpu)
(cd "$candidate" && .venv/bin/python scripts/run_baseline.py run "$recipe" \
  --models "$candidate_root" --runtime-image "$image" --context 131072 --draft on --vision cpu)
```

Compare cold prefill, warm time to first visible output at the same replay tier, decode, draft acceptance, peak RAM/VRAM, and swap during startup. Repeat in alternating order if differences are within run variability. For interactive checks, run `scripts/launch.py start` in the candidate checkout with the same recipe, image and models root. At Pi medium effort, test a multiline edit containing literal `</parameter>`, a tool result followed by another call, and retrieval of an early instruction in a long conversation. Check the edited file and the standard vision screenshot. Returning turns matter here. The [recorded Pi session](../../recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/003-2026-11-15-coding/summary.md) reused about 97% of its prompt tokens.

**v0.2.17 tuning.** Keep automatic expert caching, WMMA, PCIe miss split and PLE placement. Keep Q2_0 MTP at `--spec 4 --spec-min-p 0.5`. The upstream 47 GiB resident budget applies to larger Unsloth quants. Rank 7 tail skipping changed output on gfx1201. Trial it separately only if decode warrants it, checking the engine’s missed-experts-skipped counter and Pi edit fidelity. For a cold-prefill regression, record the loaded hipBLASLt version and tuning table. The shipped gfx1201 table for 1.5.0 was calibrated on a nightly build. To separate engine and ROCm effects, compare the same candidate source on both base images. [Release measurements](https://github.com/Niko1221/Strata/releases/tag/v0.2.17) · [RDNA4 defaults](https://github.com/Niko1221/Strata/blob/v0.2.17/docs/AMD_HIP.md#rdna4-gfx1201)

**Optional memory tuning.** If returning turns are limited by KV reads, compare 32,768, 65,536 and 131,072 resident cells at fixed context. The serving helper currently caps residency at 32,768, so first implement and test a recipe-configurable cap in the candidate worktree. Track expert-cache slots and hits alongside KV reads, latency, swap and 120K retrieval. Trial `--kv k8v4` separately if memory remains limiting. Recheck upstream status before considering [CPU IQ kernels](https://github.com/Niko1221/Strata/pull/6085) or [q4u32 KV](https://github.com/Niko1221/Strata/pull/6176).

## 5. Adopt or roll back

Import the successful candidate run from the matching candidate checkout before editing the measured inputs. The [baseline import](../baseline.md#import-a-baseline-run) generates its dated profile and reports. Keep a candidate that gives a repeatable benefit on your workload with working Pi tools, retrieval and vision. For Unsloth-only use, launch from that checkout with the tested image tag and candidate models root. To return to the reference, stop the candidate and launch from the reference checkout with its saved image and original models root. Run one of these commands after stopping the active instance:

```bash
# Candidate
(cd "$candidate" && python3 scripts/launch.py start "$recipe" --models "$candidate_root" --runtime-image "$image")

# Reference
(cd "$reference" && python3 scripts/launch.py start "$recipe" --models "$models_root" --runtime-image "$reference_image")
```

For a shared rollout, merge the validated integration and lock, build the descriptor’s default image, prepare the serving data against that lock, and refresh the installed launcher with `python3 scripts/install.py install`. Retain the reference image and data until the installed command serves the expected model.

## Optional upstream package trial

Use this for a quick functional check before porting the Docker build. The upstream launcher selects its own preparation and placement defaults. Run in a separate shell using the release tag selected in step 1.

```bash
tag=v0.2.17
```

Stop the recipe container to free the GPU. Use a fresh trial directory and a copy of the prepared Unsloth GGUFs and projector. Set `models_root` to the data root that contains your `recipes/` folder. On filesystems without reflinks, the copy needs about 78 GiB, plus space for packages and preparation.

```bash
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

Keep the same shell open for the trial commands. Confirm the startup identifies the selected engine version on the RX 9070 XT, MTP and CPU vision. Run `curl -fsS http://127.0.0.1:8082/v1/models` for the model ID. Use that ID and `http://127.0.0.1:8082/v1` in a separate local Pi provider. The upstream launcher selects its own defaults and preparation outputs, so use these results as a functional check. Stop the trial with `"$trial/bin/strata" launch --stop`.
