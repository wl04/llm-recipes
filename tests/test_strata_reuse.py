"""CPU-only Strata candidates using small, structurally valid legacy preparations."""

import hashlib
import json
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import Mock

import pytest
from test_strata import RUNTIME, load_module

OLD_KEY = "v0.2.21"
NEW_KEY = "v0.2.23"
OLD = {"sources": {"strata": {"revision": "d46f5f268f8ed797e83a5c63a69bffbd7a581cf6"}}}
NEW = {"sources": {"strata": {"revision": "4560d03793482ef367294cfbd86a4df8d5679e72"}}}
PACK = Path("packs/iq3_xxs")
MTP = Path("mtp/rt")


@pytest.fixture
def reuse(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = load_module("strata_reuse", RUNTIME / "scripts/reuse_artifacts.py")
    monkeypatch.setattr(module, "Q2_EXPERT_BYTES", len(b"fixture"))
    return module


def save(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def local_file(name: str, payload: bytes) -> dict[str, Any]:
    return {"path": name, "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def write_pack(folder: Path, shards: list[dict[str, Any]], compat: bool) -> None:
    first = shards[0]["path"]
    save(
        folder / "index.txt",
        (
            f"# strata pack index v3 from {first}\n# align 256 pool 256 tensors 1\n"
            "test 0 1 0 7 0 7 1 1 0 0 1 0 0 0 0 0 0 0\n"
        ).encode(),
    )
    save(folder / "native_experts.txt", b"# strata native experts v3:\n0 1 1 0 1 0 2 4\n")
    save(folder / "dense.bin", b"fixture")
    for name in ("vocab.json", "tokenizer.json", "chat_template.jinja"):
        save(folder / "tokenizer" / name, b"{}")
    save(
        folder / "conversions.json",
        json.dumps(
            {
                "source_shards": [
                    {"name": row["path"], "size": row["size_bytes"]} for row in shards
                ],
                "compat_bf16": compat,
            }
        ).encode(),
    )
    if compat:
        save(folder / "compat-bf16.json", b"{}")


def install(root: Path, *, compat: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    files = []
    for i in (1, 2):
        name = f"weights-{i:05}-of-00002.gguf"
        payload = (b"unsloth" if compat else b"ista") + bytes([i])
        save(root / "models" / name, payload)
        files.append(local_file(name, payload))
    donor = root / "prepared" / OLD_KEY
    write_pack(donor / PACK, files, compat)
    for name in ("experts.bin", "dense.bin"):
        save(donor / MTP / name, b"fixture")
    save(donor / MTP / "dense.txt", b"tensor bf16 1 1 0 2\n")
    save(donor / MTP / "draft_vocab.bin", b"test-vocab")
    lock = {
        "repository": "fixture/target",
        "revision": "a" * 40,
        "files": [*files, local_file("bf16.gguf", b"unused")],
        "pack": {"compat_bf16": compat},
        "mtp": {
            "repository": "fixture/mtp",
            "revision": "b" * 40,
            "expert_quantization": "q2_0",
            "draft_vocabulary": "draft_vocab.bin",
        },
    }
    projector = {**local_file("projectors/q8.gguf", b"vision"), "source": "bf16.gguf"}
    save(root.parents[1] / projector["path"], b"vision")
    save(donor / "prepared.json", json.dumps({"models": lock, "image": OLD}).encode())
    return lock, projector


def candidate_tools(data: Path, vocab: bytes = b"test-vocab") -> Path:
    folder = data / "engine/tools"
    for name in (
        "iq_pack.py",
        "strata_tokenizer.py",
        "gguf_reader.py",
        "_paths.py",
        "mtp_pack.py",
        "mtp_rt.py",
    ):
        save(folder / name, name.encode())
    save(folder.parent / "data/draft_vocab.bin", vocab)
    return folder


@pytest.mark.parametrize("rocm_only", [False, True])
def test_upgrade_reuses_distinct_packs_and_shares_mtp_without_sources(
    tmp_path: Path, reuse: ModuleType, rocm_only: bool
) -> None:
    roots = [tmp_path / "recipes" / name for name in ("ista", "unsloth")]
    tools = candidate_tools(tmp_path)
    unexpected = Mock(side_effect=AssertionError("unexpected converter"))
    build = {**OLD, "base_tag": "10.3.0-full"} if rocm_only else NEW

    for root, compat in zip(roots, (False, True), strict=True):
        lock, projector = install(root, compat=compat)
        local = reuse.LocalPreparation(
            root,
            NEW_KEY,
            OLD_KEY,
            lock,
            projector,
            build,
            tools,
            {},
            allow_copy=False,
            verify=False,
        )
        local.prepare(unexpected, unexpected, unexpected)

    a, b = [root / "prepared" / NEW_KEY for root in roots]
    for root, staged in zip(roots, (a, b), strict=True):
        donor = root / "prepared" / OLD_KEY
        assert (staged / PACK / "dense.bin").samefile(donor / PACK / "dense.bin")
        assert not (staged / PACK / "index.txt").samefile(donor / PACK / "index.txt")
        artifacts = json.loads((staged / "artifacts.json").read_text())
        assert artifacts["pack"]["producer"] == OLD
        assert (staged / "prepared.json").is_file()
        assert (donor / PACK / "dense.bin").read_bytes() == b"fixture"
    assert not (a / PACK / "dense.bin").samefile(b / PACK / "dense.bin")
    assert (a / MTP / "experts.bin").samefile(b / MTP / "experts.bin")
    shutil.rmtree(roots[0] / "prepared" / OLD_KEY)
    shutil.rmtree(a)
    assert (b / MTP / "experts.bin").read_bytes() == b"fixture"


@pytest.mark.parametrize("change", ["compat-bf16", "shard"])
def test_upgrade_rebuilds_only_pack_when_target_inputs_change(
    tmp_path: Path, reuse: ModuleType, change: str
) -> None:
    root = tmp_path / "recipes/ista"
    lock, projector = install(root, compat=False)
    tools = candidate_tools(tmp_path)
    if change == "compat-bf16":
        lock["pack"]["compat_bf16"] = True
    else:
        path = lock["files"][1]["path"]
        save(root / "models" / path, b"quantized")
        lock["files"][1] = local_file(path, b"quantized")

    def convert(script: str, output: str) -> None:
        assert script == "iq_pack.py"
        write_pack(Path(output) / PACK, lock["files"][:2], lock["pack"]["compat_bf16"])

    local = reuse.LocalPreparation(
        root, NEW_KEY, OLD_KEY, lock, projector, NEW, tools, {}, allow_copy=False, verify=False
    )
    local.prepare(
        convert, lambda stage: [str(stage)], Mock(side_effect=AssertionError("projector"))
    )

    old = root / "prepared" / OLD_KEY
    new = root / "prepared" / NEW_KEY
    assert not (old / PACK / "dense.bin").samefile(new / PACK / "dense.bin")
    assert (old / MTP / "experts.bin").samefile(new / MTP / "experts.bin")


def test_upgrade_replaces_only_vocabulary_when_its_digest_changes(
    tmp_path: Path, reuse: ModuleType
) -> None:
    root = tmp_path / "recipes/ista"
    lock, projector = install(root, compat=False)
    tools = candidate_tools(tmp_path, b"replacement-vocab")
    unexpected = Mock(side_effect=AssertionError("unexpected converter"))
    local = reuse.LocalPreparation(
        root, NEW_KEY, OLD_KEY, lock, projector, NEW, tools, {}, allow_copy=False, verify=False
    )

    local.prepare(unexpected, unexpected, unexpected)

    old = root / "prepared" / OLD_KEY / MTP
    new = root / "prepared" / NEW_KEY / MTP
    assert (old / "experts.bin").samefile(new / "experts.bin")
    assert (old / "draft_vocab.bin").read_bytes() == b"test-vocab"
    assert (new / "draft_vocab.bin").read_bytes() == b"replacement-vocab"


def test_upgrade_rejects_corrupt_shard_reference_without_completing_candidate(
    tmp_path: Path, reuse: ModuleType
) -> None:
    root = tmp_path / "recipes/ista"
    lock, projector = install(root, compat=False)
    tools = candidate_tools(tmp_path)
    old = root / "prepared" / OLD_KEY / PACK / "native_experts.txt"
    save(old, b"# strata native experts v3:\n0 1 1 0 1 0 2 4 not-locked.gguf\n")
    unexpected = Mock(side_effect=AssertionError("unexpected converter"))
    local = reuse.LocalPreparation(
        root, NEW_KEY, OLD_KEY, lock, projector, NEW, tools, {}, allow_copy=False, verify=False
    )

    with pytest.raises(ValueError, match="Invalid shard reference"):
        local.prepare(unexpected, unexpected, unexpected)

    assert not (root / "prepared" / NEW_KEY).exists()
    save(old, b"# strata native experts v3:\n0 1 1 0 1 0 2 4\n")
    local.prepare(unexpected, unexpected, unexpected)
    assert (root / "prepared" / NEW_KEY / "prepared.json").is_file()
