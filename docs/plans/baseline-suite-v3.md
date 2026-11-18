# Baseline suite v3: comparable local inference

Keep one command per configuration:

```bash
python3 scripts/run_baseline.py run <recipe>
```

Use the existing launch and desktop attach flows. The runner chooses workloads from the recipe's configured context and writes the comparison metrics into the existing `summary.md` and `results.json`. A container candidate uses the same command from its own worktree. [Baseline runner](../baseline.md#run-a-baseline) · [Candidate runtime workflow](../runtimes/strata.md#compare-a-candidate-runtime)

The baseline answers three questions for a single active user: how long a fresh prompt takes, how long a returning turn takes, and how fast the server generates once it starts. The existing functional checks and active RAM/VRAM measurements provide context for those numbers.

## Research and implications

| Reference | Practice to adopt |
|---|---|
| [llama.cpp llama-bench](https://github.com/ggml-org/llama.cpp/blob/master/tools/llama-bench/README.md) | Fix input and output sizes within each case, time prompt processing and generation separately, and repeat measurements. Keep the baseline's client timings as the common measurements across engines. |
| [vLLM serving benchmark](https://docs.vllm.ai/en/latest/cli/bench/serve/#prefix-repetition-dataset-options) | Exercise prefix reuse with controlled shared prefixes and new suffixes. Keep warmup separate and run one request at a time for the workstation use case. |
| [NVIDIA AIPerf metric definitions](https://docs.nvidia.com/nim/benchmarking/llm/latest/metrics.html) | Distinguish first output, generation pace, and total request latency. Time to first output includes client and server overhead. Label engine prefill separately when logs provide it. |

The current suite already has five 8K samples, two 120K samples, and request-level timings. Its reuse ladder exercises about 1K tokens, and first visible text is only aggregated for the reasoning case. The Strata coding log puts 1,846 of 1,947 requests at 32K or more, with roughly 97% of input reused across the session. Use a 64K replay where it fits. On the reference Strata setup, that exceeds the 32,768 GPU-resident KV cells and can expose differences in KV streaming during returning turns. [Current suite](../baseline.md#what-a-run-measures) · [Strata coding results](../../recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/003-2026-11-15-coding/summary.md)

## 1. Extend an existing cold case into a long replay

- Keep the v2 8K, 32K, 64K and 120K cold cases, their repeat counts, and their output caps. Choose one replay size before running the cold cases: prefer 64K, fall back to 32K, then use the existing short conversation ladder. Immediately after the selected cold code-review request, send one exact replay at the original output cap and two fixed follow-ups capped at 256 tokens each. Use the identical first user message, including its run-specific nonce, within this sequence. Give the follow-ups a fixed assistant reply and different user suffixes. Generated output must never become fixture input.
- Reuse the seed already fitted by the existing tokenizer or calibrated estimate. Before replay, check that the follow-ups fit with chat framing and output reserved. Preflight the full message lists where the count endpoint supports them. Leave headroom for estimated counts and flag reported truncation or context rejection. Allow for input, chat framing, and output when selecting the tier. Report which path ran and why. If the fitted messages still cannot fit, use the short ladder and record the fallback.
- Keep text generation policy the same for both images, including thinking controls. Keep the existing short tool and vision checks as separate functional results. Measure the replay by client clocks and server usage. Keep the usual per-request timeout and retain partial output when a case fails.
- An exact cold/replay pair has the same prompt and output cap. Report it separately from the two follow-ups, since the latter have different suffixes and may do different amounts of fresh work. When cache counts are unavailable, show both latencies and leave reuse unconfirmed. Warm requests on an engine without reuse still provide a valid latency measurement.

## 2. Put the comparison in the run summary

Show a compact table above the existing case detail. Include the 8K repeated case, long cold case (120K when it fits), selected 64K or 32K cold/replay pair, and returning follow-ups. Show actual input tokens for each tier. Compare warm results within the same tier.

- Show reported input and output counts, number of successful samples, client time to first output, time to first visible text where available, and client decode rate. Add cached input where the server reports it. Extract first-visible timing from the request records already written by the runner. Use a median and observed range for repeated samples. Label a one-sample result and report short or interrupted outputs with their status.
- Keep engine prefill, draft acceptance, and telemetry in the detailed report. Show peak system RAM and device VRAM with their existing scopes. Unavailable values retain the existing reason field.
- For a runtime A/B, compare matching case IDs, suite versions, model and quant, actual token counts, policy and hardware. Alternate fresh runs again when the gap is within the observed range. Across models, interpret tok/s in the context of each tokenizer and use client latency on equivalent tasks alongside rates. The existing token-fitted corpus can produce different text lengths, so use the same host Python version, show actual token counts, and retain the recorded case content IDs for checking identical workloads where relevant. Avoid a composite score.

## 3. Version and verify

1. Reuse the request, aggregation, and rendering paths in `scripts/baseline/`. Bump `suite_version` to `3`. Keep the existing result schema if its optional fields suffice. Render stored v1/v2 reports without synthesizing v3 metrics or changing their generated blocks.
2. Add focused fixture or fake-server tests for the exact replay, fixed follow-ups, and automatic 64K, 32K, and short-context selection. Check aggregation with missing cache counters and visible text following reasoning. Verify existing results still render and pass the generated-document check.
3. On the workstation, run the unchanged command on Strata and one other API path, such as TabbyAPI or LM Studio. Check the first prompt is fresh, verify reuse where observable, and confirm both reports expose the same client fields. Compare end-to-end suite time with v2. The selected cold case also seeds the replay. If cache misses add material run time, shorten or drop a follow-up before expanding the suite.
4. Update the baseline guide's suite table and workload description. Use the Strata pinned/candidate pair as the first decision made from the new report.
