# Strata evaluation plan: RX 9070 XT, 16 GiB

Keep the [UD-IQ3_XXS recipe](../../recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/recipe.md) as the serving default. Evaluate three questions in order: does exact handling of low-ranked experts improve coding tool calls, does a newer engine help this workload, and is GPU memory better spent on KV cells than on experts? Each experiment can stand alone; none requires versioned runtime directories.

## Reference and controls

The [runtime lock](../../runtimes/strata/container/versions.lock.json) pins Strata `dbb2d168` (engine 0.1.59.1). The reference uses HIP MMQ prefill, automatic expert caching, INT8 KV, 131,072 context tokens, 32,768 resident cells, Q2_0 MTP (`--spec 4 --spec-min-p 0.5`), and CPU vision.

- [Baseline 002](../../recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/002-2026-11-15-baseline/summary.md): at 119,492 input tokens, first output took 37.10 s and decode reached 85.83 tok/s; peak VRAM was 15.3/15.9 GiB. At 8K, the five-run decode range was 10.6% of the median. Treat those numbers as context, not pass/fail thresholds.
- [Coding session 003](../../recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/003-2026-11-15-coding/summary.md): 1,846 of 1,947 requests were at least 32K tokens and about 97% of prompt tokens were reused. Returning long conversations matter more here than a short, cold prefill record.

Use the [candidate-runtime workflow](../runtimes/strata.md#compare-a-candidate-runtime) and the [baseline suite](../baseline.md). Keep the model and drafter revisions, ROCm, client, sampling settings, and request fixtures fixed. Alternate reference and candidate runs from fresh starts; warm each identically and build reuse within each run, not across runs. Record image ID, source revision, build flags, effective engine arguments and routing environment with each result. Separate cold prefill, warm time to first visible output, and decode; report medians and ranges rather than the fastest run.

## 1. Routing fidelity on the pinned engine

Set `"STRATA_ROUTE_PRIOR": "0"` in the top-level `env` object of `config/strata.json` for both arms. Zero is already the [pinned source default](https://github.com/Niko1221/Strata/blob/dbb2d168cffa8cf793d9325358809d5263c7c6b0/src/core/verify.cpp#L281-L291); it prevents GPU residency from biasing expert selection. Leave `STRATA_ROUTE_TAIL_SKIP` unset for the reference and set `"STRATA_ROUTE_TAIL_SKIP": "0"` for the candidate. Confirm from startup logs that the reference actually enables tail skipping. Turning it off computes low-ranked missed experts that would otherwise be omitted; it is not just a scheduling change.

Replay sanitized coding turns with a known expected tool name and arguments. Include multiline patches, escaped strings, nested arguments, and an instruction near the start of a long conversation. Compare parsed argument values, byte-exact file payloads where required, task success, decode speed, and draft acceptance. [Issue #5225](https://github.com/Niko1221/Strata/issues/5225) motivates the test, not a claim that disabling skipping cures malformed calls. Adopt a coding-specific setting only if repeated trials show a fidelity benefit worth the measured latency cost.

## 2. Engine and prompt kernels

Build the [v0.2.15 source tag](https://github.com/Niko1221/Strata/blob/v0.2.15/CMakeLists.txt) (`c7757280`) with its default prompt kernels, keeping the routing settings identical on both engines. The [v0.2.15 release](https://github.com/Niko1221/Strata/releases/tag/v0.2.15) distributes the [v0.2.14](https://github.com/Niko1221/Strata/releases/tag/v0.2.14) HIP engine (0.1.60), whereas the source tag declares 0.1.61. Label the result as a source build.

Compare against the pinned image at fresh 8K, 32K and 120K prompts and on the returning coding turns. If results are mixed, build the **same candidate revision** with both `-DSTRATA_MMQ=ON` and `-DSTRATA_PREFILL_MMQ=ON`. The latter alone does not select the legacy HIP kernels on the candidate. Check tool and vision output, draft acceptance, memory peaks, repeated starts, stalls and GPU resets. Promote only a repeatable workload benefit without a correctness or stability regression; otherwise retain the pin.

## 3. GPU KV residency at fixed context

Compare `--kv-resident` **32768 → 65536 → 131072**, keeping `--max-context 131072`, `--kv int8`, and `--expert-cache auto` fixed. The reference already serves 120K prompts: the question is latency, not context capacity. At 131,072 resident cells the main KV pool fits the full configured context, but fewer experts may fit on the GPU.

Prerequisite: [`configure()`](../../runtimes/strata/scripts/serve.py) rewrites residency to `min(context, 32768)`, so editing native JSON alone cannot run this test. In the experiment worktree, first test that the reference still resolves to 32,768 and a recipe-specified cap resolves to the lesser of that cap and the requested context; then implement the override. Verify the effective values in the engine startup log for each arm.

Measure KV block hits and RAM reads **alongside** allocated expert slots, expert hits, warm latency, decode, VRAM, RAM and swap. Include retrieval of an early instruction at 120K, not just successful generation. Stop increasing residency on allocation failure or memory pressure that harms serving. Keep 32,768 unless a larger pool improves the long coding turns beyond run variability.

## Community patches: conditional trials only

- [#6085, `STRATA_IQ_FAST`](https://github.com/Niko1221/Strata/pull/6085): first patch to trial **if CPU expert work is a bottleneck**. The Ryzen 7 9800X3D supports the required AVX-512 VBMI. Compare off/on in the same patched image; judge end-to-end decode, not just IQ3_XXS CPU row throughput.
- [#6176, `q4u32` KV](https://github.com/Niko1221/Strata/pull/6176): defer unless KV memory limits the winning configuration. The cited 32K result is from a Windows RX 9060 XT. Explicit `--kv int8` does not exercise the new format; test the format separately and repeat 120K retrieval and tool fidelity checks.
- [#6161, RX 9070 XT at 131K](https://github.com/Niko1221/Strata/pull/6161): benchmark evidence, not a code patch. Its Windows Gyro-S run changed eight settings together and kept 32,768 resident cells. Do not import the bundle as a Linux IQ3_XXS preset.

Publish each measured configuration as a separate recipe experiment. If no candidate earns promotion, keep the baseline runtime and recipe unchanged.
