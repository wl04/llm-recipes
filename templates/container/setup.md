# Model setup

<!-- Keep concrete recipe commands here. Shared behavior belongs in runtime, launcher, and client guides. Remove authoring instructions after filling in this template. -->

## Runtime and capacity

Link to `docs/runtimes/<runtime>.md#build-and-check`. State model-specific RAM, VRAM, and disk needs, distinguishing tested hardware from requirements.

## Prepare models

Provide the runtime preparation command with this recipe's directory and external models path. Link `config/models.lock.json`; describe conversion choices and output location specific to this model. Link the runtime guide for verification, resume, and retry behavior.

## Launch

After preparation, check the recipe with `python3 scripts/launch.py doctor <recipe> --models "$HOME/Models/llm-recipes"`. Link to [diagnostics](../../docs/launcher.md#diagnose-a-recipe) for check scope and troubleshooting.

Run from the repository root:

```bash
python3 scripts/launch.py start <recipe> --name coding --detach \
  --models "$HOME/Models/llm-recipes"
python3 scripts/launch.py logs coding --follow
```

Include the API address and readiness check. Link `config/launch.json` and native settings. Explain any differences between the command and manifest defaults.

## Checks

Provide a Bash block that waits for readiness, displays the loaded model ID, and saves each supported check to a fresh directory. Use the runtime's actual endpoints and helpers; include tools, vision, and long context when supported. Keep input plus output within the configured context. For example:

```bash
(
  set -euo pipefail
  out=$(mktemp -d "${TMPDIR:-/tmp}/recipe-checks-$(date +%F)-XXXXXX")
  echo "Saving checks to $out"
  # Insert readiness and loaded-model commands for this API server.
  # Insert each check with its explicit model ID, piping JSON stdout to:
  #   tee "$out/<check>.json"
)
```

Use stderr for helper progress so saved JSON remains parseable. Use the shared `assets/checks/amdgpu-top.png` as the vision input when supported, with an optional `--image` override; link [baseline reading details](../../docs/vision-check.md). The subshell keeps shell options local; `pipefail` propagates failures through `tee`. Link the runtime guide for check behavior and token limits. Outputs stay outside the repository; record the relevant statistics and observations in the experiment summary.

## Pi

Link to [Pi setup](../../docs/clients/pi.md#configure-a-recipe) and `config/pi.models.json`. Name the provider/model and the context and vision configuration that the example matches.

## Logs and stopping

```bash
python3 scripts/launch.py stop coding
```

Link to [launcher controls](../../docs/launcher.md#foreground-and-background-execution) and the runtime's file-log documentation.

---

[Recipe](recipe.md) · [Runtime](../../docs/runtimes/<runtime>.md)
