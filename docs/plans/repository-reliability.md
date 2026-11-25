# Repository reliability improvement plan

Fix model preparation first: a successful download is of no use if the server cannot find the weights. Next, prevent large unintended copies and incorrect published measurements. The installer and baseline runner changes below can then proceed independently. Each numbered item includes a CPU-only regression test to write before the fix.

## Release blocker: model preparation

1. **Preserve the ExLlamaV3 recipe ID from preparation through serving.** The [shell wrapper](../../runtimes/exllamav3-tabbyapi/scripts/prepare-models.sh) mounts every recipe at `/recipe`, and [the helper](../../runtimes/exllamav3-tabbyapi/scripts/prepare_models.py) uses that basename as the model directory. Preserve the actual directory name in the mount and helper argument, and align the helper’s identifier validation with launcher discovery, including the dot in `qwen3.8`.
   **Acceptance:** Capture the wrapper’s Docker arguments without executing Docker for both `download` and `quantize-draft`. Use the shipped recipe, not a synthetic slug: the resolved destination must match the target and draft roots in [tabby.yml](../../recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/config/tabby.yml). Do not move or delete existing weights automatically.

## High priority: disk use and experiment integrity

2. **Keep model data out of installation snapshots.** The [quick start](../../README.md) can clone into `~/llm-recipes`, the default data root. Use a distinct checkout location in the example. Before [snapshot staging](../../scripts/install.py), resolve the checkout and data paths and reject layouts that would copy prepared model data into the app. Name both paths in the error and explain how to choose a separate location.
   **Acceptance:** With an isolated home and a sentinel weight under the default overlapping `recipes/` tree, installation fails before copying it or replacing the active snapshot. Cover a symlink alias of the same location and a successful install with separate roots.

3. **Validate log identity before updating an experiment.** In the [session CLI](../../scripts/baseline/cli.py), apply the [recipe and configuration checks](../../scripts/baseline/importer.py) even when the destination already has `profile.yaml`. Validate available facts before publishing any files; keep supported external log imports without facts distinct from logs with contradictory facts.
   **Acceptance:** Updating recipe B with logs from recipe A, or with mismatched configuration hashes, fails and leaves the profile, results, summary and index byte-for-byte unchanged. A matching update succeeds and preserves the authored profile and summary text.

4. **Calculate draft acceptance from the integer counts.** Store the full `accepted / proposed` ratio in [session statistics](../../scripts/baseline/session.py); round only the percentage in the [report](../../scripts/baseline/report.py). Recompute the derived field in the [published coding session](../../recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/003-2026-11-15-coding/session-results.json) from its recorded counts, then [regenerate the summary](../authoring.md#generate-configuration-guides). Do not edit the generated block by hand.
   **Acceptance:** `734,837 / 999,117` renders as **73.5%**, not 70.0%. Zero proposals still yield an unavailable rate rather than 0% or a division error. The generator’s `--check` passes.

## Installer correctness

5. **Report what was actually installed.** Capture the working tree’s dirty state alongside the commit when [building the snapshot](../../scripts/install.py). Propagate it from the [`VERSION` reader](../../scripts/paths.py) through baseline reporting and import; do not substitute `False` downstream. Keep older stamps readable without treating missing evidence as proof of a clean tree.
   **Acceptance:** Install from a temporary Git checkout, first clean and then with a modified runtime file. The installed revisions report the same commit but different dirty states. Include a stamp without the new field in the compatibility test.

6. **Make `install --skip-deps` produce usable commands.** Keep dependency installation off in this development mode. Select an existing interpreter with the required runtime dependencies and use it in both [command shims](../../scripts/install.py); if no usable interpreter is available, fail before activation. Leave normal installation on its private environment.
   **Acceptance:** In an isolated home with dependencies present, run both installed commands with `--help` from outside the checkout. With dependencies absent, assert a nonzero install result, an actionable message, and no changes to the existing app or shims.

## Baseline runner reliability

7. **Keep cleanup authorized for long managed runs.** Bound noninteractive renewal of the initial sudo ticket to the managed run’s lifetime, including interruption and teardown. Keep the [container-ID ownership check](../../scripts/baseline/lifecycle.py); never stop a replacement container by name. If authorization is revoked, preserve the measurements and report the cleanup failure with the owned container ID and a manual stop command.
   **Acceptance:** Simulate a workload longer than the ticket lifetime with a fake clock and command runner. Verify that normal and interrupted runs stop the owned container, renewal ends after teardown, and denied renewal does not hide cleanup failure. Attached runs must not acquire or renew credentials.

8. **Separate instance lookup from recipe selection.** For [`session <instance> --create`](../../scripts/baseline/cli.py), use the instance name to locate logs and `facts.json`’s `recipe` to choose the destination. Apply the identity checks in item 3. Preserve the documented `--logs` and `--experiment` paths for external logs.
   **Acceptance:** Starting a recipe with `--name coding` and reporting `session coding --create smoke` selects the real recipe, not `recipes/coding`. Use fixture logs, not a running server. Missing or invalid identity must not create an experiment in an unrelated recipe.

9. **Enforce the elapsed deadline on streamed responses.** In the [stream reader](../../scripts/baseline/api.py), check elapsed time before skipping keep-alives or accepting `[DONE]`. Keep the transport read timeout for silent connections and preserve partial output on deadline expiry.
   **Acceptance:** With a fake clock and a two-second deadline, feed one content event followed by keep-alives past the deadline. Expect `StreamInterrupted` with the original text, without waiting for another data event. Also test a late `[DONE]` and an on-time completion.

## Verification

Run the focused regression for each item, then `bash scripts/check.sh` from the checkout. This is the CPU gate; it does not establish that a model serves on the target hardware. For item 1, only when explicitly authorized on the RX 9070 XT workstation, follow the [recipe setup](../../recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/setup.md) with a separate data root, run `doctor`, and verify that the server loads the prepared target and draft and answers a request. Report that result separately from CI.
