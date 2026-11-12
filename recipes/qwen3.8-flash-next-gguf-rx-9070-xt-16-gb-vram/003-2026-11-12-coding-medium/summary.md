# 003 · 2026-11-12 — Long coding session in Pi

## Workload

Interactive software development in Pi using Strata with IQ3_XXS weights, MTP drafting, CPU vision enabled, and a 131,072-token context allocation. The session contains 846 completed coding requests. The six preceding text, tool, vision, and synthetic long-context checks are excluded from these measurements.

Thinking was active, with Pi effort set to **Medium** throughout the session. The server usually reserved 12,288 tokens for reasoning within a 16,384-token output allowance, using its automatic answer-room behavior. Both allowances were smaller on some requests. The Pi version was not recorded. Sampling values in the configuration snapshot are server defaults; requests can override them.

## Results

| Metric | Observed value |
|---|---:|
| Completed coding requests | 846 |
| Generated tokens | 599,207 |
| Newly processed prompt tokens | 1,310,196 |
| Reused prompt tokens | 62,147,968 |
| Prompt reuse | 97.9% |
| Aggregate prefill speed | 1,799.5 tok/s |
| Aggregate generation speed | 93.8 tok/s |
| Median request generation speed | 94.1 tok/s |
| Request generation speed, 10th–90th percentile | 82.5–110.8 tok/s |
| Request generation speed, minimum–maximum | 75.2–132.4 tok/s |
| Accepted / proposed drafts | 378,175 / 549,767 (68.8%) |
| Largest input context | 114,651 tokens |
| Requests finishing with stop | 846 |
| Requests finishing at the output cap | 0 |
| Cancelled requests | 0 |

Aggregate speeds divide total tokens by total engine time for the corresponding phase; prefill counts only newly processed tokens. Prompt reuse divides reused tokens by all prompt tokens across requests, including repeated conversation history. Draft acceptance divides accepted drafts by proposed drafts. Percentiles describe individual request generation rates.

### Performance by input context

| Input tokens | Requests | Aggregate generation | Draft acceptance |
|---|---:|---:|---:|
| Below 32,768 | 20 | 101.4 tok/s | 71.4% |
| 32,768–65,535 | 307 | 97.2 tok/s | 70.9% |
| 65,536–98,303 | 335 | 92.0 tok/s | 67.7% |
| 98,304 and above | 184 | 90.1 tok/s | 66.2% |

The context groups contain different requests and output lengths. Their rates describe the observed workload rather than an isolated measurement of context-length effects.

## Observations

Generation remained between 75.2 and 132.4 tok/s throughout the recorded coding requests. Draft acceptance remained 66.2% in aggregate for requests above 98,304 input tokens.

The engine and server logs contain matching completion records for all 846 coding requests, with no reported errors or tracebacks. Completion status measures request handling; code correctness was not scored.

Several large context reductions followed prompts around 113,000–115,000 tokens. These are consistent with compaction or conversation resets; the logs do not identify the Pi action responsible for each reduction.

The prefill aggregate includes many small additions to cached conversation history. The [initial long-context check](../001-2026-11-12-initial-checks/summary.md) instead processed a fresh synthetic prompt, so its prefill rate represents a different workload.

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml)
