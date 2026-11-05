#!/usr/bin/env python3
"""Send one short generation request to the local recipe server."""
import json
import time
from urllib.request import Request, urlopen


def main():
    base = "http://127.0.0.1:5000/v1"
    with urlopen(base + "/models", timeout=30) as response:
        models = json.load(response)["data"]
    expected = "qwen3.8-27b-exl3-3bpw"
    if not any(model["id"] == expected for model in models):
        raise RuntimeError(f"Expected loaded model {expected}; received {models}")
    request = Request(base + "/completions", data=json.dumps({
        "model": expected,
        "prompt": "Write a Python function that returns the unique items in a list, preserving their order.\n\ndef unique_items(items):\n",
        "max_tokens": 128,
        "temperature": 0,
        "seed": 42,
        "stream": False,
    }).encode(), headers={"Content-Type": "application/json"})
    started = time.monotonic()
    with urlopen(request, timeout=600) as response:
        result = json.load(response)
    elapsed = time.monotonic() - started
    if not result.get("choices") or not result["choices"][0].get("text"):
        raise RuntimeError(f"Empty generation: {result}")
    print(json.dumps({"request_seconds": round(elapsed, 3), **result}, indent=2))


if __name__ == "__main__":
    main()
