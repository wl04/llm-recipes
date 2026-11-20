# Baseline suite v3: comparable local inference

Keep one command per configuration:

```bash
llm-recipes-baseline run <recipe>
```

Use the existing launch and desktop attach flows. The runner chooses workloads from the recipe's configured context and writes the comparison metrics into the existing `summary.md` and `results.json`. A container candidate uses the checkout entry point from its own worktree. [Baseline runner](../baseline.md#run-a-baseline) · [Candidate runtime workflow](../runtimes/strata-upgrade.md#4-measure-the-upgrade)

The baseline answers three questions for a single active user: how long a fresh prompt takes, how long a returning turn takes, and how fast the server generates once it starts. The existing functional checks and active RAM/VRAM measurements provide context for those numbers.

## Research and implications

| Reference | Practice to adopt |
|---|---|
| [llama.cpp llama-bench](https://github.com/ggml-org/llama.cpp/blob/master/tools/llama-bench/README.md) | Fix input and output sizes within each case, time prompt processing and generation separately, and repeat measurements. Keep the baseline's client timings as the common measurements across engines. |
| [vLLM serving benchmark](https://docs.vllm.ai/en/latest/cli/bench/serve/#prefix-repetition-dataset-options) | Exercise prefix reuse with controlled shared prefixes and new suffixes. Keep warmup separate and run one request at a time for the workstation use case. |
| [NVIDIA AIPerf metric definitions](https://docs.nvidia.com/nim/benchmarking/llm/latest/metrics.html) | Distinguish first output, generation pace, and total request latency. Time to first output includes client and server overhead. Label engine prefill separately when logs provide it. |

## Implementation status

- [x] Suite v3 replays the selected cold prompt and two fixed follow-ups. It selects 64K, 32K, or the short conversation automatically.
- [x] The report shows client timing, cached tokens when available, and the observed range for repeated samples. The renderer preserves stored v1/v2 reports.
- [x] CPU tests cover replay selection, fixed follow-ups, and reports with missing cache counts. The [baseline guide](../baseline.md#what-a-run-measures) documents the current suite.

The documented Strata coding session puts 1,846 of 1,947 requests at 32K or more, with about 97% of input reused. A 64K replay exceeds the reference recipe’s 32,768 GPU-resident KV cells, so it can expose differences in KV streaming during returning turns. [Strata coding results](../../recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/003-2026-11-15-coding/summary.md)

## Workstation validation

1. Run v3 on Strata and one other API path, such as TabbyAPI or LM Studio. Verify the seed was fresh and check reuse where the server reports it. Confirm both reports expose the same client fields.
2. Compare total suite time with v2. Check how much time the follow-ups add on engines that miss the cache.
3. Use the [Strata reference and candidate](../runtimes/strata-upgrade.md) as the first A/B. Match replay tier, suite version, model, quantization, actual token counts, request policy, and hardware. Repeat in alternating order when the difference is within observed variation. Compare client latency on equivalent tasks alongside token rates when tokenizers differ.
