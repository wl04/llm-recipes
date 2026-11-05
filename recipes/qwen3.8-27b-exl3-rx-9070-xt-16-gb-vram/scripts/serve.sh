#!/usr/bin/env bash
set -euo pipefail
usage() {
    cat <<'HELP'
Usage: bash serve.sh [options]
  --draft on|off       DFlash2 drafting (default: on)
  --vision on|off      GPU-resident vision (default: off)
  --context TOKENS     Context and cache capacity (default: 4096)
  --models DIRECTORY   External model directory (default: ~/Models/llm-recipes)
  -h, --help           Show this help
HELP
}
fail() { echo "$*" >&2; usage >&2; exit 2; }
draft=on
vision=off
context=4096
model_dir="$HOME/Models/llm-recipes"
while (( $# )); do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --draft|--vision|--context|--models)
            (( $# >= 2 )) && [[ -n $2 && $2 != --* ]] || fail "Missing value for $1"
            case "$1" in
                --draft) draft=$2 ;;
                --vision) vision=$2 ;;
                --context) context=$2 ;;
                --models) model_dir=$2 ;;
            esac
            shift 2 ;;
        *) fail "Unknown argument: $1. Use named options." ;;
    esac
done
[[ $draft == on || $draft == off ]] || fail "--draft must be on or off"
[[ $vision == on || $vision == off ]] || fail "--vision must be on or off"
[[ $context =~ ^[0-9]{1,9}$ ]] || fail "--context must be an integer"
context=$((10#$context))
(( context >= 1024 && context % 256 == 0 )) || fail "--context must be at least 1024 and a multiple of 256"
recipe_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
model_dir=$(cd -- "$model_dir" && pwd)
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
    python3 /recipe/scripts/serve.py --draft "$draft" --vision "$vision" --context "$context"
