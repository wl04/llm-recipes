# Tested inference recipes: architecture and implementation plan

Revised 2026-11-03. Scope: a personal, shareable collection of inference setups actually used and tested across multiple computers, hardware architectures, and operating systems. Known machines include an RX 9070 XT with 16 GB dedicated VRAM on Ubuntu 26.10 and a MacBook Pro M2 with 32 GB unified memory on macOS. Exact Mac chip variant and macOS version remain to be recorded. Training is outside scope.

## Purpose

The organizing unit is a tested experience: a model, hardware/software environment, configuration, workload, and evidence. Docker, native binaries, desktop applications, ROCm, and Vulkan are implementation choices within a recipe. A recipe can be reproducible through documented manual steps; automation is optional.

The reference exl3-rdna4-recipe repository supplied inspiration only. Implement this project independently. Do not transfer its scripts, configs, patches, or documentation. If a patch is deliberately reused later, record its author, original URL and commit, license, modifications, reason for use, compatible upstream version, and removal condition. Preserve required notices and distinguish attribution for ideas from attribution for copied code.

## Findings from the supplied example

Reviewed local source: reddit-recipe/REDDIT-RECIPE.md. The accompanying memory screenshot is available, but the measurements below are taken from the written report; raw session logs and aggregation code were not supplied.

The example uses LM Studio Bionic with llama.cpp Vulkan, Qwen3.8-27B GSQ-RCO IQ3_XXS GGUF, and MTP. It documents application settings, a 131072-token context, and sustained coding work on gpu-switcher. It reports 915 requests and 1,218,469 generated tokens across five sessions on November 1–2, 2026, with aggregate decode of 48.92 tokens/s and MTP acceptance of 64.99%.

Its strengths are workload context, detailed settings, context-bucketed results, explicit rate definitions, and limitations. The 860-response subset is explained separately from the complete request count. The memory report correctly describes a snapshot rather than a measured peak. Preserve that distinction: 277 MiB free at one instant does not establish a safe memory reserve for other workloads. Similarly, configured 128K context and successful long prefills do not establish long-context reasoning quality; middle truncation is explicitly enabled.

Additional information needed for stronger reproduction: exact application build and inference-runtime version, model repository revision and file hashes, CPU/system RAM, GPU driver/Mesa version, client/harness version and configuration, test timezone, and whether vision was actually exercised. A listed mmproj file alone does not establish tested vision support. Missing details should be labeled unknown, never inferred.

## Minimal repository structure

```text
README.md                         # searchable catalog table and purpose
CONTRIBUTING.md                   # what makes an entry useful
LICENSE                          # license for original repository content
recipes/
  qwen3.8-27b-lmstudio-gguf/
    README.md                    # complete setup and experience report
    recipe.yaml                  # small index metadata
    profiles/
      rx9070xt-ubuntu-vulkan/
        profile.yaml             # hardware/OS, versions, validation status
        config/                  # original exports where available
    assets/                      # selected screenshots
    results/
      rx9070xt-ubuntu-vulkan/2026-11-01_02-coding/
        summary.md               # observations, method, limitations
        metrics.json             # optional machine-readable summary
        provenance.yaml          # exact environment/config identities
  qwen3.8-27b-exllamav3-rocm/
    README.md
    recipe.yaml
    config/
    container/                   # optional, owned by this recipe
      Dockerfile
      compose.yaml
      requirements.lock
    scripts/                     # optional preparation/startup helpers
    results/
templates/
  recipe.md
  recipe.yaml
  result.md
schemas/
  recipe.schema.json             # add with metadata validation
scripts/                         # shared tools only after actual reuse
```

Create the first directory from the user's own supplied LM Studio report. The ExLlamaV3 directory is a planned recipe and must remain visibly untested until experiments are performed. It need not exist until that work begins.

Keep each recipe understandable by itself. Prefer a small amount of duplication over mandatory shared stack/model registries. Extract a shared image build or downloader only when multiple working recipes need the same implementation. Do not require a launcher, custom configuration language, or common server architecture.

## Recipe contract

### Multiple machines and operating systems

