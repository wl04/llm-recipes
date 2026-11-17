#!/usr/bin/env python3
"""Render configuration guides, baseline and session reports, and recipe experiment indexes."""

import argparse
import html
import json
import os
import re
import sys
from collections.abc import Generator, Mapping
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

import yaml
from baseline import report, schema

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- BEGIN GENERATED CONFIGURATIONS -->"
END = "<!-- END GENERATED CONFIGURATIONS -->"
INDEX_START = "<!-- BEGIN GENERATED EXPERIMENTS -->"
INDEX_END = "<!-- END GENERATED EXPERIMENTS -->"
RESULTS_START = "<!-- BEGIN GENERATED RESULTS -->"
RESULTS_END = "<!-- END GENERATED RESULTS -->"
FOLDER_NAME = re.compile(r"(\d{3})-(\d{4}-\d{2}-\d{2})-(.+)")

SETTINGS_GROUPS = ("serving", "sampling", "thinking", "requests", "notes")
GROUP_TITLES = {
    "serving": "Serving",
    "sampling": "Sampling",
    "thinking": "Thinking",
    "requests": "Requests",
    "notes": "Experiment notes",
}
SAMPLING_KEYS = (
    "mode",
    "temperature",
    "top_k",
    "top_p",
    "min_p",
    "repetition_penalty",
    "presence_penalty",
    "seed",
)
THINKING_KEYS = ("enabled", "control", "budget")
REQUESTS_KEYS = (
    "endpoint",
    "streaming",
    "max_output_tokens",
    "concurrency",
    "token_counting",
    "forced_tool_call",
)
SERVING_KEYS = (
    "served_model_id",
    "speculative_decoding",
    "context_length_tokens",
    "cache_capacity",
    "target_cache",
    "draft_cache",
    "chunk_size",
    "max_batch_size",
    "parallel_predictions",
    "auto_hardware_optimization",
    "gpu_offload",
    "cpu_thread_pool",
    "eval_batch_size",
    "physical_batch_size",
    "flash_attention",
    "kv_cache_quantization",
    "kv_gpu_offload_unified",
    "ctx_checkpoints",
    "memory_map",
    "draft_token_limits",
    "context_overflow",
    "on_demand_tensor_loading",
    "kv_cache",
    "gpu_resident_kv_cells",
    "expert_cache",
    "prefill",
    "max_draft_tokens",
    "min_draft_probability",
    "draft_vocabulary",
    "vision",
    "vision_offload",
    "vision_min_image_tokens",
    "vision_max_image_tokens",
    "expert_pool",
    "conversation_cache",
    "hyper_connection_projections",
    "route_tail_skip",
    "tensor_parallel",
    "gpu_selection",
    "recurrent_state",
    "sysmem_recurrent_cache_mib",
)
SNAKE_CASE = re.compile(r"[a-z][a-z0-9_]*\Z")

