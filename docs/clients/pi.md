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
