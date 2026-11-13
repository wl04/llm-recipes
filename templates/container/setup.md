# Model setup

<!-- Keep concrete recipe commands here. Shared behavior belongs in runtime, launcher, and client guides. Remove authoring instructions after filling in this template. -->

## Runtime and capacity

Link to `docs/runtimes/<runtime>.md#build-and-check`. State model-specific RAM, VRAM, and disk needs, distinguishing tested hardware from requirements.

## Prepare models

Provide the runtime preparation command with this recipe's directory and external models path. Link `config/models.lock.json`; describe conversion choices and output location specific to this model. Link the runtime guide for verification, resume, and retry behavior.

## Launch

Run from the repository root:

```bash
python3 scripts/launch.py start <recipe> --name coding --detach \
  --models "$HOME/Models/llm-recipes"
python3 scripts/launch.py logs coding --follow
```

Include the API address and readiness check. Link `config/launch.json` and native settings. Explain any differences between the command and manifest defaults.

## Checks

Provide runnable check commands with the served model ID. Link to the runtime guide for check behavior and token limits.

## Pi

Link to [Pi setup](../../docs/clients/pi.md#configure-a-recipe) and `config/pi.models.json`. Name the provider/model and the context and vision configuration that the example matches.

## Logs and stopping

```bash
python3 scripts/launch.py stop coding
```

Link to [launcher controls](../../docs/launcher.md#foreground-and-background-execution) and the runtime's file-log documentation.

---

[Recipe](recipe.md) · [Runtime](../../docs/runtimes/<runtime>.md)
