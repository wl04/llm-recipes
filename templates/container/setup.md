# Setup

<!-- Fill in the current commands and supported capabilities; remove authoring comments. -->

## Prerequisites

Describe the supported OS, GPU architecture, memory and storage needs, and required host tools. Name the inference engine and API server. Include Python 3 and Docker access for the shared launcher.

## Build the image

Link to `docs/runtimes/<runtime>.md` for the build and image check. `config/launch.json` selects a shared runtime whose `runtime.json` supplies the image reference.

## Prepare the models

Provide explicit commands invoking the runtime preparation helper with this recipe directory. State the model lock, conversion options, external data directory, required disk space, and memory requirements.

## Start the server

Replace `<recipe>` with this recipe's directory name. Run from the repository root:

```bash
python3 scripts/launch.py start <recipe> --name coding --detach \
  --models "$HOME/Models/llm-recipes"
```

Document the recipe's context, drafting, and vision defaults from `config/launch.json`, supported overrides, and API address. Vision options depend on the adapter: TabbyAPI uses `on/off`; Strata uses `cpu/off`. Include the server readiness check and a generation command.

## Connect the client

Link to the shared [Pi setup guide](../../docs/clients/pi.md) when using Pi. Provide recipe-specific connection settings, including API URL, served model identifier, and supported reasoning, tool-use, and image options.

## Manage the server

```bash
python3 scripts/launch.py ps
python3 scripts/launch.py status coding
python3 scripts/launch.py logs coding --follow
python3 scripts/launch.py stop coding
```

Link to the [launcher guide](../../docs/launcher.md) for shared commands, instance naming, ports, log locations, and Ctrl+C behavior. Describe this server's file-log names and retention settings.

Edit the native server configuration and restart to change server defaults. Link to the runtime guide for image rebuild requirements.

---

[Recipe](recipe.md) · [Runtime](../../docs/runtimes/<runtime>.md)