# Display labels for every canonical dotted profile path. Profiles may override
# a path with their own optional ``labels`` mapping; engine-specific serving
# keys not listed here fall back to a derived Title Case label.
LABELS: dict[str, str] = {
    "hardware": "Hardware",
    "hardware.gpu": "GPU",
    "hardware.cpu": "CPU",
    "hardware.memory": "Memory",
    "hardware.memory.architecture": "Memory architecture",
    "hardware.memory.dedicated_vram_gib": "Dedicated VRAM (GiB)",
    "hardware.memory.system_ram_gib": "System RAM (GiB)",
    "hardware.memory.unified_memory_gib": "Unified memory (GiB)",
    "hardware.memory.speed_mt_s": "RAM speed (MT/s)",
    "os": "Operating system",
    "os.name": "Operating system",
    "os.version": "OS version",
    "os.kernel": "Kernel version",
    "os.kernel_driver": "Kernel driver",
    "software": "Software",
    "software.harness": "Agent / harness",
    "software.harness_version": "Harness version",
    "software.server": "API server",
    "software.api_server": "API server",
    "software.server_version": "API server version / revision",
    "software.engine": "Inference engine",
    "software.engine_version": "Engine version",
    "software.engine_version_note": "Engine version notes",
    "software.revision": "Engine source revision",
    "software.backend": "Compute backend",
    "software.backend_api_version": "Backend API version",
    "software.gpu_driver": "GPU driver",
    "software.gpu_driver_version": "GPU driver version",
    "software.pytorch": "PyTorch",
    "software.python": "Python",
    "software.host_python": "Host Python",
    "software.docker": "Docker",
    "software.base_image_tag": "Base image tag at preparation",
    "software.rocm_image_release": "Base image tag at preparation",
    "software.base_image": "Pinned base image",
    "software.running_image_id": "Running image ID",
    "software.vision_engine": "Vision engine",
    "software.vision_version": "Vision engine release",
    "software.vision_revision": "Vision revision",
    "model": "Model",
    "model.name": "Model name",
    "model.format": "Model format",
    "model.quantization": "Weight quantization",
    "model.repository": "Model repository",
    "model.revision": "Model revision",
    "model.artifacts": "Model files",
    "model.draft_repository": "Draft repository",
    "model.draft_revision": "Draft revision",
    "model.draft_quantization": "Draft quantization",
    "model.draft_size": "Converted draft weight size",
    "model.vision_projector": "Vision projector",
    "model.preparation": "Model preparation",
    "serving.served_model_id": "Served model id",
    "serving.speculative_decoding": "Speculative decoding",
    "serving.context_length_tokens": "Context length (tokens)",
    "serving.cache_capacity": "Cache capacity",
    "serving.target_cache": "Target cache",
    "serving.draft_cache": "Draft cache",
    "serving.chunk_size": "Chunk size",
    "serving.max_batch_size": "Maximum batch size",
    "serving.parallel_predictions": "Concurrent predictions",
    "serving.auto_hardware_optimization": "Automatic hardware optimization",
    "serving.gpu_offload": "GPU offload",
    "serving.cpu_thread_pool": "CPU thread pool",
    "serving.eval_batch_size": "Evaluation batch size",
    "serving.physical_batch_size": "Physical batch size",
    "serving.flash_attention": "Flash Attention",
    "serving.kv_cache_quantization": "K / V cache quantization",
    "serving.kv_gpu_offload_unified": "KV cache GPU offload / Unified KV cache",
    "serving.ctx_checkpoints": "Context checkpoints",
    "serving.memory_map": "Keep model in memory / mmap",
    "serving.draft_token_limits": "Max / min draft tokens / draft probability",
    "serving.context_overflow": "Context overflow",
    "serving.on_demand_tensor_loading": "On-demand tensor loading",
    "serving.kv_cache": "KV cache",
    "serving.gpu_resident_kv_cells": "GPU resident KV cells",
    "serving.expert_cache": "Expert cache",
    "serving.prefill": "Prefill",
    "serving.max_draft_tokens": "Maximum draft tokens",
    "serving.min_draft_probability": "Minimum draft probability",
    "serving.draft_vocabulary": "Draft vocabulary",
    "serving.vision": "Vision",
    "serving.vision_offload": "Vision weight offload to system RAM",
    "serving.vision_min_image_tokens": "Minimum image tokens",
    "serving.vision_max_image_tokens": "Maximum image tokens",
    "serving.expert_pool": "Expert pool",
    "serving.conversation_cache": "Conversation cache",
    "serving.hyper_connection_projections": "Hyper connection projections",
    "serving.route_tail_skip": "Route tail skip",
    "serving.tensor_parallel": "Tensor parallel",
    "serving.gpu_selection": "GPU selection",
    "serving.recurrent_state": "Recurrent state",
    "serving.sysmem_recurrent_cache_mib": "System recurrent cache budget (MB)",
    "sampling.mode": "Mode",
    "sampling.temperature": "Temperature",
    "sampling.top_k": "Top K",
    "sampling.top_p": "Top P",
    "sampling.min_p": "Min P",
    "sampling.repetition_penalty": "Repetition penalty",
    "sampling.presence_penalty": "Presence penalty",
    "sampling.seed": "Seed",
    "thinking.enabled": "Thinking enabled",
    "thinking.control": "Thinking control",
    "thinking.budget": "Reasoning budget",
    "requests.workload_suite": "Workload suite",
    "requests.endpoint": "Request endpoint",
    "requests.streaming": "Streaming",
    "requests.max_output_tokens": "Maximum output tokens",
    "requests.concurrency": "Concurrency",
    "requests.token_counting": "Token counting",
    "requests.forced_tool_call": "Forced tool call",
}


