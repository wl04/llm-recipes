# Unified baseline runner implementation plan

## Goal

Provide one command that checks a running recipe, exercises sustained workloads, samples resources throughout requests, and produces a concise standalone result. One execution per recipe documents that recipe's baseline. Reuse recipe metadata and extract request handling from the existing Strata check helpers. Support Strata, ExLlamaV3/TabbyAPI, and the LM Studio desktop recipe through the same workload and reporting conventions.

Baseline experiments eventually replace each recipe's initial text, tool, vision, and long-context experiments. Coding-session experiments stay hand-written.

The runner attaches to an already prepared, running server. Downloads, conversion, image builds, and server start/stop remain in the existing setup workflow. Raw outputs stay in a user-selected external directory; experiment profiles and summaries remain the repository's durable records.

The intended conditions are a freshly rebooted machine, the server started by the user, and nothing else running. The runner records the actual conditions instead of requiring them.

## User-facing workflow

Proposed CLI, finalized during the first implementation stage:

```bash
python3 scripts/run_baseline.py run <recipe> \
  --instance strata-coding \
  --output "$HOME/Models/llm-recipes/baselines/<run-name>"
```

For a desktop server:

```bash
python3 scripts/run_baseline.py run <desktop-recipe> \
  --base-url http://127.0.0.1:<port>/v1 \
  --model <served-model-id> --context <tokens> \
  --pid <server-pid> --gpu-pci <pci-address> \
  --output <external-directory>
```

Allow explicit endpoint, model, context, GPU, and telemetry overrides for either mode. Add offline report rendering from a completed or interrupted run so presentation changes do not require repeating inference. Keep `launch.py doctor` available independently.

Desktop recipes have no `config/launch.json` or runtime manifest, so the current recipe discovery does not find them. The runner resolves a desktop recipe by folder name for identity, output naming, and later profile promotion, and takes the endpoint and process details from options. It does not require launcher manifests or container images for them.

The command performs preflight, starts monitoring, records an idle reference, runs functional checks, warms the server, runs the workloads in a fixed order, closes monitoring, and writes a report. Show progress on stderr and a short result/location message on completion. Partial outputs survive interruption. Ctrl+C, SIGTERM, and runner crashes stop the runner's monitoring children; none of them stops the user's server. An interrupted request may keep generating server-side; the report notes the interruption.

## Architecture

Use a small Python entry point with separate modules for orchestration, API adapters, resource sampling, and report rendering.

The existing doctor validates host prerequisites only (Docker, local image, model files, configuration, devices) and needs `--models`; it never contacts a server and is not used as the running-server preflight. The preflight is new: readiness, model identity, capability probing, boot state, and a quiet-system check. The reusable request code is in `runtimes/strata/scripts/check_generation.py` (SSE reading with usage, tool-call validation, token counting through the Anthropic route). Extract the generic request and stream handling into shared code instead of invoking those helpers as opaque subprocesses; leave Strata-specific checks in place until the new path is verified.

| Component | Responsibility |
|---|---|
| CLI | Arguments, progress, exit status, output location |
| Runner | Workload order, warmup, deadlines, cancellation |
| Server adapter | Readiness, model identity, token counting, requests, cache controls, timing normalization |
| Host sampler | CPU, memory, swap, GPU telemetry, sample coverage |
| Result writer | Incremental structured records and final report |
| Workload assets | Versioned prompts, tool schemas, baseline screenshot, expected functional outcomes |

API servers remain distinct from inference engines. Use shared OpenAI-compatible request handling where possible, with explicit TabbyAPI, Strata, and LM Studio capability handling. Keep native configuration files native.

Concurrency model: the main thread issues blocking requests; sampler threads and monitoring child processes run beside it and timestamp samples with the monotonic clock on receipt. Every request has its own deadline in addition to a total run deadline. Specify the model, exit codes, and shutdown behavior in stage 1.

Discover actual capabilities at implementation time against the pinned servers. In particular, verify streaming usage/timing fields, reasoning controls, token-count endpoints, cancellation, and cache controls. Mark unsupported measurements unavailable; do not infer them from unrelated timings.

## Workloads

Run at concurrency one in a fixed order, recorded in the results, because state carries over between workloads (expert cache, parked conversations, prompt caches, GPU clocks): functional checks, warmup, 8K context with the noise probe, sustained generation, then 32K, 64K, and 120K context. Every case is one measured run, except the 8K noise probe.

