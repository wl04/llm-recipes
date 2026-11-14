# Unified baseline runner implementation plan

## Goal

Provide one command that checks a running recipe, exercises sustained workloads, samples resources throughout requests, and produces a concise standalone result. Reuse the existing doctor checks and server integrations. Support Strata, ExLlamaV3/TabbyAPI, and the LM Studio desktop recipe through the same workload and reporting conventions.

The runner attaches to an already prepared, running server. Downloads, conversion, image builds, and server lifecycle remain in the existing setup workflow. Raw outputs stay in a user-selected external directory; experiment profiles and summaries remain the repository's durable records.

## User-facing workflow

Proposed CLI, finalized during the first implementation stage:

```bash
python3 scripts/baseline.py run <recipe> \
  --instance strata-coding \
  --output "$HOME/Models/llm-recipes/baselines/<run-name>"
```

For a desktop server:

```bash
python3 scripts/baseline.py run <desktop-recipe> \
  --base-url http://127.0.0.1:<port>/v1 \
  --model <served-model-id> --context <tokens> \
  --pid <server-pid> --gpu-pci <pci-address> \
  --output <external-directory>
```

Allow explicit endpoint, model, context, GPU, and telemetry overrides for either mode. Add offline report rendering from a completed or interrupted run so presentation changes do not require repeating inference. Keep `launch.py doctor` available independently.

The command performs preflight, starts monitoring, records an idle reference, warms the server, runs functional and performance workloads, closes monitoring, and writes a report. Show progress on stderr and a short result/location message on completion. Partial outputs survive interruption. Ctrl+C stops the runner and its monitoring children; it does not stop the user's server.

## Architecture

Use a small Python entry point with separate modules for orchestration, API adapters, resource sampling, and report rendering. Reuse recipe/runtime discovery and the doctor's individual findings. Extract reusable request and response handling from the current check helpers instead of invoking those helpers as opaque subprocesses.

| Component | Responsibility |
|---|---|
| CLI | Arguments, progress, exit status, output location |
| Runner | Workload order, warmup, repetitions, deadlines, cancellation |
| Server adapter | Readiness, model identity, token counting, requests, cache controls, timing normalization |
| Host sampler | CPU, memory, swap, GPU telemetry, sample coverage |
| Result writer | Incremental structured records and final report |
| Workload assets | Versioned prompts, documents, baseline screenshot, expected functional outcomes |

API servers remain distinct from inference engines. Use shared OpenAI-compatible request handling where possible, with explicit TabbyAPI, Strata, and LM Studio capability handling. Keep native configuration files native. Desktop recipes receive no container manifests or image requirements.

Discover actual capabilities at implementation time against the pinned servers. In particular, verify streaming usage/timing fields, reasoning controls, token-count endpoints, cancellation, and cache controls. Mark unsupported measurements unavailable; do not infer them from unrelated timings.

## Workloads

Start with concurrency one and three measured repetitions per performance case. Use one excluded warmup for each workload shape where compilation or allocation may differ. Record warmup duration and resources separately.

| Stage | Initial specification | Output |
|---|---|---|
| Functional | Streaming text, forced tool call plus fixed tool result, shared screenshot | Completion/error status; tool validation; vision answer for manual review |
| Sustained generation | A small fixed set of substantial coding tasks; up to 2,048 output tokens | Actual output length, latency, rate, resource summary |
| Context scaling | Approximately 8K, 32K, 64K, and 120K input; up to 1,024 output tokens | Performance/resource summary at actual token counts |
| Conversation reuse, second increment | Follow-up requests on an existing context | Cached input, incremental prefill and response behavior |

Use realistic code/document text with clear licensing and deterministic construction. Retain synthetic records as an explicitly named capacity workload if useful. Prompt content affects speculative acceptance, so record the workload version and prompt hashes in local results.

Use the same prompt corpus across recipes. Different tokenizers produce different input counts; store the actual count and the requested budget. Clip or skip cases that cannot fit input plus output within the configured context, recording the reason. Account for chat-template and tool-schema overhead through the server tokenizer where available.

A token cap is not a guaranteed response length. Report finish reasons and actual lengths. Establish a minimum observed output length for sustained-generation cases during the workstation pilot (initial candidate: 512 tokens). Mark shorter replies as insufficient samples; retain them in raw results without silently retrying until a favorable result appears. Avoid forcing endless generation merely to satisfy a timing target.

Keep functional checks brief and summarize them separately. Do not execute arbitrary generated code. Vision checks use `assets/checks/amdgpu-top.png`, with an optional override and image hash. Readable text in `docs/vision-check.md` supports manual review rather than an automatic claim of image understanding.

### Sampling and cache policy

