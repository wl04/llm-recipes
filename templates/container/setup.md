# Model setup

<!-- Keep concrete recipe commands here. Shared behavior belongs in runtime, launcher, and client guides. Remove authoring instructions after filling in this template. -->

## Runtime and capacity

Link to `docs/runtimes/<runtime>.md#build-and-check`. State model-specific RAM, VRAM, and disk needs, distinguishing tested hardware from requirements.

## Prepare models

Provide the runtime preparation command with this recipe's directory and external models path. Link `config/models.lock.json`; describe conversion choices and output location specific to this model. Link the runtime guide for verification, resume, and retry behavior.

## Launch

After preparation, check the recipe with `llm-recipes doctor <recipe>`. Link to [diagnostics](../../docs/launcher.md#diagnose-a-recipe) for check scope and troubleshooting.

```bash
llm-recipes start <recipe> --detach
llm-recipes logs <recipe> --follow
```

The instance name defaults to the recipe identifier and the model data root defaults to `~/llm-recipes`; add `--name`, `--models`, or capacity options only where the launch deviates from these defaults or from `config/launch.json`. Include the API address and readiness check. Link `config/launch.json` and native settings. Explain any differences between the command and manifest defaults.

## Baseline

Run from the repository root:

```bash
sudo -v
python3 scripts/run_baseline.py run <recipe>
```

Add launch options only where the launch command above differs from the manifest defaults (for example `--context` and `--vision`). Mention thinking only when the reader has to act on it (for example, a server that thinks by default and needs `--request-extra` to disable it); otherwise the baseline guide covers it. Link the guide for preconditions, the phases, the output location, and how to publish a result. Do not repeat the guide's instructions here. Do not link results from this page: the setup guide is read before any experiment exists.

## Pi

Link to [Pi setup](../../docs/clients/pi.md#configure-a-recipe) and `config/pi.models.json`. Name the provider/model and the context and vision configuration that the example matches.

## Logs and stopping

```bash
llm-recipes stop <recipe>
```

Link to [launcher controls](../../docs/launcher.md#foreground-and-background-execution) and the runtime's file-log documentation.

---

[Recipe](recipe.md) · [Runtime](../../docs/runtimes/<runtime>.md)
