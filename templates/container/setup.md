# Setup

<!-- Fill in the current commands and supported capabilities; remove authoring comments. -->

## Prerequisites

Describe the supported OS, GPU architecture, memory and storage needs, and required host tools. Name the inference engine and API server. Include Python 3 and Docker access for the shared launcher.

## Build the image

Provide the recipe's image-build command. Its image tag must match `config/launch.json`.

## Prepare the models

Provide explicit download and conversion commands using the locked artifacts. State the external model directory and required disk space.

## Start the server

Replace `<recipe>` with this recipe's directory name. Run from the repository root:

```bash
python3 scripts/launch.py start <recipe> --name coding --detach \
  --models "$HOME/Models/llm-recipes"
```

Document the recipe's context, drafting, and vision defaults from `config/launch.json`, supported overrides, and API address. Include the server readiness check and a generation command.

## Connect the client

Provide the client installation and connection settings, including API URL, served model identifier, and supported reasoning, tool-use, and image options.

## Manage the server

```bash
python3 scripts/launch.py ps
python3 scripts/launch.py status coding
python3 scripts/launch.py logs coding --follow
python3 scripts/launch.py stop coding
```

`--detach` runs in the background. Without it, startup stays attached and Ctrl+C stops the server. Ctrl+C while following logs exits the log viewer and leaves the server running.

The instance name defaults to the recipe directory name. Use `--name` to choose another name and `--port` to select an available host port. Update the client's API address when changing the port. `status` reports container state; use the server readiness check to confirm the model is ready.

Logs default to `${XDG_STATE_HOME:-$HOME/.local/state}/llm-recipes/coding` for this named instance. Use `--logs DIRECTORY` to select another directory. The container is removed on exit; mounted file logs remain on the host. Describe this server's log filenames and retention settings.

Edit the native server configuration and restart to change server defaults. Document when the image needs rebuilding.

---

[Recipe](recipe.md) · [Implementation](implementation.md)
