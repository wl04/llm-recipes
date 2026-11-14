# Baseline contract

This page defines the baseline runner's result format and measurement rules and how to run it. The runner is implemented in `scripts/baseline/`; the [implementation plan](../plans/unified-baseline.md) tracks the remaining workstation validation.

One execution per recipe produces one baseline. The runner attaches to a server you have already started and never starts, stops, or reconfigures it.

## Running

Start the server first, preferably from a freshly booted machine with nothing else running. For a launcher recipe:

```bash
python3 scripts/run_baseline.py run <recipe> --instance <instance> \
  --model <served-model-id> --output "$HOME/Models/llm-recipes/baselines/<run-name>"
```

For a desktop server such as LM Studio, pass the endpoint, context, and process:

```bash
python3 scripts/run_baseline.py run <recipe> --base-url http://127.0.0.1:<port>/v1 \
  --model <served-model-id> --context <tokens> --pid <server-pid> \
  --output "$HOME/Models/llm-recipes/baselines/<run-name>"
```

`--output` must be a new directory outside the repository. Progress goes to stderr and a one-line result to stdout. Ctrl+C or SIGTERM stops the run, keeps what was recorded, and leaves the server running. `--instance` resolves the container with `sudo -n docker`, so authenticate with `sudo -v` first. Other options: `--gpu-pci` (default: the AMD GPU with the most VRAM), `--no-gpu`, `--image`, `--server-kind`, and `--request-extra` (a JSON object merged into every request).

The run directory holds `meta.json`, `requests.jsonl`, `samples.jsonl`, and the rendered `results.json` and draft `summary.md`. `python3 scripts/run_baseline.py render <run-dir>` rebuilds the rendered files from the raw ones, for example after an interrupted run, and keeps the text you wrote in `summary.md`. To publish, create the numbered experiment folder, copy `summary.md` and `results.json` into it, fill in `profile.yaml`, and run the generator.

The suite runs in a fixed order: a 5-second idle reference, functional checks (text, forced tool call, vision), an adaptive warmup of up to four requests, the 8K case repeated five times, three sustained-generation tasks, then 32K, 64K, and 120K contexts. Each case after the 8K probe is a single observation. Cases whose input plus output cannot fit the context are recorded as skipped. Prompt length is calibrated from the first warmup request's reported token count, and every request has distinct content.

### Current limits

- Thinking is disabled by default only for Strata (`reasoning_effort: none`). For other servers set the server's own field with `--request-extra`; the result records whether the default applied.
- Engine-reported timings are not parsed yet, so the engine prefill and decode columns are unavailable. Client timings are measured for every server.
- The long contexts are built from the interpreter's standard-library source (PSF-licensed code), so comparisons assume the same Python version.
- The image-token setting is not detected; note it yourself when it matters for the vision scores.
- Warning thresholds for the boot state (load average above 1.0, GPU more than 5% busy) and the warmup tolerance (10%) are provisional until the workstation pilot.

## Result document

`results.json` is machine-written JSON with a fixed key order, two-space indent, and a trailing newline. [`scripts/baseline/schema.py`](../scripts/baseline/schema.py) validates it, and `scripts/generate_configurations.py` renders it into the marked results block of the experiment's `summary.md`.

| Key | Content |
|---|---|
| `schema_version`, `suite_version` | Format version, and the version of the workload suite (prompts, expectations, and case list). Runs from different suites are not compared silently. |
| `recipe` | Recipe folder name. |
| `run` | `status` (`complete`, `interrupted`, `failed`); optional run identity and repository revision. |
| `server` | `kind` (`strata`, `tabbyapi`, `lmstudio`), served `model`, actual `context_tokens`. |
| `boot` | Optional boot-state metrics (uptime, idle readings) and warnings. |
| `functional` | One entry per check with `status` (`pass`, `fail`, `unparsed`, `skipped`). |
| `warmup` | Request count, whether it converged, and duration. |
| `cases` | One entry per workload case: `id`, `status`, `runs`, `finish_reason`, optional `note`, and `metrics`. |
| `resources` | One entry per case with resource `metrics`. |