| Stage | Initial specification | Output |
|---|---|---|
| Functional | Streaming text, forced tool call plus fixed tool result, shared screenshot | Completion/error status; tool validation; vision field scores with the answer retained |
| Warmup | Short request repeated until two consecutive results agree within a tolerance, up to a maximum count | Number of requests, duration, convergence status, resources, reported separately |
| 8K context, noise probe | About 8K input; up to 1,024 output tokens; five requests with distinct content | Median result, plus the run's noise floor |
| Sustained generation | A small fixed set of substantial coding tasks, each run once; up to 2,048 output tokens | Actual output length, latency, rate, resource summary per task |
| Context scaling | Approximately 32K, 64K, and 120K input; up to 1,024 output tokens | Performance/resource summary at actual token counts |
| Conversation reuse (stage 4) | Follow-up requests on an existing context | Cached input, incremental prefill and response behavior |

### Warmup and noise

One adaptive global warmup follows the functional checks. Server-side first-use costs (page-in of memory-mapped model files after a reboot, kernel or shader loading, allocator growth, expert-cache fill, GPU clock ramp-up) are per process, not per workload shape, so warmup per context size is unnecessary and the large sizes are too expensive to repeat. Warmup tolerance and the maximum count are set in the pilot. If warmup does not converge, record that and continue. Record warmup duration and resources separately.

The first request at each larger context size may still include one-time allocation growth. Keep it in the results as a single observation; do not exclude or repeat it. Report single observations as n=1 without a median or range.

The 8K case runs five requests, which serves as the automated noise estimate for the run. Report the 8K result as the median, and state the noise floor as the relative spread (max minus min over median) of first-output latency and client decode rate. Caveats stated in the report:

- It measures noise at 8K, not at 120K, where memory pressure and thermals can matter more.
- Five samples give only a rough spread estimate, not a confidence interval.
- The spread includes output-content variation at temperature 1; that variation is intended.
- Rates, not total durations, are used because output length varies.

Do not repeat expensive cases to estimate noise. Differences smaller than the run's noise floor are not distinguishable.

### Prompt construction

Use realistic code/document text with clear licensing and deterministic construction. Check in small assets (screenshot, tool schemas, coding task prompts). Build the long contexts deterministically from pinned, clearly licensed text at run time rather than checking in half-megabyte documents, and record source hashes. Retain synthetic records as an explicitly named capacity workload if useful. Prompt content affects speculative acceptance, so record the workload version and prompt hashes in local results.

Use the same corpus across recipes. Different tokenizers produce different input counts; store the actual count (from reported usage) and the requested budget. Clip or skip cases that cannot fit input plus output within the configured context, recording the reason.

Size prompts without a generation request over the measured prompt: a prefill-only count request would warm the cache for the measured request. Use a token-count endpoint where it exists (TabbyAPI tokenizer endpoint, Strata Anthropic route), otherwise a local tokenizer matching the model, otherwise a characters-per-token ratio calibrated from earlier cases' reported usage (for example the 8K case). Account for chat-template and tool-schema overhead through the server tokenizer where available. Exclude counting calls from resource statistics.

Warmup, noise-probe requests, and measured cases use distinct content of the intended length, with a unique leading section to avoid prefix matches.

A token cap is not a guaranteed response length. Report finish reasons and actual lengths. Establish a minimum observed output length for sustained-generation cases during the workstation pilot (initial candidate: 512 tokens) and record it in the suite version. Mark shorter replies as insufficient samples; retain them in raw results without silently retrying until a favorable result appears. Avoid forcing endless generation merely to satisfy a timing target.

Keep functional checks brief and summarize them separately. Do not execute arbitrary generated code. Vision checks use `assets/checks/amdgpu-top.png` for every recipe, with an optional override and the image hash recorded.

Score the vision answer against expectations stored next to the image in `assets/checks/amdgpu-top.expected.json`:

- The prompt asks for fixed fields (application and version, GPU model, architecture, device VRAM used/total, device GTT used/total, process name and its VRAM) as a JSON object. Free-form description is harder to score and the output cap can cut it short. Extract the first JSON object leniently; an unparseable answer is recorded as unparsed, with the answer text kept.
- Each expectation has an id, a tier, and accepted spellings normalized for case, whitespace, and thousands separators. Tier `identity` holds the application and GPU model. Tier `detail` holds the numbers, architecture, and process fields.
- Each field is scored `match`, `mismatch` (a different value, such as a misread), or `missing`. The report shows counts per tier and the per-field table.
- The functional outcome passes when all `identity` fields match. `detail` scores are informational and do not fail the run. Earlier results show that small on-screen text depends strongly on the image-token budget: at 300 tokens the models recognized the application but invented panel names, while 1,024 tokens read the details correctly. Report the image-token setting beside the scores, and compare scores only at equal settings.
- Record the expectations file hash and version. Changing the image, prompt, or expectations bumps the workload-suite version.
- Generate the value table in `docs/vision-check.md` from the expectations file, or replace it with a link, so there is one source of truth.
- The scores are a text-matching check on one screenshot, not a general claim of image understanding.

