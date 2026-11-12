# 003 · 2026-11-07 — Pi software development: gpu-switcher

One extended development session generated 660,836 tokens across 898 completed requests. Aggregate generation speed was approximately 57.1 tokens/s with 39.6% DFlash2 acceptance.

## Workload

Session #1 used Pi to work on a gpu-switcher improvement plan for a Python/GTK Linux application and its privileged helper. Planned work covered timeout/error handling, GPU detection and selection, asynchronous D-Bus/polkit operations, systemd integration, package restructuring, UX, and tooling/CI. The plan called for incremental tests, linting, type checks, and commits. These describe the intended workflow; the server log records tool calls and inference statistics, without their execution results or repository changes.

Pi issued streaming chat-completion requests to TabbyAPI with DFlash2 and GPU-resident vision enabled, a 131,072-token context/cache allocation, Q4 caches, and maximum batch size 1. Requests report top-k 20 and top-p 0.95 from server defaults and client output limits of 12,297–16,384 tokens (861 of 899 requests specify 16,384). Server temperature defaults to 1. The server reasoning budget is unset. The log does not record Pi's selected reasoning effort or whether images were submitted.

The report date follows the supplied session context; the console log records times of day only. Hardware and build details in the profile follow the existing workstation recipe, with startup settings checked against this log.

## Statistics

| Session | Requests started | Completed | Cancelled | Generated tokens | Aggregate generation tokens/s | Aggregate fresh-prefill tokens/s |
|---|---:|---:|---:|---:|---:|---:|
| #1 | 899 | 898 | 1 | 660,836 | 57.1 | 738.9 |

Statistics include completed requests of all response lengths. Request #139 was cancelled after a client disconnect and has no completion metrics; it is excluded from token and timing totals. Generated tokens combine all reported output, including reasoning and tool-call content; the log provides no separate counts for those categories.

Aggregate generation speed is total output tokens divided by the sum of output tokens / logged generation rate. It is approximate because those rates are rounded. Aggregate prefill speed uses fresh input tokens divided by logged prefill time, excluding reused tokens from the numerator.

| Metric | Value |
|---|---:|
| Sum of completed request durations | 3 h 56 min 21 s |
| Fresh input tokens processed | 1,814,513 |
| Sum of prompt tokens across completed requests | 64,808,177 |
| Reused prompt tokens (prompt minus fresh input) | 62,993,664 |
| Aggregate prompt reuse | 97.2% |
| Fresh-prefill time | 2,455.82 s |
| Median generation speed | 59.6 tokens/s |
| Generation speed range | 30.9–127.4 tokens/s |
| Median / maximum first-token latency | 1.90 / 107.70 s |
| Actual prompt length range | 390–114,693 tokens |
| Accepted / proposed draft tokens | 485,656 / 1,226,260 |
| Draft acceptance | 39.6% |
| Largest completed output | 12,148 tokens |

Cumulative prompt counts count reused prefixes again for each request; they do not describe resident context size.

Context below is prompt length at request start, with 1K = 1,024 tokens.

| Context range | Completed requests | Generated tokens | Median generation tokens/s | Aggregate generation tokens/s |
|---|---:|---:|---:|---:|
| Below 32K | 25 | 20,516 | 77.6 | 77.3 |
| 32–64K | 343 | 250,545 | 66.8 | 65.2 |
| 64–96K | 378 | 263,656 | 55.7 | 54.7 |
| 96–128K | 152 | 126,119 | 50.1 | 47.5 |

## Tool use and continuity

The server logged 920 emitted tool calls: 534 `bash`, 209 `edit`, 153 `read`, and 24 `write`. Emission does not establish successful execution or passing tests.

Fourteen consecutive completed-request pairs show prompt reductions greater than 20,000 tokens. Several occur around 110K–115K input tokens, consistent with compaction or conversation changes. The server log alone does not identify their cause. Cache reuse remained 97.2% across completed requests overall.

The session ended with a graceful shutdown and model unload. Alongside the client cancellation, there were two invalid-HTTP-request warnings. The supplied log contains no ERROR-level entries or reported GPU out-of-memory failures.

## Observations

- Generation slowed with larger prompts: aggregate speed was 77.3 tokens/s below 32K and 47.5 tokens/s at 96–128K. Request content also differed across these groups.
- The three longest outputs contained 12,148, 11,517, and 11,199 tokens and took approximately 225, 191, and 302 seconds respectively. All completed outputs were below their respective requested output limits.
- The plan's milestone completion, test outcomes, code quality, and usefulness require the Pi transcript or resulting code. Device/process memory, power, and temperature were not recorded in this session log.

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml)
