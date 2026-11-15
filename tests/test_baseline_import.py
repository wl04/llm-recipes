"""Tests for importing a completed baseline run as a repository experiment."""

import json
import shutil
from pathlib import Path
from typing import Any

import generate_configurations as gen
import pytest
import yaml
from baseline import importer

ROOT = Path(__file__).resolve().parents[1]
RECIPE = "qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram"
POLICY = {
    "temperature": 1.0,
    "top_k": 20,
    "top_p": 0.95,
    "min_p": 0.0,
    "repetition_penalty": 1.0,
    "presence_penalty": 0.0,
}
SYSTEM = {
    "hostname": "ubuntu-ws",
    "os": {"name": "Ubuntu", "version": "26.10"},
    "kernel": "7.3.0-10-generic",
    "cpu": {"model": "AMD Ryzen 7 9800X3D 8-Core Processor", "cores": 16},
    "memory": {"total_gib": 59.24},
    "gpu": {
        "driver": "amdgpu",
        "model": "Navi 48 [Radeon RX 9070/9070 XT/9070 GRE] (rev cf)",
        "pci_vendor": "0x1002",
        "pci_device": "0x7550",
        "vram_total_gib": 15.92,
        "vram_used_gib": 0.5,
        "gfx_arch": "gfx1201",
    },
}
FACTS: dict[str, Any] = {
    "schema_version": 1,
    "started_at": "2026-11-15T18:18:00+00:00",
    "runtime": "exllamav3-tabbyapi",
    "adapter": "tabbyapi",
    "options": {"port": 8080, "context": 65536, "draft": "on", "vision": "cpu"},
    "config_hashes": {},
    "image": {
        "reference": "llm-recipes/exl3-rdna4:probe",
        "image_id": "sha256:aaa",
        "base_digest": "sha256:ddd",
    },
    "host": SYSTEM,
}


def _results() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "suite_version": "1.5.0",
        "recipe": RECIPE,
        "run": {
            "id": "2026-11-15-1818",
            "started_at": "2026-11-15T18:18:00+00:00",
            "status": "complete",
        },
        "policy": {
            "suite": {"seed": 1, "cache": "Off", "max_output_tokens": "Off"},
            "performance": POLICY,
            "thinking": "disabled",
            "thinking_request": {"chat_template_kwargs": {"enable_thinking": False}},
            "request_extra": {"chat_template_kwargs": {"enable_thinking": False}},
            "sources": {"thinking": "Recipe config"},
        },
        "server": {
            "kind": "tabbyapi",
            "model": "qwen3.8-27b-exl3",
            "context_tokens": 65536,
            "startup_seconds": 30.0,
        },
        "functional": [],
        "phases": [{"id": "functional", "status": "skipped", "metrics": {}}],
        "cases": [{"id": "p", "status": "ok", "runs": 1, "metrics": {}}],
        "boot": {
            "ready_after_seconds": 10.0,
            "ready_attempts": 3,
            "checks": [
                {"path": "/v1/models", "status": 200, "latency_ms": 5.0},
                {"path": "/v1/models", "status": 200, "latency_ms": 5.0},
                {"path": "/v1/chat/completions", "status": 200, "latency_ms": 5.0},
                {"path": "/v1/token/encode", "status": 404, "latency_ms": 1.0},
            ],
        },
    }


def _meta(**overrides: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "schema_version": 1,
        "suite_version": "1.5.0",
        "recipe": RECIPE,
        "run": {"id": "2026-11-15-1818", "status": "complete"},
        "server": {"kind": "tabbyapi"},
        "policy": {"performance": POLICY},
        "host": {
            "hostname": "ubuntu-ws",
            "python": "3.12.13",
            "revision": {"commit": "abc123def", "branch": "main", "dirty": False},
            "system": SYSTEM,
        },
        "launch": {"port": 8080, "context": 65536, "draft": "on", "vision": "cpu"},
        "container": None,
        "launch_facts": FACTS,
    }
    meta.update(overrides)
    return meta