### Sampling and cache policy

Define and record an explicit request policy for the baseline rather than inheriting unknown server defaults. Performance workloads: temperature 1, top-k 20, top-p 0.95, min-p 0, repetition penalty 1, presence penalty 0, and thinking disabled. This is realistic but makes output length and speculative acceptance vary between runs, which the noise probe measures. Functional checks use temperature 0 with thinking disabled, like the existing helpers, so a forced tool call does not become flaky. Validate that each server accepts and applies the settings. Record unsupported fields and effective settings; do not claim deterministic outputs across engines. A seed may aid repeatability where supported but does not guarantee it.

Keep reasoning-enabled coding evaluation as a separately identified workload. Its reasoning budget and effort must be captured, and reasoning tokens included or separated according to API reporting.

Separate warmed execution from cached prompts. Verify cached-token counts where the server reports them, and record cache state as unknown when controls or counters are absent. A changed prompt nonce alone is not proof of a cold cache. Cached follow-ups belong to their own workload. Cache clearing requires an explicit dedicated-server run; avoid changing an active coding session's state implicitly.

## Preflight and boot state

Preflight checks readiness, model identity (a mismatch with `--model` fails), context, and capability probes. Record boot state: uptime, load average, available and cached memory, swap occupancy, GPU idle busy percentage, temperature, power, other processes using the GPU, and notable CPU consumers. Warn, but do not fail, when the system is not quiet; thresholds are set in the pilot. A freshly booted machine is the expected case, and the recorded uptime lets readers judge it.

## Continuous resource measurement

Begin sampling before warmup and keep it active through the final response. Use a monotonic clock for samples and request boundaries; retain wall-clock metadata only in external run artifacts. `amdgpu_top` JSON carries no timestamps, so samples from child processes are stamped on receipt; state the tolerated skew when joining samples to request intervals. Join samples to workload/request intervals and calculate time-weighted averages over active requests, excluding idle pauses and token-count preparation calls.

Start with a 500 ms sampling interval. Validate overhead and sample coverage on the workstation. A short pre-run and post-run idle reference helps explain retained allocations, but the primary statistics describe active requests. Mark first-output boundaries when streaming allows it; label these as waiting-for-first-output and streaming intervals, not exact engine prefill/decode phases.

| Metric | Preferred source | Definition and caveat |
|---|---|---|
| Container CPU | cgroup v2 `cpu.stat` deltas | CPU seconds divided by wall seconds, expressed as average cores consumed |
| Container RAM | `memory.current`, `memory.stat` | Total charged memory plus anonymous/file-cache breakdown; not process RSS |
| Container swap | `memory.swap.current` | Occupancy and change during the workload |
| Desktop process CPU/RAM | `/proc` process tree, optionally psutil | Track server workers; sum CPU; use PSS where readable to avoid shared-memory double counting, otherwise clearly label RSS |
| System RAM | `/proc/meminfo` | Minimum available RAM and sampled system-used memory with formula recorded |
| System swap activity | `/proc/vmstat` counter deltas | Swap-in/out activity; distinct from swap occupancy |
| GPU memory (device) | AMD sysfs (`mem_info_vram_used`, `mem_info_gtt_used`) | Device VRAM/GTT, which includes other processes using the device |
| GPU memory (process) | `amdgpu_top` JSON fdinfo | Process allocations where readable; refresh lags by the fdinfo process-index interval |
| GPU load/power/temperature | AMD sysfs (`gpu_busy_percent`, hwmon) | Active-period average and sampled maximum, with units; power sensors may already be firmware-averaged |

Resolve a container through launcher labels once at start, using non-interactive `sudo docker` like the launcher, and read its host PID and cgroup path. After that read cgroup and `/proc` files without privileges, so an expired sudo timestamp cannot end monitoring mid-run. Fail early if non-interactive access is unavailable. Resolve the GPU by PCI address, not adapter enumeration order; this workstation also has an iGPU. For process monitoring, guard against PID reuse and worker changes. Record telemetry tool versions and detected devices.

