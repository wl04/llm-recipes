# Pi setup

Run [Pi](https://github.com/badlogic/pi-mono) on the host in the project you want it to work on. Pi handles files, shell commands, and conversation history, and connects to the recipe's API server.

## Install on Ubuntu

Install [nvm using its official instructions](https://github.com/nvm-sh/nvm#installing-and-updating), then open a new terminal. Use Node.js LTS and the latest stable Pi release:

```bash
nvm install --lts
nvm alias default 'lts/*'
nvm use default
npm install -g --ignore-scripts @earendil-works/pi-coding-agent@latest
node --version
pi --version
```

Run npm as your regular user. Repeat the install command to update Pi or after switching Node versions. Record Pi and Node versions with experiment results.

## Shared extensions

The author's shared Pi setup uses these extensions across recipes and projects:

| Extension | Purpose |
|---|---|
| [pi-mcp-adapter](https://github.com/nicobailon/pi-mcp-adapter) | Connect MCP servers and discover their tools on demand. |
| [pi-web-access](https://github.com/nicobailon/pi-web-access) | Search the web and fetch page content. |
| [context-mode](https://github.com/mksglu/context-mode) | Process and index large tool outputs, then retrieve relevant portions into the conversation. |
| [rpiv-ask-user-question](https://github.com/juicesharp/rpiv-mono/tree/main/packages/rpiv-ask-user-question) | Ask structured questions with selectable answers. |
| [rpiv-todo](https://github.com/juicesharp/rpiv-mono/tree/main/packages/rpiv-todo) | Track tasks in a live overlay that survives reload and compaction. |

Install the upstream packages into Pi's shared user configuration:

```bash
pi install npm:pi-mcp-adapter
pi install npm:pi-web-access
pi install npm:context-mode
pi install npm:@juicesharp/rpiv-ask-user-question
pi install npm:@juicesharp/rpiv-todo
```

Restart Pi after installation. Use `pi list` to inspect installed packages. Follow each extension's linked documentation to configure MCP servers, search providers, and other preferences.

When extension versions or settings materially affect an experiment, record them with its results. Context management and tool-output filtering can change prompt sizes, cache reuse, and compaction behavior.

## Configure a recipe

Use Pi's standard `~/.pi/agent/` directory. Follow the recipe's `setup.md` for the provider and model configuration, preserving existing entries in `models.json` and `settings.json`.

The recipe supplies the API address, model identifier, context window, and compatibility settings for reasoning, tool calls, and images. Match the context window and capabilities to the running server. If the launcher's host port changes, update the provider's API address.

## Start a session

Once the API server is ready, open another terminal:

```bash
cd /path/to/your/project
pi
```

Use `/model` to select the configured model and `/thinking` to change reasoning effort. Follow the recipe's instructions for supported thinking settings.

---

[All recipes](../../README.md) · [Launcher](../launcher.md)
