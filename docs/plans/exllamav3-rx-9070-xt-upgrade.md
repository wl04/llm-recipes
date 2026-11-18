# ExLlamaV3 runtime upgrade plan for the RX 9070 XT

Evaluate whether ExLlamaV3 1.6.7 improves warm Pi turns and whether the community RDNA4 kernels improve long-context decode. Keep the [current recipe](../../recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/recipe.md) available as the serving default until a candidate passes on the target GPU.

## Reference

The [runtime lock](../../runtimes/exllamav3-tabbyapi/container/versions.lock.json) pins unpatched ExLlamaV3 1.6.6 and TabbyAPI `8f92fac`, built for `gfx1201` on AMD’s PyTorch `2.14.0+rocm10.1.0` image. The [model lock](../../recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/config/models.lock.json) pins the Qwen3.8-27B EXL3 3 bpw target and DFlash2 source and defines the 3 bpw draft conversion.

- [Baseline 001](../../recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/001-2026-11-14-baseline/summary.md) recorded 1,038 tok/s prefill, 36.4 tok/s decode, and 28.9% draft acceptance at 119,542 input tokens.
- [Coding session 002](../../recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/002-2026-11-07-coding-gpu-switcher/summary.md) recorded 97.2% prompt reuse, 1.90 s median time to first token, and 59.6 tok/s median decode.

Rerun the reference with the current baseline runner. The historical results establish the workload and its scale. Promotion decisions use the paired runs below.

## 1. Test the upstream release

Build vanilla [ExLlamaV3 1.6.7](https://github.com/turboderp-org/exllamav3/releases/tag/v1.6.7) (`8c593e4`) with [TabbyAPI `4728158`](https://github.com/theroyallab/tabbyAPI/commit/47281587f). Pin the full source revisions and archive hashes. Compare TabbyAPI’s runtime dependencies with the existing hashed overlay and validate the recipe against its configuration schema. Keep the ROCm/PyTorch image digest, GPU architecture, and server sampling settings fixed.

Rolling recurrent checkpoints can reduce the tokens replayed on follow-up turns. Measure this with cached requests and track warm first-token latency. Long cold prompts exercise the chunked-prefill shared-memory fix. The prefill pipeline requires at least two GPU stages, so the single RX 9070 XT uses the regular prefill path. [Release comparison](https://github.com/turboderp-org/exllamav3/compare/v1.6.6...v1.6.7) · [Pipeline source](https://github.com/turboderp-org/exllamav3/blob/v1.6.7/exllamav3/model/prefill_pipeline.py)

## 2. Test the RDNA4 kernels on the same release

Create a second candidate from the step 1 build inputs. Pin the [combined patch from reference revision `d8c5c742`](https://github.com/parth-thakre/exl3-rdna4-recipe/blob/d8c5c742/patches/exllamav3-rdna4.patch), record its source and SHA-256 in the build inputs, and check and apply it before compiling. Record the patch license and effective kernel settings. Build from the existing AMD base image with the recipe’s model locks.

Compare the patched build with its tuning disabled, then with the gfx12 WMMA verification path and the Q4 split-decode tuning documented by the reference. Verify the effective switches, since the reference’s disable behavior is in its launcher script. If the combined settings help, test the verification and attention changes separately to identify which settings to carry. The same-card reference results use greedy code and a different ROCm/PyTorch stack. The sampled decode and long-context gain on this machine are the outcomes to measure. [Patch scope](https://github.com/parth-thakre/exl3-rdna4-recipe/blob/d8c5c742/patches/README.md) · [Switches](https://github.com/parth-thakre/exl3-rdna4-recipe/blob/d8c5c742/setup/env.sh) · [Measurements](https://github.com/parth-thakre/exl3-rdna4-recipe/blob/d8c5c742/notes/measurements.md)

## Workstation validation

1. Use separate worktrees and image tags for the reference and candidates. In each candidate worktree, set the image tag in `runtime.json` and use a separate models root. Copy or filesystem-clone the prepared target and original draft folders, including their manifests. Use the [runtime build and image check](../runtimes/exllamav3-tabbyapi.md#build-and-check) and the [recipe preparation command](../../recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/setup.md#prepare-models) to convert the draft into fresh output and work directories. The converted draft manifest must match the candidate’s build lock. Record output hashes as well as conversion arguments, since two conversions may yield different draft artifacts. Compare tuning off and on using the same patched image and converted draft to isolate the kernel changes.
2. Run `python3 scripts/run_baseline.py run qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram --context 131072 --draft on --vision on --models "$models_root"` from each worktree. Use one server at a time. Verify the recorded image ID and keep the same suite version, replay tier, sampling, context, Q4 caches, GPU vision and batch size of one. Alternate fresh reference and candidate starts, using the same warmup. Compare cold prefill and decode at 8K, 32K, 64K and near 120K separately from first-token latency and replayed tokens on warm turns. Record draft acceptance, peak VRAM and RAM, and any stalls or GPU resets. [Baseline guide](../baseline.md)
3. Replay the same short Pi coding task through each candidate, with the same reasoning effort and output cap. Include streamed tool calls with escaped and multiline arguments, a follow-up turn reusing the conversation, and a long-context check that retrieves an early instruction. Confirm the vision response and repeat the near-120K run with vision enabled to check memory headroom. Use the sampled workload for the decision and a greedy replay as a diagnostic.

## Promotion

Promote the upstream pins if the candidate preserves tool, vision and retrieval behavior and improves warm latency or long-prompt reliability without a repeatable performance regression. Adopt the RDNA4 patch only if sampled generation improves beyond run-to-run variation without increasing allocation failures, stalls, or incorrect output. Record the winning configuration and results as a new dated experiment. If the measurements are mixed, keep the current image and model root available and retain the simpler passing configuration.

Revisit [FlashStates](https://github.com/turboderp-org/exllamav3/pull/595) and its [TabbyAPI integration](https://github.com/theroyallab/tabbyAPI/pull/519) if recurrent replay still dominates warm-turn latency. Revisit [DFlash2 rejection sampling](https://github.com/turboderp-org/exllamav3/pull/423) if draft acceptance remains the bottleneck and a compatible revision is available. Keep both outside the initial comparison.