Use sysfs as the primary GPU source: it is cheap and has no extra dependency. Verify the files exist for the target GPU. Use one long-lived `amdgpu_top --json` process for per-process allocations only. Installed `amdgpu_top` 0.11.5 provides `-J`, `-s <ms>`, `-n 0` (continuous), `--pci`, and `-u` (fdinfo process-index refresh, default 5 s); pin and probe the version, because the JSON schema is not a stable contract. Disable or avoid its performance counters (`--no-pc`): reading them may deactivate the GPU's power saving, which would perturb clocks and power during measurement. Avoid parsing interactive `top` output.

Reading PSS from `/proc/<pid>/smaps_rollup` walks page tables and can stall a process with large mappings. Sample PSS at a slower interval than other metrics and include it in the overhead check.

Treat container and device metrics as different scopes. Do not add RSS, cgroup charges, pinned memory estimates, and VRAM together. Driver-accounted allocations and file mappings can have subtle accounting behavior. Record sample count, gaps, and collection errors. A missing permission or sensor produces an unavailable metric, not zero.

Report sampled peaks honestly; polling can miss transient spikes. Cgroup `memory.peak` may include activity before the run and must not be labeled a workload peak unless its interval is established. Do not reset shared counters as a side effect. Validate attribution and monitoring overhead before interpreting small performance differences.

## Timing and statistical definitions

Capture client request duration and time to first nonempty streamed output using a monotonic clock. The first output is the first non-empty delta of content, reasoning content, or tool call, so reasoning-enabled and disabled runs are comparable. Record actual input/output counts, cached input, finish reason, failures, and truncation. Capture engine-reported prefill/decode duration and draft accepted/proposed counts when available.

- Keep client timing and engine timing in separate fields with their measurement source.
- Cross-recipe comparisons rest on client-side metrics, because TabbyAPI and LM Studio may not report engine timings. The headline pair is time to first output and client decode rate, `(completion_tokens - 1) / (t_last_output - t_first_output)`, with the token count from reported usage. This does not assume one chunk is one token, so it remains valid when chunks carry several tokens (speculative decoding). Label it as a client estimate.
- Engine-reported rates are supplementary and shown separately where available.
- Do not calculate prefill speed from time to first token; queueing, image encoding, and other work can be included.
- Do not treat one streamed chunk as one token. Report chunk timing only as chunk timing.
- Per-case values are per request. The 8K case reports the median of its five requests with the noise floor; all other cases are single observations with no median or range. Do not claim a tail-latency figure such as p99.
- Where several requests are summarized (for example engine throughput over the sustained-generation tasks), aggregate throughput is total applicable tokens divided by total applicable engine time. Draft acceptance is total accepted divided by total proposed for the same covered requests.
- Preserve failed and short requests in results. Summaries state included/excluded counts and reasons.

## Output and repository documentation

Use a schema version and a workload-suite version. Write metadata, request results, and resource samples incrementally into a new external output directory. Refuse to overwrite another run. Store request/phase identifiers and units explicitly so offline rendering is reliable.

### Formats

- **Raw, external, append-only:** JSON Lines for request records and resource samples, plus a small metadata file. JSONL survives interruption because each line is complete; YAML cannot be appended safely.
- **Result, structured:** the renderer reads the raw files and writes `results.json`: schema version, suite version, one entry per case (actual token counts, first-output latency, client decode rate, engine rates, finish reason, noise floor for the 8K case), resource summaries per workload, warmup, boot state, and functional outcomes. Units are explicit in field names. An unavailable metric is `null` with a stated reason, never zero or an omitted key. Write with a fixed key order, 2-space indent, and a trailing newline so promoted files give clean diffs. `profile.yaml` stays YAML because it is curated by hand; the machine-written results use JSON, which keeps exact types and needs no extra dependency in the runner.
- **Tables:** the generator renders `results.json` into markdown tables, as `generate_configurations.py` renders `profile.yaml` into `configuration.md`, and `--check` in `scripts/check.sh` verifies they are current. The tables go into a marked block inside the experiment's `summary.md`, so the "Results" link in the recipe index points at the full baseline. A baseline `summary.md` is an authored title, the generated block, and authored observations. The generator renders the block only for experiments that have a `results.json`; hand-written experiments keep their free-form summaries.
- **Comparison:** a later comparison page or chart reads `results.json` across recipes and does not need the raw files. Comparable fields share names and definitions across recipes, with the workload-suite version stored so runs from different suites are not compared silently.
- **Promotion:** `results.json` (small) is promoted next to `profile.yaml` in the experiment folder; raw JSONL stays external. The runner writes a draft `summary.md` with the title, markers, and an observations stub. It does not write `profile.yaml`: the profile stays hand-curated, and the runner records the facts it verified (served model, context, image identity, request policy) in `results.json` for the user to transfer. Whether a `promote` subcommand creates the numbered folder is decided in stage 1.

