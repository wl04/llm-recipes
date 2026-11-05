#!/usr/bin/env bash
set -euo pipefail
if [[ $# -gt 3 || ( ${1:-on} != on && ${1:-on} != off ) ]]; then
    echo "Usage: bash $0 [on|off] [context-tokens] [model-directory]" >&2
    exit 2
fi
recipe_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
model_dir=$(cd -- "${3:-$HOME/Models/llm-recipes}" && pwd)
mkdir -p -- "$model_dir/.cache"
groups=(--group-add "$(stat -c %g /dev/kfd)")
for node in /dev/dri/renderD*; do groups+=(--group-add "$(stat -c %g "$node")"); done
sudo docker run --rm --init --name llm-recipes-exl3 \
    --user "$(id -u):$(id -g)" "${groups[@]}" \
    --device=/dev/kfd --device=/dev/dri \
    --publish 127.0.0.1:5000:5000 \
    --env XDG_CACHE_HOME=/cache --env HF_HOME=/cache/huggingface \
    --env TRITON_CACHE_DIR=/cache/triton --env PYTHONUNBUFFERED=1 \
    --mount "type=bind,src=$recipe_dir,dst=/recipe,readonly" \
    --mount "type=bind,src=$model_dir,dst=/models,readonly" \
    --mount "type=bind,src=$model_dir/.cache,dst=/cache" \
    llm-recipes/exl3-rdna4:probe \
    python3 /recipe/scripts/serve.py --draft "${1:-on}" --context "${2:-4096}"
