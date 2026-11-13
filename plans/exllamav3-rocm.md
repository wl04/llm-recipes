# ExLlamaV3 / ROCm container implementation plan

## Objective

Prepare an independently maintained image for Qwen3.8-27B EXL3 on the RX 9070 XT (gfx1201), Ryzen 7 9800X3D, and 64 GB RAM. Use AMD's published ROCm/PyTorch image, upstream ExLlamaV3, and upstream TabbyAPI. Include DFlash2 support in the initial version through ExLlamaV3’s integrated implementation, retaining draft-disabled operation as a comparison and fallback. Model preparation is explicit; serving mounts the prepared weights externally.

## Findings from source inspection

Inspected reference revision: `fe77c7b430b27232959d8fa19cb0de6f8640178c` of [exl3-rdna4-recipe](https://github.com/parth-thakre/exl3-rdna4-recipe).

- Its Dockerfile builds on `rocm/dev-ubuntu-24.04`, then copies a Python environment into an Ubuntu runtime image. It installs its own recipe scripts and applies RDNA4 patches. Our requested ROCm/PyTorch base is a different packaging choice.
- It pins ExLlamaV3 v1.6.6 and an older TabbyAPI revision, and uses custom WMMA/GEMV, MLP, and attention changes. Its throughput and context limits describe that patched stack and host.
- Its model preparation includes an upstream target quant and a maintainer-produced 3 bpw draft. Select target and draft artifacts from their original publishers or prepare their quantization explicitly.
- Useful operational ideas: external weights, explicit configuration, target GPU compilation, and separate serving/model-preparation commands. Implement those independently. Keep operational documentation and selected results; do not import its patch archive, research logs, benchmark suite, installers, or triage agent workflow.

Inspected upstream candidates (observations, not a validated compatibility lock):

| Component | Revision | Finding |
|---|---|---|
| [ExLlamaV3](https://github.com/turboderp-org/exllamav3) | `bd1f519172406a9560bd5c90e61000691bb69a07` | Source includes `architecture/dflash2.py`, architecture registration, and integrated generator support. Build code handles ROCm and links HIP libraries. |
| [TabbyAPI](https://github.com/theroyallab/tabbyAPI) | `8f92fac5d9307bf1e09668c3715b32ff46ad0333` | ExLlamaV3 backend and native draft-model configuration; Python dependencies include broad ranges, so a resolved lock is needed. |

Docker Hub's web tag endpoint returned HTTP 403. Subsequent research retrieved tags, manifests, and image build metadata through the public OCI registry API; see the base-image comparison below. No image layers have been downloaded and no container build or GPU inference has been performed.

## 1. Resolve the compatibility set

1. Inspect AMD's [ROCm/PyTorch image](https://hub.docker.com/r/rocm/pytorch) and [ROCm documentation](https://rocm.docs.amd.com/). Select the newest stable published combination supporting RDNA4/gfx1201, then record its explicit tag, manifest digest, linux/amd64 image digest, ROCm/Python/PyTorch versions, and bundled build tools.
2. Pull by digest and inspect the actual installed versions. Check the host kernel/amdgpu/firmware and device permissions against AMD's support matrix. Record any gap between the documented matrix and this Ubuntu 26.10 host; an image cannot replace the host driver.
3. Recheck upstream release/commit state at implementation time. Pin full ExLlamaV3 and TabbyAPI SHAs after testing their combination. Prefer current stable upstream; use a newer upstream commit only for a concrete required fix.
4. Confirm the selected Python, PyTorch, ROCm compiler/runtime, Triton, and any attention dependencies agree. Inspect upstream build flags for gfx1201 and constrain build jobs to host RAM/CPU. Avoid an installer silently replacing AMD's bundled PyTorch with a CUDA or incompatible ROCm wheel.
5. Compile and import the upstream engine, run a GPU tensor operation, then a short target-only generation. If upstream fails, isolate the cause and document the smallest upstream fix or blocked prerequisite. Do not silently import the reference patch set.

Deliverable: a verified compatibility record and exact candidate locks. “Latest” is the selection policy when updating; builds consume immutable pins.

## 2. Build the prepared image

- Start with one AMD ROCm/PyTorch-derived image to retain its coherent libraries. Optimize image size only after correctness and startup work.
- Build ExLlamaV3 from the pinned upstream revision; install pinned TabbyAPI and its required dependencies. Compile build-time extensions during image creation. Document any unavoidable GPU-specific first-run/JIT cache warm-up.
- Lock direct and transitive Python/build dependencies with hashes, source SHAs/submodules, and any added OS packages via reproducible package sources/versions. Preserve TLS/checksum verification. Record bundled packages from the base separately from added packages.
- Keep a small build manifest containing the base digest, engine/server revisions, Python/Torch/ROCm versions, build architecture/flags, and dependency lock identity. Include it in the image and results profile.
- Use native TabbyAPI YAML configuration mounted read-only. Mount model directories read-only for serving, with separate writable caches and application state. Keep API credentials outside the image and repository.
- Pass `/dev/kfd` and the selected `/dev/dri` devices with appropriate group access. Select the RX 9070 XT explicitly: this host also has an integrated GPU. Avoid privileged mode. Publish the API to host loopback by default and retain supported authentication.
- Use one serving configuration with an explicit draft on/off option. Resolve the exact supported TabbyAPI override mechanism at the pinned revision; if a small entrypoint adapter is needed, render a temporary native config without modifying the mounted source. Record the effective mode and settings. Draft-disabled mode must disable automatic MTP as well and must start without draft files. Draft-enabled mode must fail clearly if its artifacts are missing rather than silently falling back.
- Serving startup validates required mounts/configuration and starts TabbyAPI. Download and quantization remain separate commands. Verify graceful shutdown and restart with the same mounted artifacts.

## 3. Prepare target and draft explicitly

1. Target candidate: the engine author's `turboderp/Qwen3.8-27B-exl3`, with a roughly 3 bpw quant as a starting candidate for 16 GB. Resolve its immutable repository revision, exact files, tokenizer/template, quantization details, and license from the publisher. Treat the reference's `SC_3.00bpw_H4` choice as a candidate to validate on our stack.
2. Download the selected published EXL3 quant explicitly. If preparing a quantization ourselves, use pinned upstream tools and record the source revision, conversion command, calibration inputs where applicable, quantization settings, tool revision, and output hashes. Keep weights outside Git.
3. Resolve the original Qwen3.8-27B DFlash2 checkpoint and its immutable revision. Upstream currently references `z-lab/Qwen3.8-27B-DFlash2`, while the reference recipe uses `incoai/Qwen3.8-27B-DFlash2`; confirm publisher identity and actual files. Check target-layer taps, dimensions, vocabulary/tokenizer, architecture metadata, and compatibility with the pinned engine. Use a compatible publisher-provided EXL3 draft or quantize the original checkpoint with pinned upstream tools. Include source revisions, conversion settings, and output hashes in the artifact manifest. No standalone DFlash service or package is assumed.
4. Estimate disk, RAM, and GPU needs before quantizing. Use another adequately provisioned machine if conversion exceeds the target workstation's resources; serving compatibility still requires validation on the RX 9070 XT.
5. Save a small artifact manifest with revisions, file identities, sizes/hashes, and licenses. Validate it before serving. Keep downloads resumable and avoid overwriting existing artifacts without an explicit preparation request.

## 4. Validate draft-disabled and DFlash2 operation

First run the serving configuration with speculative decoding disabled, including automatic MTP/draft paths. Start at a modest context and concurrency one; choose cache precision and target quantization from measured memory use.

Required checks: model loads; authenticated model listing; non-streaming and streaming completions; finite/coherent output; request cancellation; a real coding-agent tool-call round trip; restart using external mounts. Confirm the loaded engine, GPU, model, config, and draft-disabled state from runtime output.

Run a small fixed workload at increasing context sizes within measured capacity. Record generated tokens, generation/prefill processing times, cache reuse, output lengths, VRAM/RAM/GTT, and failures. Cold and reused-prefix prefills are separate observations. Establish the usable context range while the normal desktop is active. Long-context capacity and 128K remain measurements to make, not inherited defaults.

Enable DFlash2 in the same image and repeat functional checks, confirming actual draft activation and acceptance counters. Compare on/off runs with the same target quantization, prompts, output budgets, sampling, cache precision, concurrency, and shared context sizes. Include coding and sampled prose; distinguish warm-up from steady-state timing. Record generation speed, prefill, acceptance, additional memory, and any correctness/tool-call differences. Check deterministic agreement where supported by the engine’s numerical behavior and investigate divergences.

Choose DFlash2 as the default after it demonstrates a useful coding speedup with acceptable desktop memory headroom. Preserve the explicit off option. If compatibility or correctness fails, diagnose it before claiming the initial version complete. If it works but has no useful speedup, include support with the off mode as default and document the measurement.

Record both modes in one dated experiment: the profile identifies the selected configuration and draft artifact, while the summary records the comparison and mode-specific differences. No dedicated DFlash2 experiment folder is required.

## 5. Repository layout and publication

Keep automation specific to this recipe:

```text
recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/
  setup.md
  container/
    Dockerfile
    compose.yaml
    versions.lock.yaml
    requirements.lock
  config/
    serving.yaml
  scripts/
    prepare-models.sh
    smoke.py
  models.lock.yaml
  YYYY-MM-DD/
    profile.yaml
    configuration.md
    summary.md
```

Add a conversion helper only if preparing our own target or draft quantization. Use the existing Markdown generator for each completed result. The current `recipes/*/*/profile.yaml` discovery works with this layout; container/config folders contain no profile files.

Extend only these container result profiles with labeled image digest, source revisions, lock/artifact identities, and server version fields. The harness remains the actual workload client; TabbyAPI is the server. Native TabbyAPI config is the executable authority; identify its file/hash in the result snapshot and capture effective settings after resolution. Keep old configurations available through Git history and recorded revision/hash. Existing desktop profiles retain their present fields.

Record useful results and concise operational instructions. Keep raw logs, weights, caches, build outputs, and copied development history outside the repository. Minimal smoke checks serve this image; a general benchmark framework is unnecessary.

Build and validate locally first. Record the final image digest if distributing through a registry. Choose the registry and public-image publication separately. Respect upstream licenses, including TabbyAPI's AGPL obligations and model licenses; include required notices/source availability when distributing the image. If a patch becomes necessary, record its author, upstream URL/SHA, license, purpose, supported revision, and removal condition.

## Completion criteria

- Digest-pinned AMD base and exact source/dependency locks rebuild successfully.
- Both draft-disabled and DFlash2 modes pass functional checks on the actual host GPU.
- Matched on/off measurements establish the documented default and usable context/memory limits.
- Serving starts from prepared external model mounts without downloading artifacts.
- Results identify the image, models, native configuration, machine, and actual workload client.
- Instructions cover target/draft preparation, build, startup with drafting on or off, shutdown, and the checks actually performed.

Implementation starts with compatibility resolution and the upstream baseline. No project scripts or containers have been implemented by this planning task.

## Base-image research

Registry metadata inspected for two published linux/amd64 candidates:

- `rocm/dev-ubuntu-26.04:10.1.0-full`
  - Digest: `sha256:4f5ed1bf6532a4b9920400401b0ad0f706af356dae61e40afefbfd6c8073f0ce`
  - Compressed layer total: 8.87 GB; not unpacked disk usage.
- `rocm/pytorch:rocm10.1.0_ubuntu26.04_py3.14_pytorch_release_2.14.0`
  - Digest: `sha256:68295d40dcdcb53d9b50828f30017faad8cf5ad9a8c7923c5a815b414b45e3e6`
  - Compressed layer total: 11.78 GB; not unpacked disk usage.

The development image's build metadata declares ROCm 10.1.0, package-based installation, multi-architecture GPU coverage, and `/opt/rocm`. Its image title says “ROCm runtime”; the `dev` repository name alone does not prove every header/compiler needed by ExLlamaV3 is installed. Verify hipcc, hipBLAS headers, Python development headers, and actual device support inside the image.

The PyTorch image's build history installs `torch[device-all]==2.14.0+rocm10.1.0`, `rocm[devel,device-all]`, torchvision, torchaudio, and Apex, then runs `rocm-sdk init`. The tag specifies Python 3.14. This is a wheel-based ROCm SDK setup rather than simply PyTorch installed on the development image's `/opt/rocm` packages. These are build-metadata observations; installed versions still need runtime verification.

Upstream ExLlamaV3 requires Torch >=2.6.0 and builds its extension against the installed Torch. Its ROCm build links hipBLAS and its `use_rocm_sdk_devel` helper handles both explicit ROCM_HOME/ROCM_PATH and pip-installed ROCm SDK development files. Both image layouts therefore have plausible upstream build paths, subject to actual compilation and gfx1201 execution.

Recommendation: use the matching PyTorch image as the first compatibility probe because it already combines ROCm 10.1.0 and Torch 2.14.0 and includes the development SDK in its installation history. Evaluate the development image if controlling the Python/Torch installation or reducing framework extras provides a concrete benefit. Its starting compressed size is smaller (8.87 versus 11.78 GB), but adding Torch/SDK wheels may erase that saving. Neither image has been validated on our host. Ubuntu versions inside and outside the container need not match; host driver compatibility still matters.

Next verification: inspect actual Python/Torch/HIP versions and SDK paths, confirm gfx1201 support, build ExLlamaV3 with the intended preinstalled Torch and build isolation disabled, install pinned TabbyAPI without CUDA extras, then perform the target-only and DFlash2 checks. Do not mix ROCm 7.2 Torch wheels with ROCm 10.1 packages merely because both are available.

Sources: [AMD development image](https://hub.docker.com/r/rocm/dev-ubuntu-26.04), [AMD PyTorch image](https://hub.docker.com/r/rocm/pytorch), [ExLlamaV3 build source](https://github.com/turboderp-org/exllamav3/blob/bd1f519172406a9560bd5c90e61000691bb69a07/setup.py), and [SDK selection helper](https://github.com/turboderp-org/exllamav3/blob/bd1f519172406a9560bd5c90e61000691bb69a07/exllamav3/util/cuda_flags.py). Digests above were resolved from `registry-1.docker.io`; tags remain mutable.
