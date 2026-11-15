#!/usr/bin/env python3
"""One-off migration of experiment profiles from the flat settings map to schema v2.

Maps old human-keyed ``settings`` entries to the canonical groups understood by
``generate_configurations.py`` (serving / sampling / thinking / requests / notes).
Residual prose of the removed ``Request policy`` rows is preserved verbatim in
``notes`` through the explicit ``EXPERIMENT_EDITS`` table below: splitting prose
is a one-time reviewed editorial act, so it is encoded as data and reviewed once.
Sampling values come from ``results.json`` ``policy.performance`` when the
experiment has one. Rerunning on an already-migrated profile is a no-op.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]

SERVING_MAP: dict[str, str] = {
    "Served model id": "served_model_id",
    "Speculative decoding": "speculative_decoding",
    "Context length": "context_length_tokens",
    "Cache capacity": "cache_capacity",
    "Target cache": "target_cache",
    "Draft cache": "draft_cache",
    "Chunk size": "chunk_size",
    "Maximum batch size": "max_batch_size",
    "Concurrent predictions": "parallel_predictions",
    "Automatic hardware optimization": "auto_hardware_optimization",
    "GPU offload": "gpu_offload",
    "CPU thread pool": "cpu_thread_pool",
    "Evaluation batch size": "eval_batch_size",
    "Physical batch size": "physical_batch_size",
    "Flash Attention": "flash_attention",
    "K / V cache quantization": "kv_cache_quantization",
    "KV cache GPU offload / Unified KV cache": "kv_gpu_offload_unified",
    "Context checkpoints": "ctx_checkpoints",
    "Keep model in memory / mmap": "memory_map",
    "Max / min draft tokens / draft probability": "draft_token_limits",
    "Context overflow": "context_overflow",
    "On-demand tensor loading": "on_demand_tensor_loading",
    "KV cache": "kv_cache",
    "GPU resident KV cells": "gpu_resident_kv_cells",
    "Expert cache": "expert_cache",
    "Prefill": "prefill",
    "Maximum draft tokens": "max_draft_tokens",
    "Minimum draft probability": "min_draft_probability",
    "Draft vocabulary": "draft_vocabulary",
    "Vision": "vision",
    "Vision offload": "vision_offload",
    "Vision minimum image tokens": "vision_min_image_tokens",
    "Vision maximum image tokens": "vision_max_image_tokens",
    "Expert pool": "expert_pool",
    "Conversation cache": "conversation_cache",
    "Hyper connection projections": "hyper_connection_projections",
    "Route tail skip": "route_tail_skip",
    "Tensor parallel": "tensor_parallel",
    "GPU selection": "gpu_selection",
    "Recurrent state": "recurrent_state",
    "System recurrent cache MB": "sysmem_recurrent_cache_mib",
}
SAMPLING_MAP: dict[str, str] = {
    "Temperature": "temperature",
    "Top K": "top_k",
    "Top k": "top_k",
    "Top P": "top_p",
    "Top p": "top_p",
    "Min P": "min_p",
    "Min p": "min_p",
    "Repeat penalty": "repetition_penalty",
    "Repetition penalty": "repetition_penalty",
    "Presence penalty": "presence_penalty",
    "Seed": "seed",
}
THINKING_MAP: dict[str, str] = {
    "Thinking enabled": "enabled",
    "Enable Thinking": "enabled",
    "Thinking control": "control",
    "Reasoning budget": "budget",
    "Server reasoning budget": "budget",
}
REQUESTS_MAP: dict[str, str] = {
    "Request endpoint": "endpoint",
    "Token counting": "token_counting",
    "Forced tool call": "forced_tool_call",
    "Maximum output tokens": "max_output_tokens",
    "Limit response length": "max_output_tokens",
}
# Dropped when the value carries no information the new schema expresses elsewhere.
DROPPED_WHEN_EMPTY: dict[str, str] = {
    "Workload suite": "derived from results.json suite_version",
    "Reasoning effort": "null adds nothing",
}
SPECIAL_KEYS = {"Request policy", "Server sampling", "Configuration notes", "Coding requests"}

# One-time reviewed editorial split of the removed prose rows, keyed by
# "<recipe>/<experiment>". ``requests``/``thinking`` override mechanically
# migrated rows; ``notes`` sentences are appended after the configuration notes.
EXPERIMENT_EDITS: dict[str, dict[str, Any]] = {
    "qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/001-2026-11-14-baseline": {
        "requests": {
            "endpoint": "/v1/chat/completions",
            "streaming": "Performance requests streamed",
            "concurrency": 1,
            "token_counting": "/v1/token/encode",
        },
        "thinking": {
            "enabled": False,
            "control": "chat_template_kwargs.enable_thinking=false",
        },
        "notes": [
            "Request policy: functional checks run at temperature 0."
            " Output caps: 1,024 for context cases, 2,048 for sustained generation,"
            " 256 for text/tools, 512 for vision.",
            "Software configuration basis: repository runtime/model locks and native"
            " settings; the running image ID and engine version were recorded by the"
            " baseline run.",
        ],
    },
    "qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/002-2026-11-07-coding-gpu-switcher": {
        "requests": {
            "endpoint": "/v1/chat/completions",
            "streaming": True,
        },
    },
    "qwen3.8-27b-gguf-rx-9070-xt-16-gb-vram/001-2026-11-15-baseline": {
        "requests": {
            "endpoint": "/v1/chat/completions",
            "streaming": "Performance requests streamed",
            "concurrency": 1,
        },
        "thinking": {
            "enabled": False,
            "control": (
                "Per request: reasoning_effort none for performance and functional"
                " requests, reasoning_effort high for the reasoning case"
            ),
        },
        "notes": [
            "Request policy: functional checks run at temperature 0."
            " Output caps: 1,024 for context cases, 2,048 for sustained generation,"
            " 1,536 for reasoning, 512 for vision, 256 for text and conversation.",
            "Software configuration basis: model, context length, request policy,"
            " corpus hash, and runner commit f78d3db were recorded by the baseline run.",
        ],
    },
    "qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram/001-2026-11-14-baseline": {
        "requests": {
            "endpoint": "/v1/chat/completions",
            "streaming": "Performance requests streamed",
            "concurrency": 1,
            "token_counting": "/v1/messages/count_tokens",
        },
        "thinking": {"enabled": False, "control": "reasoning_effort=none for performance requests"},
        "notes": [
            "Request policy: functional checks run at temperature 0."
            " Output caps: 1,024 tokens for the 8K and context cases, 2,048 for"
            " sustained generation, 256 for text and tools, 512 for vision.",
            "Software configuration basis: repository runtime and model locks;"
            " the running image ID and the engine startup log were captured by the"
            " baseline run.",
        ],
    },
    "qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/001-2026-11-14-baseline": {
        "requests": {
            "endpoint": "/v1/chat/completions",
            "streaming": "Performance requests streamed",
            "concurrency": 1,
            "token_counting": "/v1/messages/count_tokens",
        },
        "thinking": {"enabled": False, "control": "reasoning_effort=none for performance requests"},
        "notes": [
            "Request policy: functional checks run at temperature 0."
            " Output caps: 1,024 tokens for the 8K and context cases, 2,048 for"
            " sustained generation, 256 for text and tools, 512 for vision.",
            "Software configuration basis: repository runtime and model locks;"
            " the running image ID and the engine startup log were captured by the"
            " baseline run.",
        ],
    },
}
# Coding-session profiles record per-request client behaviour in one nested map.
CODING_REQUESTS_MAP: dict[str, tuple[str, str]] = {
    "Thinking": ("thinking", "enabled"),
    "Pi effort": ("thinking", "control"),
    "Output allowance": ("requests", "max_output_tokens"),
    "Reasoning allowance": ("thinking", "budget"),
}
INTEGER_RE = re.compile(r"\A\d+\Z")
FLOAT_RE = re.compile(r"\A\d+\.\d+\Z")


def scalarize(value: object, *, allow_booleans: bool = True) -> object:
    if isinstance(value, str):
        if INTEGER_RE.match(value):
            return int(value)
        if FLOAT_RE.match(value):
            return float(value)
        if allow_booleans:
            if value in {"On", "true", "True"}:
                return True
            if value in {"Off", "false", "False"}:
                return False
    return value


def performance_sampling(experiment: Path) -> dict[str, object]:
    results = experiment / "results.json"
    if not results.is_file():
        return {}
    policy = yaml.safe_load(results.read_text()).get("policy") or {}
    performance = policy.get("performance") or {}
    return {key: value for key, value in performance.items() if key in set(SAMPLING_MAP.values())}


def migrate_settings(
    settings: dict[str, object], experiment: Path
) -> tuple[dict[str, dict[str, object]], list[str]]:
    groups: dict[str, dict[str, object]] = {
        "serving": {},
        "sampling": {},
        "thinking": {},
        "requests": {},
    }
    problems: list[str] = []
    for key, value in settings.items():
        if value is None or value == {} or value == []:
            continue
        for group_map, group in (
            (SERVING_MAP, "serving"),
            (SAMPLING_MAP, "sampling"),
            (THINKING_MAP, "thinking"),
            (REQUESTS_MAP, "requests"),
        ):
            if key in group_map:
                groups[group][group_map[key]] = scalarize(value, allow_booleans=group != "requests")
                break
        else:
            if key in DROPPED_WHEN_EMPTY and str(value).strip().isdigit():
                continue
            if key in ("Request policy", "Configuration notes"):
                continue  # preserved through EXPERIMENT_EDITS notes / Configuration notes
            elif key == "Server sampling" and isinstance(value, dict):
                for subkey, subvalue in value.items():
                    if subkey not in SAMPLING_MAP:
                        problems.append(f"unmapped Server sampling key {subkey!r}")
                        continue
                    groups["sampling"][SAMPLING_MAP[subkey]] = scalarize(subvalue)
            elif key == "Coding requests" and isinstance(value, dict):
                for subkey, subvalue in value.items():
                    if subkey == "Thinking":
                        groups["thinking"]["enabled"] = subvalue == "enabled"
                        continue
                    target = CODING_REQUESTS_MAP.get(subkey)
                    if target is None:
                        problems.append(f"unmapped Coding requests key {subkey!r}")
                        continue
                    group, newkey = target
                    if newkey == "control":
                        groups[group][newkey] = f"Pi reasoning effort: {subvalue}"
                        continue
                    groups[group][newkey] = scalarize(subvalue)
            else:
                problems.append(f"unmapped settings key {key!r}")
    for key, value in performance_sampling(experiment).items():
        groups["sampling"][key] = value
    return groups, problems


def migrate(profile: Path) -> bool:
    data = yaml.safe_load(profile.read_text())
    settings = data.get("settings")
    if not isinstance(settings, dict) or set(settings) <= {
        "serving",
        "sampling",
        "thinking",
        "requests",
        "notes",
    }:
        return False  # already v2 or nothing to do
    experiment = profile.parent
    key = f"{experiment.parent.name}/{experiment.name}"
    groups, problems = migrate_settings(settings, experiment)
    edits = EXPERIMENT_EDITS.get(key, {})
    for group in ("serving", "sampling", "thinking", "requests"):
        groups[group].update(edits.get(group, {}))
    note_sentences: list[str] = []
    configuration_notes = settings.get("Configuration notes")
    if isinstance(configuration_notes, str) and configuration_notes.strip():
        note_sentences.append(configuration_notes.strip())
    note_sentences.extend(edits.get("notes", []))
    if data.get("software", {}).pop("configuration_basis", None) is not None:
        if not any("Software configuration basis" in sentence for sentence in note_sentences):
            problems.append(
                "software.configuration_basis was dropped but EXPERIMENT_EDITS"
                " carries no replacement note"
            )
    settings_groups: dict[str, object] = {
        group: values for group, values in groups.items() if values
    }
    if note_sentences:
        settings_groups["notes"] = " ".join(note_sentences)
    rebuilt: dict[str, object] = {
        key_name: data[key_name] for key_name in ("id", "title") if key_name in data
    }
    for key_name in ("hardware", "os", "software", "model"):
        if key_name in data:
            rebuilt[key_name] = data[key_name]
    rebuilt["settings"] = settings_groups
    if problems:
        raise ValueError(f"{profile}: {'; '.join(problems)}")
    profile.write_text(yaml.safe_dump(rebuilt, allow_unicode=True, sort_keys=False, width=88))
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    migrated = 0
    for profile in sorted((ROOT / "recipes").glob("*/*/profile.yaml")):
        if migrate(profile):
            migrated += 1
            print(f"Migrated: {profile.relative_to(ROOT)}")
    print(f"{migrated} profile(s) migrated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