A recipe describes a coherent model/tool workflow. A profile specifies the hardware, OS, backend, and effective settings used for that workflow. A dated result records one experiment or period of use with a particular profile. Validation status and last-tested date belong to each profile; one successful Linux profile does not validate the recipe on macOS.

Add another profile when the model artifacts and main workflow remain shared and platform differences can be explained clearly. Create another recipe when the engine, model format, installation, or operating procedure differs substantially. For example, a macOS application setup using the same GGUF workflow may fit beside the Linux profile; a different engine using a different model format may deserve its own recipe. Backend availability must be checked during implementation, not assumed from another platform.

Do not require a shared machine registry initially. Record a non-sensitive machine label and complete environment details in each profile/result. If repeated machine specifications become burdensome, extract reusable machine descriptions, while preserving an immutable environment snapshot with each result so later OS upgrades cannot rewrite historical evidence.

Represent memory explicitly as dedicated GPU memory, system RAM, or unified memory. For the MacBook, record 32 GB as unified memory shared by the system, not as 32 GB dedicated VRAM. Leave dedicated VRAM not applicable. Record measured process/device memory, system memory pressure and swap where available, using platform-native metric names and definitions. Do not directly equate VRAM occupancy with unified-memory occupancy or assume all installed memory is available for inference.

The catalog should expose model, application/engine, backend, OS, hardware, memory type/capacity, and profile validation status. Readers should be able to find either all recipes tested on their machine class or all tested profiles for a particular model.

Every entry explains:

1. What it is useful for, and what was actually tried.
2. Hardware and software versions, including the host and the effective inference backend.
3. Exact model artifacts and quantization; tokenizer/template and vision projector where applicable.
4. Installation prerequisites and reproduction steps, including manual GUI operations if necessary.
5. Effective configuration: model loading, memory, context, sampling, drafting, and API settings.
6. Client/workload details and how the server was accessed.
7. Results, measurement definitions, evidence availability, and limitations.
8. Upstream references and attribution.

Keep metadata small. Example values below describe the supplied report and do not certify independent reproduction:

```yaml
schema_version: 1
id: qwen3.8-27b-lmstudio-gguf
profile: rx9070xt-ubuntu-vulkan
status: tested
last_tested: 2026-11-02
execution: desktop-app
reproduction: manual
hardware:
  gpu: AMD Radeon RX 9070 XT
  memory:
    architecture: discrete
    dedicated_vram_gib: 16
    system_ram_gib: null
os:
  name: Ubuntu
  version: '26.10'
software:
  application: LM Studio Bionic
  application_version: null
  engine: llama.cpp
  engine_version: null
  backend: Vulkan
model:
  name: Qwen3.8-27B
  format: GGUF
  quantization: IQ3_XXS
speculation: MTP
workloads: [coding, tool-use]
evidence: summarized-session-logs
```

Separate execution method (desktop-app, native, container) from compute backend (Vulkan, ROCm, CUDA, CPU, or another backend). Separate application/harness, inference engine, server, and client roles in documentation; one application may fulfill several roles. Do not impose a one-component-per-role deployment.

Use profile statuses such as experimental, tested, and retired. Record whether another person has reproduced a profile separately. “Tested” means the author used that exact setup, not that every advertised upstream feature or every hardware/OS combination has been verified. Preserve an explicit unknown value for absent version information. The metadata example combines recipe and profile fields for illustration; keep common identity in recipe.yaml and environment-specific fields in profile.yaml when implementing multiple profiles.

## Configuration and evidence

Use original application exports and native server configs when available. Include screenshots for GUI-only settings and a textual table so readers can search and compare them. Record which defaults matter and whether automatic optimization was disabled. Redact API keys and personal paths before sharing.

A result belongs to a specific configuration and environment. Each result record should identify the recipe revision or configuration hash, model hashes/revisions, application and runtime versions, hardware/driver, workload, time period/timezone, and measurement method. If some of these were not recorded historically, state that limitation.

Keep real-workload reports and controlled benchmarks as distinct evidence types. Both are valuable. Real-workload reports describe sustained behavior, observed failures, tool use, compaction/truncation, and subjective usefulness. Controlled comparisons hold prompts, output budgets, context, sampling, concurrency, and cache state as constant as practical.

