# ExLlamaV3 / TabbyAPI runtime

The shared runtime builds ExLlamaV3 against AMD's ROCm/PyTorch image and serves through TabbyAPI. It targets `gfx1201` and selects the RX 9070 XT by name. Recipes provide target/draft locks, conversion options, native TabbyAPI settings, and Pi metadata.

## Build and check

To test a newer engine or ROCm image, follow [Upgrade a container runtime](../launcher.md#upgrade-a-container-runtime).

Use the pinned build command in the recipe setup on Ubuntu x86_64 with Docker and working AMD `/dev/kfd` and `/dev/dri` devices. Lower `--max-jobs` if compiler memory use is excessive. The image check verifies engine imports and GPU matrix multiplication.

The recipe’s `config/launch.json` selects a release under [the runtime’s release directory](../../runtimes/exllamav3-tabbyapi/releases). Its `runtime.json` names the image, and `container/versions.lock.json` pins the AMD image digest, engine and API server revisions, and source archive hashes. Run `llm-recipes list` to see the selected image, including local trials.

The base image supplies Torch, the ROCm SDK, and Triton. The [dependency overlay](../../runtimes/exllamav3-tabbyapi/container/requirements.lock) pins the remaining Python packages with hashes. ExLlamaV3 compiles against the base image’s Torch with build isolation disabled. Source licenses are under `/opt/src`. Serving and draft conversion verify the image’s build lock against the selected release.

For a separate image, pass `--tag candidate` to the builder. Use `--runtime-image llm-recipes/exl3-rdna4:candidate` with the launcher or baseline and set `LLM_RECIPES_RUNTIME_IMAGE=llm-recipes/exl3-rdna4:candidate` for the preparation commands. Give a different build lock its own release key and image tag. Downloads are shared between builds of the recipe.

## Preparation

The recipe's setup guide supplies the `prepare-models.sh` commands for `download` and `quantize-draft`. Its model lock defines downloads, directory names, and conversion arguments.

An optional third argument selects the host models directory; its default is the data root (`~/llm-recipes`, overridable with `LLM_RECIPES_HOME`), the same directory `--models` uses. Both commands run as the host UID and mount the recipe and runtime read-only. Quantization also receives GPU access. Downloads verify file sizes and Git/LFS hashes, then save checksum manifests. Converted drafts record source metadata, build pins, conversion arguments, and output checksums. Preparation is locked against another writer in the same model directory.

Interrupted downloads can be rerun. Conversion requires fresh output and work directories: move failed outputs aside before retrying. With a release selected, the converter puts both directories under `prepared/<build-key>/` within the recipe data folder. The serving helper resolves TabbyAPI’s draft directory under the same key. The target and original draft stay at their model-lock paths.

Test an upgrade against the installed target and converted draft with `python3 scripts/upgrade_runtime.py exllamav3-tabbyapi`. If the draft source lock, target compatibility and conversion settings match, the candidate can use the verified EXL3 files without the original draft. The candidate baseline must load the EXL3 files and exercise DFlash2 generation; a successful image test alone does not verify the draft format. If conversion settings change, have the locked original draft available locally.

## Serving

The [launcher](../launcher.md#shared-runtimes) provides mounts and invokes the serving helper.

The helper validates `config/tabby.yml` against the pinned TabbyAPI schema, verifies model preparation metadata and image pins, selects the GPU before HIP initialization, and starts TabbyAPI in a temporary writable directory. That directory's `logs` entry points to `/logs`. TabbyAPI rotates file logs at 20 MB, compresses them, and retains them for one week by default; native logging settings control retention.

`--vision on|off` selects GPU-resident vision, `--draft on|off` controls the configured draft, and `--context` sets sequence and cache capacity. Native sampling values remain in the recipe. Entries with `force: false` supply defaults; explicit request values take precedence. The default host API port is 5000; the UI is `/ui/` and status is `/ui/status`. With admin access, select a running request or one of the last 20 completed requests to inspect its prompt and generated text. [TabbyAPI status page](https://github.com/theroyallab/tabbyAPI/blob/8f92fac5d9307bf1e09668c3715b32ff46ad0333/docs/03.-Usage.md#status-page)

## Baseline and clients

Run the baseline command from the recipe’s setup guide. The runner selects the target named in `tabby.yml` because `/v1/models` can also list other local model directories. It sends `chat_template_kwargs.enable_thinking: false` for the performance and functional cases and `true` for the reasoning case. The [baseline guide](../baseline.md#what-a-run-measures) covers overrides.

Streamed usage supplies cached-token counts. The runner counts prompts through `/v1/token/encode`, which applies the chat template and omits the final assistant prefix. Prefill and draft acceptance come from the server log.

Use [Pi setup](../clients/pi.md) and the recipe's provider configuration.

---

[All recipes](../../README.md) · [Launcher](../launcher.md) · [Authoring](../authoring.md)
