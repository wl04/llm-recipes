# Launcher guide

Run commands from the repository root using host Python 3 and `sudo docker`. Build the image and prepare models following the selected recipe's `setup.md`.

## Recipes and instances

A recipe defines a prepared model/server setup. An instance is one launch of that recipe. The API-server adapter controls startup; the inference engine performs inference. Supported combinations are `tabbyapi` / `exllamav3` and `strata` / `strata`.

```bash
python3 scripts/launch.py list
python3 scripts/launch.py start <recipe> --name coding --detach \
  --models "$HOME/Models/llm-recipes"
python3 scripts/launch.py ps
python3 scripts/launch.py status coding
python3 scripts/launch.py logs coding --follow
python3 scripts/launch.py stop coding
```

Replace `<recipe>` with a directory identifier from `list`. Without `--name`, the recipe identifier becomes the instance name. Names contain up to 160 lowercase letters, digits, dots, dashes, or underscores and start with a letter or digit. Distinct instances require distinct names and available host ports. Docker reports name or port conflicts.

`ps` discovers running instances through Docker labels. `status` reports container state; use the recipe's readiness endpoint or status page to confirm the model has loaded. `status`, `logs`, and `stop` select an instance independently of recipe discovery.

## Foreground and background execution

| Command | Behavior | Ctrl+C |
| --- | --- | --- |
| `start <recipe>` | Runs attached to the server | Stops the server |
| `start <recipe> --detach` | Returns to the shell after starting the container | The server runs independently |
| `logs <instance> --follow` | Streams container console output | Ends log following; the server keeps running |

Use `stop <instance>` to stop a background server. Rerun its start command to restart it. Containers are removed on exit; mounted model files, caches, and file logs remain on the host.

## Launch options

Explicit CLI options override the recipe's launch defaults.

| Option | Default | Purpose |
| --- | --- | --- |
| `--name NAME` | Recipe identifier | Instance name |
| `--models DIRECTORY` | `~/Models/llm-recipes` | Prepared model directory |
| `--logs DIRECTORY` | Per-instance state directory | Persistent server file logs |
| `--port PORT` | Manifest port | Host loopback port; update the client's API address when changed |
| `--context TOKENS` | Manifest context | Context capacity |
| `--draft on\|off` | Manifest drafting setting | Configured speculative decoding |
| `--vision on\|off\|cpu` | Manifest vision setting | TabbyAPI: `on/off` GPU vision; Strata: `cpu/off` CPU vision |
| `--detach` | Off | Background execution |
| `--dry-run` | Off | Print the command without creating directories or accessing GPU devices |

Both adapters accept contexts of at least 1,024 tokens in multiples of 256, up to nine digits. Model and memory limits still determine usable context. GPU device group IDs are resolved at actual startup; dry runs omit them.

Run `python3 scripts/launch.py start --help` for CLI help.

## Persistent logs

The default directory is `${XDG_STATE_HOME:-$HOME/.local/state}/llm-recipes/<instance>`. Use `--logs` to choose another location, including an existing log directory.

`logs --follow` reads console output while the container exists. After it exits, read the files in the host log directory. Server-specific filenames, rotation, and retention are documented in the recipe's setup guide.

## Launch manifest

The launcher discovers `recipes/*/config/launch.json`. The recipe directory supplies its identifier. Every manifest field is required:

| Field | Meaning |
| --- | --- |
| `adapter` | API-server integration: `tabbyapi` or `strata` |
| `engine` | Inference engine: `exllamav3` or `strata` |
| `image` | Prepared Docker image reference |
| `port` | Container API port and default host port |
| `context` | Default context capacity |
| `draft` | Default `on` or `off` |
| `vision` | TabbyAPI: `on/off`; Strata: `cpu/off` |

Use the [container manifest template](../templates/container/config/launch.json) as the TabbyAPI example; for Strata, set both `adapter` and `engine` to `strata`, select its image and port, and use `cpu` or `off` for vision. Native server settings stay in their own file, such as `config/tabby.yml`. Dated `profile.yaml` files record settings used for measured results. Desktop recipes use their application's launch flow.

## Implementation boundaries

[`scripts/launch.py`](../scripts/launch.py) handles CLI input and presentation. [`scripts/launcher.py`](../scripts/launcher.py) handles discovery, validation, command planning, and process execution. Docker labels record instance, recipe, API-server adapter, and engine; `ps` uses these labels without a separate state database.

Recipe entry points validate native settings and start the server. Recipe-specific preparation, GPU selection, mounts, and image checks are described in each implementation guide.

---

[All recipes](../README.md) · [Authoring](authoring.md) · [Pi setup](clients/pi.md) · [Development](project-instructions.md)