def _make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    config = root / "recipes" / RECIPE / "config"
    config.mkdir(parents=True)
    (config / "launch.json").write_text(
        json.dumps(
            {
                "runtime": "exllamav3-tabbyapi",
                "port": 8080,
                "context": 4096,
                "draft": "off",
                "vision": "off",
            }
        )
    )
    (config / "models.lock.json").write_text(
        json.dumps(
            {
                "target": {
                    "repo_id": "ExaAI/Qwen3.8-27B-EXL3",
                    "revision": "rev1",
                    "files": ["model-00001.safetensors", "index.json"],
                },
                "draft": {"repo_id": "ExaAI/Draft", "revision": "rev2"},
                "conversion": {"arguments": ["--quant", "q8_0"]},
            }
        )
    )
    (config / "pi.models.json").write_text(
        json.dumps({"providers": {"local": {"models": [{"id": "m", "name": "Qwen3.8-27B EXL3"}]}}})
    )
    (config / "tabby.yml").write_text(
        "model:\n  cache_size: 4096\n  cache_mode: q4_0\n  chunk_size: 2048\n"
        "  max_batch_size: 1\n  tensor_parallel: 1\n"
    )
    recipe_index = root / "recipes" / RECIPE / "recipe.md"
    recipe_index.write_text(f"## Experiments\n\n{gen.INDEX_START}\n\n{gen.INDEX_END}\n")
    runtime = root / "runtimes" / "exllamav3-tabbyapi"
    (runtime / "container").mkdir(parents=True)
    (runtime / "runtime.json").write_text(
        json.dumps(
            {"adapter": "tabbyapi", "engine": "exllamav3", "image": "llm-recipes/exl3:probe"}
        )
    )
    (runtime / "container" / "versions.lock.json").write_text(
        json.dumps(
            {
                "base_image": "docker.io/rocm/pytorch:rocm7.10.0_ubuntu24.04_py3.12@sha256:ddd",
                "torch_version": "2.14.0+rocm7.1.0",
                "python_version": "3.12.3",
                "sources": {
                    "exllamav3": {
                        "repository": "https://github.com/exllamav3/exllamav3",
                        "revision": "1111111111111111111111111111111111111111",
                    },
                    "tabbyAPI": {
                        "repository": "https://github.com/aredden/tabbyapi",
                        "revision": "2222222222222222222222222222222222222222",
                    },
                },
            }
        )
    )
    shutil.copytree(ROOT / "templates", root / "templates")
    return root


def _make_run(
    tmp_path: Path, results: dict[str, Any] | None = None, meta: dict[str, Any] | None = None
) -> Path:
    run_dir = tmp_path / "baselines" / RECIPE / "2026-11-15-1818"
    run_dir.mkdir(parents=True)
    (run_dir / "results.json").write_text(json.dumps(results or _results()))
    (run_dir / "meta.json").write_text(json.dumps(meta or _meta()))
    return run_dir


def test_import_creates_a_complete_experiment_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_repo(tmp_path)
    run_dir = _make_run(tmp_path)
    monkeypatch.setattr(
        importer, "_repository_url", lambda _root: "https://github.com/wl04/llm-recipes"
    )

    folder = importer.import_run(run_dir, root)

    assert folder.name == "001-2026-11-15-baseline"
    profile = yaml.safe_load((folder / "profile.yaml").read_text())
    assert profile["id"] == "Qwen3.8-27B / EXL3 / RX 9070 XT / 16 GB VRAM"
    assert profile["hardware"]["memory"]["architecture"] == "discrete"
    assert profile["hardware"]["memory"]["dedicated_vram_gib"] == 16
    assert profile["hardware"]["memory"]["system_ram_gib"] == 59
    assert profile["os"]["version"] == "26.10"
    assert profile["software"]["harness"] == importer.HARNESS
    assert profile["software"]["harness_version"].endswith("/commit/abc123def")
    assert profile["software"]["base_image_tag"].endswith("/tags")
    assert profile["software"]["server_version"].endswith(
        "/commit/2222222222222222222222222222222222222222"
    )
    assert profile["model"]["repository"] == "https://huggingface.co/ExaAI/Qwen3.8-27B-EXL3"
    assert profile["model"]["draft_quantization"] == "--quant q8_0"
    settings = profile["settings"]
    assert settings["sampling"] is None
    assert settings["serving"]["context_length_tokens"] == 65536
    assert settings["serving"]["cache_capacity"] == 4096
    assert settings["serving"]["vision"] == "cpu"
    assert settings["thinking"]["control"] == "chat_template_kwargs.enable_thinking=false"
    assert settings["requests"]["token_counting"] == "/v1/token/encode"
    configuration = (folder / "configuration.md").read_text()
    assert "## Serving" in configuration
    assert "## Sampling" in configuration
    assert (folder / "results.json").is_file()
    summary = (folder / "summary.md").read_text()
    assert summary.startswith("# 001 · 2026-11-15 — Baseline")
    assert "| p | ok | 1 |" in summary
    index = (folder.parent / "recipe.md").read_text()
    assert "| 001 · 2026-11-15 — Baseline |" in index
    assert "(001-2026-11-15-baseline/summary.md)" in index
    assert (root / "recipes" / RECIPE / folder.name / "profile.yaml").is_file()


