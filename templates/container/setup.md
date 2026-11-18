# Model setup

<!-- Keep concrete recipe commands here. Shared behavior belongs in runtime, launcher, and client guides. Remove authoring instructions after filling in this template. -->

## Runtime and capacity

Link to `docs/runtimes/<runtime>.md#build-and-check`. State model-specific RAM, VRAM, and disk needs, distinguishing tested hardware from requirements.

## Prepare models

Provide the runtime preparation command with this recipe’s directory and the models root used by the launcher. Link `config/models.lock.json`; describe conversion choices and output location specific to this model. Link the runtime guide for verification, resume, and retry behavior.

## Launch

The `llm-recipes` command comes from the installed serving snapshot; link to [Quick start](../../README.md#quick-start) for installation and refresh. After preparation, check the recipe before starting. Link to [diagnostics](../../docs/launcher.md#diagnose-a-recipe) for check scope and troubleshooting.

```bash
sudo -v
llm-recipes doctor <recipe>
llm-recipes start <recipe> --detach
```

The instance name defaults to the recipe identifier and the model data root defaults to `~/llm-recipes`; add `--name`, `--models`, or capacity options only where the launch deviates from these defaults or from `config/launch.json`. Link [launch options](../../docs/launcher.md#launch-options) where the guide tells readers how to override defaults per launch or in the manifest. Include the API address and readiness check. Link `config/launch.json` and native settings. Explain any differences between the command and manifest defaults.

## Baseline

Run with the installed command:

```bash
llm-recipes-baseline run <recipe>
```

Add launch options only where the launch command above differs from the manifest defaults (for example `--context` and `--vision`). Document any overrides this recipe needs. Link to the baseline guide for thinking controls, model selection, preconditions, output, and publishing results. Do not repeat the guide's instructions here. Do not link results from this page: the setup guide is read before any experiment exists.

## Pi

Link to [Pi setup](../../docs/clients/pi.md#configure-a-recipe) and `config/pi.models.json`. Name the provider/model and the context and vision configuration that the example matches.

## Logs and stopping

```bash
llm-recipes logs <recipe> --follow
llm-recipes stop <recipe>
```

Link to [launcher controls](../../docs/launcher.md#foreground-and-background-execution) and the runtime's file-log documentation.

Use `llm-recipes tui` and press **s** on the recipe to open the launch form. It starts with the recipe defaults and accepts per-instance overrides. See the [launcher guide](../../docs/launcher.md#terminal-dashboard).

---

[Recipe](recipe.md) · [Runtime](../../docs/runtimes/<runtime>.md)
