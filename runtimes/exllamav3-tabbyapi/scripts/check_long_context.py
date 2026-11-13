#!/usr/bin/env python3
"""Exercise a near-full context with synthetic records and a short completion."""

import argparse
import hashlib
import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

BASE = "http://127.0.0.1:5000/v1"


def post(route, data, timeout=120, base=BASE):
    request = Request(
        base + route, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"HTTP {error.code}: {error.read().decode()}") from error


def build_prompt(budget, nonce, count):
    header = f"Run {nonce}. Read these synthetic service records.\n"
    suffix = (
        "\nWrite a Python function that counts records by service name."
        "\n\ndef count_by_service(records):\n"
    )

    def render(n):
        records = (
            f"record {i}: service=worker_{i % 97}, duration_ms={(i * 37) % 10000}, "
            f"status={'ok' if i % 13 else 'retry'}\n"
            for i in range(n)
        )
        return header + "".join(records) + suffix

    low, high = 0, 128
    best, tokens = render(0), count(render(0))
    if tokens > budget:
        raise ValueError("Token budget is too small for the prompt instructions")
    while count(render(high)) <= budget:
        high *= 2
    while low <= high:
        mid = (low + high) // 2
        prompt = render(mid)
        length = count(prompt)
        if length <= budget:
            best, tokens = prompt, length
            low = mid + 1
        else:
            high = mid - 1
    return best, tokens


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default=BASE)
    parser.add_argument("--prompt-tokens", type=int, default=130000)
    parser.add_argument("--context", type=int, default=131072)
    parser.add_argument("--output-tokens", type=int, default=128)
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()
    if min(args.prompt_tokens, args.output_tokens, args.timeout) <= 0:
        parser.error("token counts and timeout must be positive")
    if args.prompt_tokens + args.output_tokens + 256 > args.context:
        parser.error("leave at least 256 tokens of headroom beyond prompt + output")
    nonce = uuid4().hex
    print("Counting synthetic prompt tokens with the server tokenizer…", flush=True)
    prompt, measured = build_prompt(
        args.prompt_tokens,
        nonce,
        lambda text: post(
            "/token/encode", {"text": text, "add_bos_token": False}, base=args.base_url.rstrip("/")
        )["length"],
    )
    print(
        f"Sending {measured:,} input tokens; up to {args.output_tokens} output tokens. "
        "Watch amdgpu_top during prefill.",
        flush=True,
    )
    started = time.monotonic()
    result = post(
        "/completions",
        {
            "model": args.model,
            "prompt": prompt,
            "max_tokens": args.output_tokens,
            "temperature": 0,
            "seed": 42,
            "add_bos_token": False,
            "stream": False,
        },
        timeout=args.timeout,
        base=args.base_url.rstrip("/"),
    )
    report = {
        "workload": "synthetic service records",
        "run_nonce": nonce,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "tokenizer_prompt_tokens": measured,
        "request_seconds": round(time.monotonic() - started, 3),
        **result,
    }
    print(json.dumps(report, indent=2))
    if not result.get("choices") or not result["choices"][0].get("text"):
        raise RuntimeError("Server returned no generated text")
    actual = result.get("usage", {}).get("prompt_tokens")
    if actual != measured:
        raise RuntimeError(
            "Prompt count mismatch: "
            f"sent {measured}, server reports {actual}; inspect truncation/tokenization"
        )


if __name__ == "__main__":
    main()