Do not rank recipes solely by tokens/s across different workloads, quantizations, context lengths, or rate definitions. Preserve aggregate versus median calculations and explain exclusions. Separate processing latency from end-to-end latency including client and tool execution. Use “no crashes observed in these sessions” rather than a general stability guarantee.

Commit small curated summaries and selected images. Large logs, traces, and benchmark output can be release assets or external artifacts with hashes and links. If private prompts/source cannot be shared, provide sanitized aggregates and the analysis method where possible, stating that exact replay is unavailable. Retain only useful evidence, not every debugging transcript or failed experiment.

## Reproduction levels

Support three practical levels without treating manual recipes as inferior:

- Documented: steps, settings, and results are recorded; some historical dependencies or inputs may be unavailable.
- Pinned: exact versions/artifacts/configuration are identified and obtainable, subject to upstream distribution terms.
- Automated: preparation and startup can be executed through supplied commands, with checks.

Proprietary application recipes link to the publisher's installation source and identify the tested build. Do not bundle installers or binaries unless redistribution is permitted. If an old build becomes unavailable, retain the experience report and mark the reproduction limitation.

## Optional container recipe

For the future ExLlamaV3 recipe, independently implement a prepared image based on AMD's published ROCm/PyTorch image, exact upstream ExLlamaV3 and TabbyAPI revisions, and compatible target/draft artifacts. Resolve and test the actual base-image digest at implementation time. No current compatibility claim is made by this plan.

Model weights remain external mounts. Download/quantization is an explicit preparation step. Keep a draft-disabled baseline and test DFlash2 as a separate configuration. The speculative implementation may be integrated into the engine; do not assume a standalone DFlash package or service is required.

Lock build dependencies for automated recipes, but do not impose image digests or container-specific files on desktop recipes. Keep native settings native. Test the actual Ubuntu host driver/GPU combination; a container cannot replace the host kernel driver.

## Updates and maintenance

Keep the last working configuration intact while testing an update. Add a dated result for the candidate; update the recommended configuration only after using and validating it. Mark older results with the software/configuration they measured. There is no need to retest every recipe whenever an upstream release appears.

Use Git history and release tags for superseded configurations. Keep a current README with clear historical result links. If a tool becomes unavailable or an old setup stops working, mark the recipe retired or reproduction-limited rather than quietly deleting the experience.

Initially, CI checks document links within the repo, metadata/schema validity, required fields, and absence of accidental large artifacts. Hardware-dependent tests are optional per recipe. CI success must not be presented as GPU inference validation.

## Implementation plan

1. Create the catalog and templates. Start with Markdown and minimal YAML; no shared runtime framework. Define recipe, hardware/OS profile, dated result, status, reproduction level, and evidence vocabulary. Include both dedicated and unified memory in the metadata design.
2. Curate the supplied LM Studio recipe. Preserve its settings and reported measurements, separate setup from dated results, add the screenshot, and list missing version/provenance fields. Do not invent missing data or claim the aggregates were independently recomputed.
3. Capture a repeatable LM Studio session. Export available settings, record exact runtime/model identities, save sanitized logs and analysis code, and document startup/API access. Recheck tool round trips, long prefill, truncation behavior, and memory observations.
4. Develop the upstream ExLlamaV3/ROCm recipe independently. Start with a compatibility experiment, then baseline serving, then draft preparation and tuning. Publish it as tested only after actual GPU execution.
5. Add a MacBook Pro M2/macOS experiment after selecting a suitable model/tool workflow and recording the exact chip, OS, and application versions. Reuse a recipe via a new profile only where its workflow is genuinely shared. Keep the Mac profile experimental until tested; existing Radeon measurements provide no Mac validation. Compare setups on a small shared workload if useful, reporting latency, throughput, platform-specific memory measurements, functionality, setup effort, and limitations. Preserve separate real-world experience reports.
6. Extract shared tools after repetition appears: API smoke checks, log aggregation, benchmark request runner, or model downloads. A generated catalog or website can follow once the collection outgrows a README table.

Success means another person can identify a relevant setup, understand the evidence and limitations, and follow its reproduction path—with a GUI, native process, or container as appropriate.