Define and record an explicit request policy for the baseline rather than inheriting unknown server defaults. Initial candidate: temperature 1, top-k 20, top-p 0.95, min-p 0, repetition penalty 1, presence penalty 0, and thinking disabled. Validate that each server accepts and applies the settings. Record unsupported fields and effective settings; do not claim deterministic outputs across engines. A seed may aid repeatability where supported but does not guarantee it.

Keep reasoning-enabled coding evaluation as a separately identified workload. Its reasoning budget and effort must be captured, and reasoning tokens included or separated according to API reporting.

Separate warmed execution from cached prompts. Fresh-context cases should disable or clear prefix reuse using supported controls and verify cached-token counts. When controls or counters are absent, record cache state as unknown. A changed prompt nonce alone is not proof of a cold cache. Cached follow-ups belong to their own workload. Cache clearing requires an explicit dedicated-server run; avoid changing an active coding session's state implicitly.

## Continuous resource measurement

Begin sampling before warmup and keep it active through the final response. Use a monotonic clock for samples and request boundaries; retain wall-clock metadata only in external run artifacts. Join samples to workload/repetition intervals and calculate time-weighted averages over active requests, excluding idle pauses and token-count preparation calls.

Start with a 500 ms sampling interval. Validate overhead and sample coverage on the workstation. A short pre-run and post-run idle reference helps explain retained allocations, but the primary statistics describe active requests. Mark first-output boundaries when streaming allows it; label these as waiting-for-first-output and streaming intervals, not exact engine prefill/decode phases.

| Metric | Preferred source | Definition and caveat |
|---|---|---|
| Container CPU | cgroup v2 `cpu.stat` deltas | CPU seconds divided by wall seconds, expressed as average cores consumed |
| Container RAM | `memory.current`, `memory.stat` | Total charged memory plus anonymous/file-cache breakdown; not process RSS |
| Container swap | `memory.swap.current` | Occupancy and change during the workload |
| Desktop process CPU/RAM | `/proc` process tree, optionally psutil | Track server workers; sum CPU; use PSS where readable to avoid shared-memory double counting, otherwise clearly label RSS |
| System RAM | `/proc/meminfo` | Minimum available RAM and sampled system-used memory with formula recorded |
| System swap activity | `/proc/vmstat` counter deltas | Swap-in/out activity; distinct from swap occupancy |
| GPU memory | `amdgpu_top` JSON | Device VRAM/GTT, process allocations where readable |
| GPU load/power/temperature | `amdgpu_top` JSON; AMD sysfs fallback | Active-period average and sampled maximum, with units |

Resolve a container through launcher labels and inspect its host PID/cgroup. Resolve the GPU by PCI address, not adapter enumeration order; this workstation also has an iGPU. For process monitoring, guard against PID reuse and worker changes. Record telemetry tool versions and detected devices.

Use one long-lived `amdgpu_top --json` process with a configured interval instead of repeatedly starting a TUI. Probe the installed JSON schema and PCI-selection options. AMD sysfs can provide a smaller fallback when the utility is absent. Avoid parsing interactive `top` output.

Treat container and device metrics as different scopes. Do not add RSS, cgroup charges, pinned memory estimates, and VRAM together. Driver-accounted allocations and file mappings can have subtle accounting behavior. Record sample count, gaps, and collection errors. A missing permission or sensor produces an unavailable metric, not zero.

Report sampled peaks honestly; polling can miss transient spikes. Cgroup `memory.peak` may include activity before the run and must not be labeled a workload peak unless its interval is established. Do not reset shared counters as a side effect. Validate attribution and monitoring overhead before interpreting small performance differences.

## Timing and statistical definitions

Capture client request duration and time to first nonempty streamed output using a monotonic clock. Record actual input/output counts, cached input, finish reason, failures, and truncation. Capture engine-reported prefill/decode duration and draft accepted/proposed counts when available.

- Keep client timing and engine timing in separate fields with their measurement source.
- Do not calculate prefill speed from time to first token; queueing, image encoding, and other work can be included.
- Do not treat one streamed chunk as one token. Report chunk timing only as chunk timing; derive token-normalized client estimates only when token counts and boundaries support the formula, and label estimates distinctly.
- Report median and min–max across three repetitions. Three observations do not justify a tail-latency claim such as p99.
- Aggregate engine throughput is total applicable tokens divided by total applicable engine time. Draft acceptance is total accepted divided by total proposed for the same covered requests.
- Preserve failed and short requests in results. Summaries state included/excluded counts and reasons.

## Output and repository documentation

Use a schema version and a workload-suite version. Write metadata, request results, and resource samples incrementally into a new external output directory. Refuse to overwrite another run. Store request/phase identifiers and units explicitly so offline rendering is reliable.

Capture the repository revision and relevant file hashes, recipe identity, served model ID, actual context, host hardware/OS, runtime/model lock identities, sampling, image-token settings, and monitoring versions. Distinguish checked-in configuration from verified runtime state. Existing doctor checks only establish local image availability; they do not prove the running image's embedded build lock. Record running image identity and verification status separately.