def test_import_uses_next_free_sequence_number(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    (root / "recipes" / RECIPE / "002-2026-11-02-coding").mkdir()
    run_dir = _make_run(tmp_path)

    folder = importer.import_run(run_dir, root)

    assert folder.name == "003-2026-11-15-baseline"


def test_import_suffix_extends_the_folder_name(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    run_dir = _make_run(tmp_path)

    folder = importer.import_run(run_dir, root, suffix="rerun")

    assert folder.name == "001-2026-11-15-baseline-rerun"


def test_import_rejects_an_invalid_suffix(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    run_dir = _make_run(tmp_path)

    with pytest.raises(ValueError, match="lowercase"):
        importer.import_run(run_dir, root, suffix="Bad Suffix")


def test_import_requires_results_json(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    with pytest.raises(ValueError, match=r"results\.json"):
        importer.import_run(run_dir, root)


def test_import_rejects_an_incomplete_run(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    results = _results()
    results["run"]["status"] = "failed"
    run_dir = _make_run(tmp_path, results=results)

    with pytest.raises(ValueError, match="not complete"):
        importer.import_run(run_dir, root)


def test_import_requires_an_existing_recipe(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    shutil.rmtree(root / "recipes" / RECIPE)
    run_dir = _make_run(tmp_path)

    with pytest.raises(ValueError, match="no folder"):
        importer.import_run(run_dir, root)


def test_import_desktop_run_without_facts_leaves_unobserved_fields_null(
    tmp_path: Path,
) -> None:
    root = _make_repo(tmp_path)
    launch = root / "recipes" / RECIPE / "config" / "launch.json"
    launch.write_text(json.dumps({"runtime": "lmstudio", "port": 1234, "context": 32768}))
    results = _results()
    results["server"]["kind"] = "lmstudio"
    results["server"]["model"] = "qwen3.8-27b"
    meta = _meta(container=None, launch_facts=None, launch=None)
    meta["host"] = {"hostname": "x", "python": "3.13.7", "kernel": "7.0.0"}
    run_dir = _make_run(tmp_path, results=results, meta=meta)

    folder = importer.import_run(run_dir, root)

    profile = yaml.safe_load((folder / "profile.yaml").read_text())
    assert profile["hardware"]["gpu"] is None
    assert profile["software"]["base_image"] is None
    assert profile["software"]["host_python"] == "3.13.7"
    assert profile["os"]["kernel"] == "7.0.0"
    assert profile["settings"]["requests"]["token_counting"] is None
    assert profile["settings"]["serving"]["context_length_tokens"] == 65536
    assert "cache_capacity" not in profile["settings"]["serving"]


def test_experiment_identity_splits_documented_recipe_names() -> None:
    parts = importer.experiment_identity(
        "qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram"
    )

    assert parts == (
        "Qwen3.8-Flash-Next",
        "GGUF Unsloth UD IQ3 XXS",
        "RX 9070 XT",
        "16 GB VRAM",
    )


def test_experiment_identity_rejects_a_name_without_hardware() -> None:
    with pytest.raises(ValueError, match="memory part"):
        importer.experiment_identity("qwen3.8-27b-exl3")
