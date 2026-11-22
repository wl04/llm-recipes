# Strata runtime

Strata serves GGUF models through its own API on Ubuntu x86_64 with Docker and a gfx1201 GPU. Start with the setup guide for your model. Each guide gives the commands for its pinned image, weights, and Pi provider.

| Recipe | Pinned Strata build | Setup |
|---|---|---|
| Unsloth UD-IQ3_XXS | [v0.2.18](../../runtimes/strata/releases/v0.2.18/runtime.json) | [Build and run](../../recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/setup.md) |
| ISTA IQ3_XXS | [v0.2.13 + 95 commits](../../runtimes/strata/releases/v0.2.13-95-gdbb2d168/runtime.json) | [Build and run](../../recipes/qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram/setup.md) |

## Build and check

Docker needs access to `/dev/kfd` and `/dev/dri`. The recipe's build command reads its selected release lock and checks binary startup, API imports and a HIP kernel. If the compiler runs short of RAM, add `--max-jobs 2`.

## Preparation

The data root defaults to `~/llm-recipes`. Set `LLM_RECIPES_HOME` before preparation and launch to use another location. Preparation verifies the published GGUF shards and projector under `recipes/<recipe>/models/`. Recipes using the same pinned checkpoint share the verified BF16 MTP source under `.cache/strata/mtp/<repository>/<revision>/`.

Each recipe keeps its generated pack, tokenizer, Q2_0 draft and receipt in `recipes/<recipe>/prepared/<version>/`. Repeating preparation reuses a completed matching receipt and resumes partial downloads.

## Serving

The server publishes its API on loopback. `server.log` contains API output and `engine.log` contains engine and vision diagnostics. Both survive container removal under `<data root>/logs/<instance>/`. Baseline runs keep their own logs in the run directory. See the [launcher controls](../launcher.md#foreground-and-background-execution) and [baseline guide](../baseline.md).

## Upgrade Strata on the RX 9070 XT

For a release already selected on `main`, pull and reinstall with serving instances stopped. If you already prepared that build on this machine, you can start the recipe immediately. For a fresh machine, follow the recipe setup above.

```bash
git pull --ff-only
python3 scripts/install.py install
```

To evaluate a **new upstream release**, run the following in Bash from your main checkout with the GPU free:

```bash
read -rp 'Strata release tag (vX.Y.Z): ' tag
python3 scripts/upgrade_strata.py "$tag"
```

The script creates or resumes a sibling worktree for the tag, checks the image, and prepares each installed Strata recipe with local weights. Choose one of the printed commands to start the candidate or run its baseline. The baseline starts its own server.

The [upgrade configuration](../../runtimes/strata/upgrade.json) controls the ROCm base tag, build parallelism and engine options. For a second build of the same release, set a distinct image suffix and pass the same `--config <file>` to preparation, adoption and deletion.

### Adopt and publish

To select the tested candidate locally, run this from the main checkout:

```bash
python3 scripts/upgrade_strata.py "$tag" --adopt
```

Adoption verifies the prepared recipes, commits their release selections and pins in the candidate branch, and points the installed launcher at that worktree. Keep the worktree while it is selected. To publish, use the push command printed by the script and merge the branch through your usual review workflow. Other machines can then pull and reinstall.

On reinstall, a recipe switches to the installed settings if its release and build lock match the active trial. Otherwise the launcher keeps the trial selected. If the trial's `config/launch.json` is missing, the launcher warns and uses the installed recipe and runtime for that recipe only. Restoring the manifest reactivates the trial without reinstalling. To adopt another trial for the affected recipe, first restore the manifest or roll back the trial.

### Discard or roll back

Stop the trial's containers. To discard an unpublished trial or restore the previous local selection:

```bash
python3 scripts/upgrade_strata.py "$tag" --delete
```

Deletion removes the trial worktree, image tag and version-specific preparations. Published weights and baseline reports stay in the data root. Roll back stacked trials newest first. The command refuses deletion while the main checkout or installed defaults select that release.

---

[All recipes](../../README.md) · [Launcher](../launcher.md) · [Authoring](../authoring.md)