Capture the repository revision and relevant file hashes, recipe identity, served model ID, actual context, host hardware/OS, boot state, runtime/model lock identities, sampling, image-token settings, and monitoring versions. Distinguish checked-in configuration from verified runtime state. Existing doctor checks only establish local image availability; they do not prove the running image's embedded build lock. Record running image identity and verification status separately.

The report contains:

1. Workload and effective configuration, with missing data stated.
2. Boot state and any quiet-system warnings.
3. A compact functional outcome list.
4. Warmup summary: request count, duration, convergence.
5. One row per case: actual input and output counts, first-output latency, client decode rate, engine rates where available, and finish reason. The 8K row shows the median and the run's noise floor.
6. A resource table by workload: average CPU cores, peak container/process RAM, minimum system-available RAM, peak device VRAM/GTT, and swap activity.
7. Observations about truncation, resource pressure, errors, and sample coverage.

Keep reports standalone. Cross-recipe comparisons and charts can later consume the structured files. Do not insert comparisons into individual experiment reports or publish raw logs automatically.

Generate `results.json`, its rendered tables, and a draft `summary.md` in the external directory for review. Promote the confirmed snapshot into `recipes/<recipe>/NNN-YYYY-MM-DD-description/`, then run the existing configuration/index generator. Define in stage 1 how baseline results map onto existing `profile.yaml` fields (`software.harness`, `harness_version`, check-request settings) and what the generator validates; extend the template only where needed. Do not infer unknown runtime settings. Name baseline experiments `NNN-YYYY-MM-DD-baseline`, adding a variant suffix when the configuration differs from the recipe default (for example draft or vision settings). Keep the result template usable for manually recorded experiments as well as baseline runs.

## Delivery stages

### 1. Define contracts and prove API support

- Inventory current doctor and generation helpers; reuse their request and stream validation, not the doctor.
- Specify result records, units, missing-data representation, capability flags, workload versioning, CLI exit codes, the concurrency/shutdown model, and the desktop-recipe resolution.
- Specify the mapping onto `profile.yaml` and template fields.
- Specify the vision expectations file format and the scoring rules.
- Specify the `results.json` schema (fields, units, null-with-reason representation) and extend the generator to render and `--check` it.
- Record real response fixtures (redacted, with the server version noted) for all three API servers, including streaming, error, tool, and token-count responses. Hand-written mocks only encode assumptions.
- Add the new modules to the mypy file list and ruff configuration; decide how runtime-local scripts import shared code.
- Verify telemetry availability on the target host, including the sysfs files, and identify the RX 9070 XT and container cgroups.

Acceptance: each proposed metric has a defined source or explicit unavailable state; fixture tests demonstrate request/response handling without Docker or a GPU.

### 2. Implement monitoring and the initial unified suite

- Build the orchestrator with preflight, boot-state capture, adaptive warmup, the 8K noise probe, sustained text/context workloads, functional checks, and bounded requests.
- Implement concurrent CPU/RAM/GPU sampling and incremental output writing.
- Add offline report generation and interruption cleanup.
- Keep server configuration and lifecycle under the existing launcher.

Acceptance: a fake-server integration test exercises a full run, injected errors, cancellation, sample attribution, noise-floor calculation, and partial-report rendering. Monitoring starts before requests and continues while requests block. No server shutdown or model-file mutation occurs.

Implementation notes (stage 2, implemented):

- The command is `scripts/run_baseline.py`; a `scripts/baseline.py` would collide with the `scripts/baseline/` package.
- The long contexts are built from the interpreter's standard-library source, which is PSF-licensed and needs no checked-in corpus. The Python version is part of what makes runs comparable.
- The first warmup request is a roughly 1K-token code-review prompt whose reported token count calibrates prompt length for the later cases, so no measured prompt is also used for counting.
- Thinking is disabled by default only for Strata, the one server with a verified field. Others need `--request-extra`, and the result records whether the default applied.
- Engine-reported timings are not parsed yet; those metrics are unavailable with that reason.
- Per-process VRAM comes from one `amdgpu_top` child that the runner always stops; device-wide figures come from sysfs.
- Still open for the workstation pilot: warmup tolerance, quiet-system thresholds, the minimum sustained output length, observer overhead, and the image-token setting.