The report contains:

1. Workload and effective configuration, with missing data stated.
2. A compact functional outcome list.
3. One row per sustained workload/context: repetitions, actual output count, median first-output latency, engine generation/prefill rates where available, and timing range.
4. A resource table by workload: average CPU cores, peak container/process RAM, minimum system-available RAM, peak device VRAM/GTT, and swap activity.
5. Observations about truncation, resource pressure, errors, and sample coverage.

Keep reports standalone. Cross-recipe comparisons and charts can later consume the structured files. Do not insert comparisons into individual experiment reports or publish raw logs automatically.

Generate a draft `summary.md` and profile data in the external directory for review. Promote the confirmed snapshot into `recipes/<recipe>/NNN-YYYY-MM-DD-description/`, then run the existing configuration/index generator. Do not overwrite historical profiles or infer unknown runtime settings. Keep the result template usable for manually recorded experiments as well as baseline runs.

## Delivery stages

### 1. Define contracts and prove API support

- Inventory current doctor and generation helpers and reuse their validation behavior.
- Specify result records, units, missing-data representation, capability flags, workload versioning, and CLI exit codes.
- Collect small mocked response fixtures for all three API servers, including streaming, error, tool, and token-count responses.
- Verify telemetry availability on the target host and identify the RX 9070 XT and container cgroups.

Acceptance: each proposed metric has a defined source or explicit unavailable state; fixture tests demonstrate request/response handling without Docker or a GPU.

### 2. Implement monitoring and the initial unified suite

- Build the orchestrator with preflight, warmup, sustained text/context workloads, functional checks, and bounded requests.
- Implement concurrent CPU/RAM/GPU sampling and incremental output writing.
- Add offline report generation and interruption cleanup.
- Keep server configuration and lifecycle under the existing launcher.

Acceptance: a fake-server integration test exercises a full run, injected errors, cancellation, sample attribution, and partial-report rendering. Monitoring starts before requests and continues while requests block. No server shutdown or model-file mutation occurs.

### 3. Validate on the workstation and unify documentation

- Pilot Strata ISTA and Unsloth, then ExLlamaV3/TabbyAPI and LM Studio.
- Compare sampled measurements with live tools; validate memory scope, CPU units, PCI selection, and cache classification.
- Run matched cases with monitoring enabled/disabled to quantify observer overhead.
- Confirm the proposed lengths, repetition counts, and context matrix yield useful durations without exhausting memory. Record actual suite duration before documenting an estimate.
- Replace setup-guide validation blocks with the unified command. Update runtime/client instructions, authoring guidance, and templates.
- Retain small compatibility wrappers for existing check commands during migration if needed; remove duplicate request logic once the new path is verified.

Acceptance: each recipe can produce a standalone baseline with comparable metric definitions and clearly marked gaps. Historical results remain unchanged. Workstation validation is reported separately from CPU-only CI.

### 4. Add representative conversation reuse

- Add a fixed multi-turn coding conversation with realistic tool-result text.
- Report fresh versus reused prompt processing and resource behavior separately.
- Add reasoning-enabled evaluation only with verified effort/budget mappings.

Acceptance: cache reuse is observable or explicitly unknown, and workload changes receive a new suite version. A later comparison page can consume completed runs without changing their reports.

## Tests and completion checklist

Use behavior-focused tests for counter deltas, timestamp alignment, sample gaps, missing sensors, changing processes, cache classification, partial streams, early EOS, malformed responses, mismatched model IDs, and cancellation. Test report calculations with known values and preserve unavailable metrics through serialization. Verify that outputs never mix progress messages with JSON.

Run `bash scripts/check.sh`, which includes generated-document validation. Check setup examples and local links. Add required development dependencies to the existing pinned dependency workflow; document any host monitoring dependency. Keep automated tests CPU-only and deterministic.

The initial implementation is complete when one command produces useful sustained measurements and an actionable standalone report for the supported recipes, captures resources while requests execute, retains partial diagnostics on failure, and leaves publication under user control.

## Research references

- [amdgpu_top usage and JSON mode](https://github.com/Umio-Yasuno/amdgpu_top#usage): continuous telemetry, PCI selection, and sampling interval.
- [Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): CPU, memory, peak, and swap accounting.
- [AMDGPU monitoring interfaces](https://docs.kernel.org/gpu/amdgpu/thermal.html): utilization, temperature, and power sensors.
- [Docker stats](https://docs.docker.com/reference/cli/docker/container/stats/): memory/cache accounting distinctions and container statistics.
- [llama-bench](https://github.com/ggml-org/llama.cpp/tree/master/tools/llama-bench): warmup, repeated measurements, and context-depth workloads.
- [vLLM serving benchmark](https://github.com/vllm-project/vllm/blob/main/vllm/benchmarks/serve.py): separate first-token, output-token, and end-to-end latency metrics.