### Metrics

Every metric is either measured or unavailable:

```json
{"value": 81.5, "unit": "tokens/s", "source": "client estimate"}
{"value": null, "unavailable": "server reports no timings"}
```

An unavailable measurement is never zero and never omitted. Units are part of the metric. Client timings and engine timings are separate metrics with their own sources. Case metrics the table shows: `input_tokens`, `output_tokens`, `cached_input_tokens`, `first_output_s`, `client_decode_tok_s`, `engine_prefill_tok_s`, `engine_decode_tok_s`, and `noise_first_output_spread` / `noise_decode_spread` for the repeated 8K case. Resource metrics: `cpu_cores_avg`, `ram_peak_gib`, `system_available_min_gib`, `vram_peak_gib`, `gtt_peak_gib`, `swap_in_pages`, `swap_out_pages`.

The client decode rate is `(completion_tokens - 1) / (last output - first output)`, using reported token counts. It does not assume one streamed chunk is one token. The noise floor is the range over the median of the repeated 8K case.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Run completed and the report was written. |
| 1 | Run completed with failed functional checks or failed requests. |
| 2 | Invalid arguments or configuration. |
| 3 | Preflight failed: server unreachable, model mismatch, or no non-interactive access to resolve the container. |
| 130 | Interrupted. Partial output is kept. |

## Server capabilities

Servers differ in what they report. Capabilities are discovered by probing the running server and recorded; they are not assumed. A capability that was not probed is recorded as unknown, and the metric that depends on it is unavailable. This covers streaming usage, cached-token counts, engine timings, token-count routes, and cache controls. The Strata helpers use `POST /v1/messages/count_tokens` and streamed usage; TabbyAPI and LM Studio still need to be recorded against real servers (see [fixtures](../tests/fixtures/README.md)).

## Telemetry sources

Verified on the target workstation (RX 9070 XT at `0000:03:00.0`, plus an iGPU at `0000:12:00.0`, so devices are selected by PCI address):

| Metric | Source |
|---|---|
| GPU busy, VRAM, GTT | `/sys/bus/pci/devices/<address>/gpu_busy_percent`, `mem_info_vram_used`, `mem_info_gtt_used` |
| GPU power, temperature | `hwmon` in the same device directory (`power1_average`, `temp1_input`) |
| Container CPU, memory, swap | cgroup v2 files, readable without privileges once the container's cgroup path is known |
| System memory, swap activity | `/proc/meminfo`, `/proc/vmstat` |
| Process allocations | `amdgpu_top` 0.11.5 JSON (`-J`, `-s <ms>`, `-n 0`, `--pci`) with `--no-pc` to avoid its performance counters; one long-lived child that the runner always stops. Its process index refreshes about once a second. |

Resolving a container uses `sudo -n docker`, as the launcher does, once at start. Device memory is device-wide and is not added to cgroup or process figures.

## Desktop recipes

Desktop recipes (for example LM Studio) have no launch manifest. The runner resolves the recipe by folder name for identity and output naming, and requires the endpoint, model, context, server process ID, and GPU address as options.

## Experiment profile

`profile.yaml` stays hand-curated. The runner records what it verified (served model, context, request policy) in `results.json`; transfer those into the profile. Set `software.harness` to the llm-recipes baseline runner, `software.harness_version` to the repository commit URL, and `settings.Workload suite` to the suite version.

## Vision check

All recipes use `assets/checks/amdgpu-top.png`. [`assets/checks/amdgpu-top.expected.json`](../assets/checks/amdgpu-top.expected.json) lists the expected fields in two tiers. The prompt is built from that file and asks for a JSON object. Each field scores `match`, `mismatch`, or `missing`. The check passes when every `identity` field matches; `detail` fields are informational because small text depends on the image-token budget. Record the image-token setting beside the scores. The scores are a text-matching check on one screenshot, not a general claim of image understanding.

---

[All recipes](../README.md) · [Authoring](authoring.md) · [Launcher](launcher.md)