### 3. Validate on the workstation and unify documentation

- Pilot Strata ISTA and Unsloth, then ExLlamaV3/TabbyAPI and LM Studio, each from a freshly booted machine with one execution.
- Compare sampled measurements with live tools; validate memory scope, CPU units, PCI selection, and cache classification.
- Run matched cases with monitoring enabled/disabled to quantify observer overhead.
- Set the warmup tolerance and maximum count, the quiet-system thresholds, and the minimum sustained output length from pilot data. Check that noise floors are plausible and comparable across recipes.
- Confirm the proposed lengths and context matrix yield useful durations without exhausting memory. Record actual suite duration before documenting an estimate.
- Replace setup-guide validation blocks with the unified command where a setup guide exists (desktop recipes have none). Update runtime/client instructions, authoring guidance, and templates.
- Retain small compatibility wrappers for existing check commands during migration if needed; remove duplicate request logic once the new path is verified.
- Replace each recipe's initial-check and vision experiments with a baseline, only after that recipe has a baseline covering the same content (text, tools, vision, long context, memory). Rules:
  - Hand-written coding-session experiments are kept.
  - Do not renumber; gaps are acceptable and the baseline takes the next number.
  - Some experiments are configuration variants, not plain checks (ISTA `002` with 1,024 image tokens; EXL3 `001`, which compares DFlash2 against disabled). Re-run them as baselines under that configuration, or keep them.
  - Remove or move assets only when nothing references them.
  - Fix the cross-references to removed experiments: EXL3 `002` links an asset in `001`, and the Unsloth `001` summary links the ISTA initial check.
  - Update `docs/authoring.md` examples that name the removed folders, and `docs/vision-check.md`, which mentions the earlier Unsloth image.
  - Git history preserves the removed results. Run the generator so the recipe index is regenerated.

Acceptance: each recipe can produce a standalone baseline with comparable metric definitions and clearly marked gaps. Retained historical results are unchanged, and removed ones leave no dangling links. Workstation validation is reported separately from CPU-only CI.

### 4. Add representative conversation reuse

- Add a fixed multi-turn coding conversation with realistic tool-result text.
- Report fresh versus reused prompt processing and resource behavior separately.
- Add reasoning-enabled evaluation only with verified effort/budget mappings.

Acceptance: cache reuse is observable or explicitly unknown, and workload changes receive a new suite version. A later comparison page can consume completed runs without changing their reports.

## Tests and completion checklist

Use behavior-focused tests for counter deltas, timestamp alignment, sample gaps, missing sensors, changing processes, cache classification, partial streams, early EOS, malformed responses, mismatched model IDs, warmup convergence and non-convergence, vision scoring (all match, mismatch, missing field, unparseable answer, spelling and separator normalization, using fixed answer strings and a small generated image rather than the repository screenshot), noise-floor calculation, client decode-rate calculation, and cancellation. Test report calculations with known values, preserve unavailable metrics through serialization, and verify that `results.json` renders deterministically into tables. Verify that outputs never mix progress messages with JSON.

Run `bash scripts/check.sh`, which includes generated-document validation. Check setup examples and local links. Add required development dependencies to the existing pinned dependency workflow; document any host monitoring dependency. Keep automated tests CPU-only and deterministic.

The initial implementation is complete when one execution per recipe produces useful sustained measurements and an actionable standalone report for the supported recipes, captures resources while requests execute, retains partial diagnostics on failure, and leaves publication under user control.

## Research references

- [amdgpu_top usage and JSON mode](https://github.com/Umio-Yasuno/amdgpu_top#usage): continuous telemetry, PCI selection, and sampling interval.
- [Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): CPU, memory, peak, and swap accounting.
- [AMDGPU monitoring interfaces](https://docs.kernel.org/gpu/amdgpu/thermal.html): utilization, temperature, and power sensors.
- [Docker stats](https://docs.docker.com/reference/cli/docker/container/stats/): memory/cache accounting distinctions and container statistics.
- [llama-bench](https://github.com/ggml-org/llama.cpp/tree/master/tools/llama-bench): warmup, repeated measurements, and context-depth workloads.
- [vLLM serving benchmark](https://github.com/vllm-project/vllm/blob/main/vllm/benchmarks/serve.py): separate first-token, output-token, and end-to-end latency metrics.