def cell(value: object) -> str:
    if value is None:
        return "—"
    return html.escape(str(value)).replace("|", "&#124;").replace("\n", "<br>")


def value_cell(value: object) -> str:
    """Render URL values as links, abbreviating commit IDs only in display text."""
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        url = urlsplit(value)
        if url.netloc and not any(char.isspace() for char in value):
            commit = re.search(r"/commit/([0-9a-fA-F]{7,40})$", url.path)
            label = commit.group(1)[:8] if commit else value
            release = re.fullmatch(r"/[^/]+/[^/]+/releases/tag/(.+)", url.path)
            image = re.fullmatch(r"/r/([^/]+/[^/]+)/tags", url.path)
            if url.hostname == "github.com" and release:
                label = unquote(release.group(1))
            elif url.hostname == "hub.docker.com" and image:
                tags = parse_qs(url.query).get("name", [])
                if len(tags) == 1 and re.fullmatch(r"[\w][\w.-]{0,127}", tags[0]):
                    label = f"{image.group(1)}:{tags[0]}"
            target = quote(value, safe=":/?#@!$&'*+,;=%~.-_")
            text = cell(label).replace("[", "&#91;").replace("]", "&#93;")
            return f"[{text}]({target})"
    return cell(value)


def empty(value: object) -> bool:
    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    if isinstance(value, (dict, list)):
        items = value.values() if isinstance(value, dict) else value
        return all(empty(item) for item in items)
    return False


def rows(
    data: Mapping[str, object], labels: Mapping[str, object], prefix: str = ""
) -> Generator[str]:
    for key, value in data.items():
        if empty(value):
            continue
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            yield from rows(value, labels, path)
            continue
        label = labels.get(path)
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"Missing display label for {path}")
        if isinstance(value, list):
            yield (
                f"| {cell(label)} | "
                + "<br>".join(value_cell(item) for item in value if not empty(item))
                + " |"
            )
        else:
            yield f"| {cell(label)} | {value_cell(value)} |"


def profile_identity(data: Mapping[str, object]) -> tuple[str, str]:
    caption = data.get("id")
    if not isinstance(caption, str):
        raise ValueError("Profile id must be Model / Format / Hardware / Memory")
    parts = caption.split(" / ")
    if len(parts) != 4 or any(not part.strip() for part in parts):
        raise ValueError(
            "Profile id must have four nonempty parts: Model / Format / Hardware / Memory"
        )
    slug = "-".join(re.sub(r"[^a-z0-9.-]+", "-", part.lower()).strip("-") for part in parts)
    return caption, slug


def display_label(path: str, overrides: Mapping[str, object]) -> str:
    override = overrides.get(path)
    if isinstance(override, str) and override.strip():
        return override
    known = LABELS.get(path)
    if known is not None:
        return known
    leaf = path.rsplit(".", 1)[-1]
    return " ".join(word.capitalize() for word in leaf.split("_"))


def label_map(
    data: Mapping[str, object], overrides: Mapping[str, object], prefix: str = ""
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            mapping.update(label_map(value, overrides, path))
        else:
            mapping[path] = display_label(path, overrides)
    return mapping


def validate_settings(settings: object, profile: Path) -> None:
    if settings is None:
        return
    if not isinstance(settings, dict):
        raise ValueError(f"{profile}: settings must be a mapping of {', '.join(SETTINGS_GROUPS)}")
    for key in settings:
        if key not in SETTINGS_GROUPS:
            raise ValueError(
                f"{profile}: settings group {key!r} is not allowed;"
                f" expected only {', '.join(SETTINGS_GROUPS)}"
            )
    for group, allowed in (
        ("serving", None),
        ("sampling", SAMPLING_KEYS),
        ("thinking", THINKING_KEYS),
        ("requests", REQUESTS_KEYS),
    ):
        value = settings.get(group)
        if value is None:
            continue
        if not isinstance(value, dict):
            raise ValueError(f"{profile}: settings.{group} must be a mapping")
        for key in value:
            if isinstance(value[key], dict):
                raise ValueError(f"{profile}: settings.{group}.{key} must not nest")
            if allowed is None:
                if not SNAKE_CASE.match(str(key)):
                    raise ValueError(f"{profile}: settings.serving.{key} must be snake_case")
            elif key not in allowed:
                raise ValueError(
                    f"{profile}: unknown key {key!r} in settings.{group};"
                    f" expected only {', '.join(allowed)}"
                )
    notes = settings.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise ValueError(f"{profile}: settings.notes must be a single string")


def suite_version(result: Path) -> str | None:
    path = result / "results.json"
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: not valid JSON") from error
    value = document.get("suite_version") if isinstance(document, dict) else None
    return str(value) if value is not None else None


def _as_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None


def warn_duplicate_sampling(result: Path, sampling: object) -> None:
    if not isinstance(sampling, dict):
        return
    path = result / "results.json"
    if not path.is_file():
        return
    try:
        document = json.loads(path.read_text())
    except json.JSONDecodeError:
        return
    policy = document.get("policy") if isinstance(document, dict) else None
    performance = policy.get("performance") if isinstance(policy, dict) else None
    if not isinstance(performance, dict):
        return
    duplicated = [
        key
        for key in SAMPLING_KEYS
        if key in sampling
        and _as_number(sampling[key]) is not None
        and _as_number(sampling[key]) == _as_number(performance.get(key))
    ]
    if len(duplicated) >= 3:
        try:
            location = str(result.relative_to(ROOT))
        except ValueError:
            location = str(result)
        print(
            f"Warning: {location}: sampling keys "
            f"{', '.join(duplicated)} duplicate policy.performance from results.json;"
            " prefer run_baseline.py import",
            file=sys.stderr,
        )


def ordered_present(
    values: Mapping[str, object], keys: tuple[str, ...], append_unknown: bool = False
) -> dict[str, object]:
    present = {key: values[key] for key in keys if key in values and not empty(values[key])}
    if append_unknown:
        present.update(
            {
                key: values[key]
                for key in sorted(values)
                if key not in keys and not empty(values[key])
            }
        )
    return present


def canonical_number(value: object) -> object:
    """Render 1.0 as 1 so the same value never drifts between int and float notation."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def group_table(
    title: str,
    prefix: str,
    values: Mapping[str, object],
    overrides: Mapping[str, object],
) -> list[str]:
    if not values:
        return []
    normalized = {key: canonical_number(value) for key, value in values.items()}
    labels = {str(key): display_label(f"{prefix}.{key}", overrides) for key in normalized}
    body = list(rows(normalized, labels))
    if not body:
        return []
    return ["", f"## {cell(title)}", "", "| Setting | Value |", "|---|---|", *body, ""]


def render_settings(
    settings: Mapping[str, object],
    suite: str | None,
    overrides: Mapping[str, object],
    sampling_fallback: Mapping[str, object] | None = None,
) -> list[str]:
    lines: list[str] = []
    serving = settings.get("serving")
    if isinstance(serving, dict):
        lines += group_table(
            GROUP_TITLES["serving"],
            "serving",
            ordered_present(serving, SERVING_KEYS, append_unknown=True),
            overrides,
        )
    for group, keys in (("sampling", SAMPLING_KEYS), ("thinking", THINKING_KEYS)):
        values = settings.get(group)
        if group == "sampling" and (not isinstance(values, dict) or not values):
            values = dict(sampling_fallback) if sampling_fallback else None
        if isinstance(values, dict):
            lines += group_table(
                GROUP_TITLES[group], group, ordered_present(values, keys), overrides
            )
    request_values: dict[str, object] = {}
    if suite is not None:
        request_values["workload_suite"] = suite
    requests = settings.get("requests")
    if isinstance(requests, dict):
        request_values.update(ordered_present(requests, REQUESTS_KEYS))
    lines += group_table(GROUP_TITLES["requests"], "requests", request_values, overrides)
    notes = settings.get("notes")
    if isinstance(notes, str) and notes.strip():
        lines += ["", f"## {GROUP_TITLES['notes']}", "", notes.strip(), ""]
    return lines


def results_policy_sampling(result: Path) -> dict[str, object] | None:
    """``policy.performance`` from a colocated ``results.json``, filtered to sampling keys.

    Baseline experiments keep sampling in ``results.json`` alone; the profile repeats it
    only when it differs from what the run measured.
    """
    path = result / "results.json"
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    policy = document.get("policy") if isinstance(document, dict) else None
    performance = policy.get("performance") if isinstance(policy, dict) else None
    if not isinstance(performance, dict):
        return None
    sampled = {key: value for key, value in performance.items() if key in SAMPLING_KEYS}
    return sampled or None


def render(result: Path) -> str:
    profile = result / "profile.yaml"
    data = yaml.safe_load(profile.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{profile}: expected a YAML mapping")
    caption, slug = profile_identity(data)
    if result.parent.name != slug:
        raise ValueError(f"{profile}: recipe folder must be {slug}")
    settings = data.get("settings")
    validate_settings(settings, profile)
    if isinstance(settings, dict):
        warn_duplicate_sampling(result, settings.get("sampling"))
    overrides = data.get("labels")
    if not isinstance(overrides, dict):
        overrides = {}
    suite = suite_version(result)
    lines = [f"# {cell(caption)}", ""]
    for key, value in data.items():
        if key in {"labels", "id", "title"} or empty(value):
            continue
        if key == "settings":
            continue
        if isinstance(value, dict):
            title = display_label(str(key), overrides)
            lines += ["", f"## {cell(title)}", ""]
            section_rows = list(rows(value, label_map(value, overrides, str(key)), str(key)))
        else:
            section_rows = list(rows({key: value}, label_map({key: value}, overrides)))
        if section_rows:
            lines += ["", "| Setting | Value |", "|---|---|", *section_rows, ""]
    settings_map = settings if isinstance(settings, dict) else {}
    if settings_map or suite is not None:
        fallback = results_policy_sampling(result)
        lines += render_settings(settings_map, suite, overrides, fallback)
    links = ["[Recipe](../recipe.md)", "[Results](summary.md)"]
    if (result.parent / "setup.md").is_file():
        links.append("[Build and run](../setup.md)")
    links.append("[Profile YAML](profile.yaml)")
    if (result / "results.json").is_file():
        links.append("[Results data](results.json)")
    lines += ["---", "", " · ".join(links), ""]
    return "\n".join(lines).rstrip() + "\n"


def write_atomic(path: Path, content: str) -> None:
    """Write content through a temporary file, then atomically replace the document.

    A crash before the rename leaves the previous document intact; a leftover
    temporary file from an interrupted run is cleaned up on the next attempt.
    """
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def update(result: Path) -> tuple[Path, str, str]:
    path = result / "configuration.md"
    original = path.read_text()
    if original.count(START) != 1 or original.count(END) != 1:
        raise ValueError(f"{path}: expected exactly one pair of generated-section markers")
    before, rest = original.split(START)
    _, after = rest.split(END)
    return path, original, before + START + "\n\n" + render(result) + "\n" + END + after


def expected_title(result: Path, data: Mapping[str, object]) -> str:
    """Generated title: folder number and date, plus the profile ``title`` or the description."""
    match = FOLDER_NAME.fullmatch(result.name)
    if match is None:
        raise ValueError(f"{result}: expected a NNN-YYYY-MM-DD-description folder name")
    number, date, description = match.groups()
    custom = data.get("title")
    if isinstance(custom, str) and custom.strip():
        label = " ".join(custom.split())
    else:
        label = description.replace("-", " ").capitalize()
    return f"# {number} · {date} — {label}"


def _render_results_block(result: Path, text: str) -> str:
    """Replace the marked block with the rendering of the experiment's ``results.json``."""
    data_path = result / "results.json"
    try:
        document = json.loads(data_path.read_text())
    except json.JSONDecodeError as error:
        raise ValueError(f"{data_path}: not valid JSON") from error
    try:
        block = report.render_results_block(document)
    except ValueError as error:
        raise ValueError(f"{data_path}: {error}") from error
    path = result / "summary.md"
    if text.count(RESULTS_START) != 1 or text.count(RESULTS_END) != 1:
        raise ValueError(f"{path}: expected exactly one pair of results markers")
    before, middle = text.split(RESULTS_START)
    _, after = middle.split(RESULTS_END)
    return before + RESULTS_START + "\n\n" + block + "\n" + RESULTS_END + after


def update_results_block(result: Path) -> tuple[Path, str, str]:
    """Refresh the results block of a run directory, which has no profile or generated title."""
    path = result / "summary.md"
    original = path.read_text()
    return path, original, _render_results_block(result, original)


def _render_session_block(result: Path, text: str) -> str:
    data_path = result / "session-results.json"
    try:
        document = json.loads(data_path.read_text())
        schema.validate_session(document)
    except ValueError as error:
        raise ValueError(f"{data_path}: {error}") from error
    return report.replace_session_block(
        text, report.render_session(document), result / "summary.md"
    )


def update_summary(result: Path) -> tuple[Path, str, str]:
    """Generate the summary title and the marked baseline or session report."""
    profile = result / "profile.yaml"
    data = yaml.safe_load(profile.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{profile}: expected a YAML mapping")
    path = result / "summary.md"
    original = path.read_text()
    first, separator, rest = original.partition("\n")
    if not first.startswith("# "):
        raise ValueError(f"{path}: the first line must be the report title")
    title = expected_title(result, data)
    text = original if first == title else title + separator + rest
    baseline = (result / "results.json").is_file()
    session = (result / "session-results.json").is_file()
    if baseline and session:
        raise ValueError(f"{result}: cannot contain both results.json and session-results.json")
    if baseline:
        text = _render_results_block(result, text)
    elif session:
        text = _render_session_block(result, text)
    return path, original, text


def update_index(
    recipe: Path, summaries: Mapping[Path, str] | None = None, *, additional: Path | None = None
) -> tuple[Path, str, str]:
    """Rebuild the experiment table; ``summaries`` holds not-yet-written summary texts."""
    path = recipe / "recipe.md"
    original = path.read_text()
    if original.count(INDEX_START) != 1 or original.count(INDEX_END) != 1:
        raise ValueError(f"{path}: expected exactly one pair of experiment markers")
    lines = ["## Experiments", "", "| Experiment | Configuration | Results |", "|---|---|---|"]
    profiles = list(recipe.glob("*/profile.yaml"))
    if additional is not None:
        profiles.append(additional / "profile.yaml")
    for profile in sorted(profiles, key=lambda p: p.parent.name, reverse=True):
        result = profile.parent
        summary = result / "summary.md"
        text = (summaries or {}).get(summary)
        if text is None:
            text = summary.read_text()
        titles = [line[2:].strip() for line in text.splitlines() if line.startswith("# ")]
        if len(titles) != 1:
            raise ValueError(f"{summary}: expected one report title")
        if not (result / "configuration.md").is_file():
            raise ValueError(f"{result}: missing configuration.md")
        lines.append(
            f"| {cell(titles[0])} | "
            f"[Configuration]({result.name}/configuration.md) | "
            f"[Results]({result.name}/summary.md) |"
        )
    before, rest = original.split(INDEX_START)
    _, after = rest.split(INDEX_END)
    return (
        path,
        original,
        before + INDEX_START + "\n\n" + "\n".join(lines) + "\n\n" + INDEX_END + after,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Fail if generated content is stale; write nothing"
    )
    args = parser.parse_args()
    try:
        profiles = sorted((ROOT / "recipes").glob("*/*/profile.yaml"))
        changes = [update(p.parent) for p in profiles]
        changes += [update_summary(p.parent) for p in profiles]
        summaries = {path: new for path, _, new in changes if path.name == "summary.md"}
        changes += [
            update_index(recipe, summaries)
            for recipe in sorted({p.parent.parent for p in profiles})
        ]
    except (ValueError, OSError, yaml.YAMLError) as exc:
        print(exc, file=sys.stderr)
        return 2
    stale = False
    for path, old, new in changes:
        if old != new:
            stale = True
            if args.check:
                print(f"Stale: {path.relative_to(ROOT)}")
            else:
                write_atomic(path, new)
                print(f"Updated: {path.relative_to(ROOT)}")
    return int(args.check and stale)


if __name__ == "__main__":
    sys.exit(main())
