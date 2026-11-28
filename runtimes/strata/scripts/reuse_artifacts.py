"""Prepare a versioned Strata candidate from local serving artifacts and sources."""

import json
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from model_artifacts import (
    FileRecord,
    artifact_path,
    inventory,
    sha256,
    stage_files,
    staged_preparation,
    verify_inventory,
)
from mtp_source import cache_path, validate

PACK = Path("packs/iq3_xxs")
MTP = Path("mtp/rt")
VOCAB = "draft_vocab.bin"
PACK_FILES = {
    "native_experts.txt",
    "index.txt",
    "dense.bin",
    "conversions.json",
    "tokenizer/chat_template.jinja",
    "tokenizer/vocab.json",
    "tokenizer/tokenizer.json",
}
MTP_FILES = {"experts.bin", "dense.bin", "dense.txt", VOCAB}
Q2_EXPERT_BYTES = 512 * 3 * (2560 * 640 * 18 // 64)
# These releases share the converters, tokenizer helper, GGUF helpers and vocabulary.
LEGACY_EQUIVALENT = {
    "d46f5f268f8ed797e83a5c63a69bffbd7a581cf6",  # v0.2.21
    "4560d03793482ef367294cfbd86a4df8d5679e72",  # v0.2.23
}


def pack_inputs(lock: dict[str, Any], projector: dict[str, Any] | None) -> dict[str, Any]:
    """Keep ordered, published target identities separate from projector and MTP settings."""
    return {
        "shards": [
            {"repository": lock["repository"], "revision": lock["revision"], **item}
            for item in lock["files"]
            if not projector or item["path"] != projector["source"]
        ],
        "options": {"compat_bf16": False, **lock.get("pack", {})},
    }


def mtp_inputs(lock: dict[str, Any]) -> dict[str, Any]:
    return {key: lock["mtp"][key] for key in ("repository", "revision", "expert_quantization")}


def validate_pack(folder: Path, inputs: dict[str, Any]) -> None:
    """Check the standalone GGUF pack tables, their ranges, and their named shards."""
    paths = inputs["shards"]
    shards = {Path(row["path"]).name: row["size_bytes"] for row in paths}
    first = next(name for name in shards if re.search(r"-00001-of-\d{5}\.gguf$", name))
    conversions = read_metadata(folder / "conversions.json")
    if (
        conversions["source_shards"]
        != [{"name": name, "size": size} for name, size in shards.items()]
        or conversions["compat_bf16"] != inputs["options"]["compat_bf16"]
    ):
        raise ValueError(f"Pack conversion inputs differ: {folder / 'conversions.json'}")
    if inputs["options"]["compat_bf16"] and not (folder / "compat-bf16.json").is_file():
        raise ValueError(f"Missing conversion record: {folder / 'compat-bf16.json'}")
    index = folder / "index.txt"
    header, counts, *rows = index.read_text().splitlines()
    if not header.startswith("# strata pack index v3 ") or not header.endswith(f" from {first}"):
        raise ValueError(f"Unsupported pack index: {index}")
    count = re.fullmatch(r"# align \d+ pool \d+ tensors (\d+)", counts)
    if not rows or count is None or int(count[1]) != len(rows):
        raise ValueError(f"Incomplete pack index: {index}")
    dense_size = (folder / "dense.bin").stat().st_size
    for row in rows:
        fields = row.split()
        if len(fields) != 19:
            raise ValueError(f"Invalid tensor row: {index}: {row}")
        offset, length = map(int, fields[3:5])
        if (
            offset < 0
            or length < 0
            or (length and (fields[1] != "0" or offset + length > dense_size))
        ):
            raise ValueError(f"Tensor outside standalone dense data: {index}: {fields[0]}")
    native = folder / "native_experts.txt"
    header, *rows = native.read_text().splitlines()
    if not rows or not re.match(r"# strata native experts v[345]:", header):
        raise ValueError(f"Unsupported native expert index: {native}")
    if "experts v5:" in header and not (folder / "hadamard.txt").is_file():
        raise ValueError(f"Missing Hadamard parameters: {folder / 'hadamard.txt'}")
    for row in rows:
        fields = row.split()
        if len(fields) not in (8, 9):
            raise ValueError(f"Invalid native expert row: {native}: {row}")
        files = fields[8].split(",") if len(fields) == 9 else [first]
        if len(files) == 1:
            files *= 3
        if len(files) != 3 or any(
            not 0 <= int(offset) < shards.get(name or first, 0)
            for name, offset in zip(files, fields[5:8], strict=True)
        ):
            raise ValueError(f"Invalid shard reference or expert offset: {native}: {row}")


def validate_mtp(folder: Path, quantization: str) -> None:
    dense_bytes = (folder / "dense.bin").stat().st_size
    names: set[str] = set()
    index = folder / "dense.txt"
    for line in index.read_text().splitlines():
        name, kind, rows, cols, offset, size = line.split()
        begin, length = int(offset), int(size)
        if (
            name in names
            or kind not in {"q8_0", "bf16", "f32"}
            or min(int(rows), int(cols), length) <= 0
            or begin < 0
            or begin + length > dense_bytes
        ):
            raise ValueError(f"Invalid MTP dense tensor: {index}: {line}")
        names.add(name)
    if not names:
        raise ValueError(f"Empty MTP dense index: {index}")
    experts = folder / "experts.bin"
    if quantization == "q2_0":
        if experts.stat().st_size != Q2_EXPERT_BYTES:
            raise ValueError(f"Incorrect Q2_0 expert data size: {experts}")
    elif not (folder / "experts.txt").is_file():
        raise ValueError(f"Missing native MTP expert layout: {folder / 'experts.txt'}")


def donor_root(root: Path, key: str) -> Path:
    if key == "base":
        return root
    if not re.fullmatch(r"v[0-9][A-Za-z0-9.-]{0,126}", key):
        raise ValueError("Invalid donor preparation key")
    return root / "prepared" / key


def legacy_tools_match(donor: dict[str, Any], build: dict[str, Any]) -> bool:
    old, new = donor["sources"], build["sources"]
    old_rev, new_rev = old["strata"]["revision"], new["strata"]["revision"]
    return old.get("llama_cpp") == new.get("llama_cpp") and (
        old_rev == new_rev or {old_rev, new_rev} <= LEGACY_EQUIVALENT
    )


def read_metadata(path: Path) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot read {path}: {error}") from error
    if not isinstance(result, dict):
        raise ValueError(f"Expected an object in {path}")
    return result


def receipt(folder: Path) -> dict[str, Any] | None:
    path = folder / "prepared.json"
    if folder.resolve() != folder or not path.is_file():
        return None
    artifact_path(folder, path.name)
    return read_metadata(path)


def artifact_receipt(folder: Path) -> dict[str, Any]:
    path = artifact_path(folder, "artifacts.json")
    if not path.exists():
        if "artifact_schema" in (receipt(folder) or {}):
            raise ValueError(f"Missing artifact receipt: {path}")
        return {}
    result: dict[str, Any] = read_metadata(path)
    if result.get("schema") != 1:
        raise ValueError(f"Unsupported artifact receipt: {path}")
    return result


def output_inventory(
    folder: Path, required: set[str], recorded: dict[str, FileRecord] | None, *, verify: bool
) -> dict[str, FileRecord]:
    files = inventory(folder) if recorded is None else recorded
    if missing := required - files.keys():
        raise ValueError(f"Missing serving artifacts in {folder}: {', '.join(sorted(missing))}")
    if recorded is not None:
        verify_inventory(folder, files, verify=verify)
    return files


def locked_inventory(
    folder: Path, specs: dict[str, dict[str, Any]], known: dict[str, FileRecord], *, verify: bool
) -> dict[str, FileRecord]:
    result = {}
    for name, spec in specs.items():
        saved = known.get(name)
        if saved is not None and saved["sha256"] == spec["sha256"]:
            records = {name: saved}
            verify_inventory(folder, records, verify=verify)
        else:
            records = inventory(folder, [name])
        info = records[name]
        if info["size"] != spec["size_bytes"] or info["sha256"] != spec["sha256"]:
            raise ValueError(f"File differs from model lock: {folder / name}")
        result[name] = info
    return result


class LocalPreparation:
    def __init__(
        self,
        root: Path,
        key: str,
        donor: str,
        lock: dict[str, Any],
        projector: dict[str, Any] | None,
        build: dict[str, Any],
        tools: Path,
        tensors: dict[str, str],
        *,
        allow_copy: bool,
        verify: bool,
    ) -> None:
        self.root = root
        self.data = root.parents[1]
        self.final = donor_root(root, key)
        self.donor = donor_root(root, donor)
        self.lock = lock
        self.projector = projector
        self.build = build
        self.tools = tools
        self.tensors = tensors
        self.allow_copy = allow_copy
        self.verify = verify
        self.pack = pack_inputs(lock, projector)
        self.mtp = mtp_inputs(lock)
        self.vocab = artifact_path(tools.parent / "data", lock["mtp"]["draft_vocabulary"])
        self.owner = {"models": lock, "image": build}

    def prepare(
        self,
        run: Callable[..., None],
        pack_args: Callable[[Path], list[str]],
        projector: Callable[[dict[str, Any], Path], None],
    ) -> None:
        existing = receipt(self.final)
        if self.final.exists() and (
            not existing or any(existing.get(name) != value for name, value in self.owner.items())
        ):
            raise ValueError(f"Conflicting preparation at {self.final}")
        known = artifact_receipt(self.final if existing else self.donor)
        shards = locked_inventory(
            self.root / "models",
            {item["path"]: item for item in self.pack["shards"]},
            known.get("shards", {}),
            verify=self.verify,
        )
        if self.projector:
            self.prepare_projector(self.projector, projector, known.get("projector", {}))
        if existing:
            output_inventory(
                self.final / PACK,
                PACK_FILES,
                known.get("pack", {}).get("files"),
                verify=self.verify,
            )
            output_inventory(
                self.final / MTP, MTP_FILES, known.get("mtp", {}).get("files"), verify=self.verify
            )
            validate_pack(self.final / PACK, self.pack)
            validate_mtp(self.final / MTP, self.mtp["expert_quantization"])
            if sha256(self.final / MTP / VOCAB) != sha256(self.vocab):
                raise ValueError(
                    f"MTP vocabulary differs from the candidate: {self.final / MTP / VOCAB}"
                )
            print(
                f"{self.root.name}: target pack and MTP already prepared for {self.final.name}",
                flush=True,
            )
            return
        with staged_preparation(self.final, {**self.owner, "mode": "local"}) as stage:
            artifacts = {
                "schema": 1,
                "shards": shards,
                "projector": self.projector_records,
                "pack": self.prepare_pack(stage, run, pack_args),
                **self.prepare_mtp(stage, run),
            }
            (stage / "artifacts.json").write_text(json.dumps(artifacts, indent=2) + "\n")
            (stage / "prepared.json").write_text(
                json.dumps({**self.owner, "artifact_schema": 1}, indent=2) + "\n"
            )

    projector_records: dict[str, FileRecord] | None = None

    def prepare_projector(
        self,
        spec: dict[str, Any],
        convert: Callable[[dict[str, Any], Path], None],
        known: dict[str, FileRecord] | None,
    ) -> None:
        target = artifact_path(self.data, spec["path"])
        if target.exists():
            reason = "reusing locked projector"
        else:
            source = next(item for item in self.lock["files"] if item["path"] == spec["source"])
            locked_inventory(target.parent, {spec["source"]: source}, {}, verify=True)
            convert(spec, self.data)
            reason = "rebuilt projector from verified local BF16"
        self.projector_records = locked_inventory(
            self.data,
            {spec["path"]: spec},
            known or {},
            verify=self.verify,
        )
        print(f"{self.root.name}: {reason}", flush=True)

    def tool_hashes(self, *files: str) -> dict[str, Any]:
        return {
            "llama_cpp": self.build["sources"].get("llama_cpp"),
            **{name: sha256(self.tools / name) for name in files},
        }

    def prepare_pack(
        self,
        stage: Path,
        run: Callable[..., None],
        pack_args: Callable[[Path], list[str]],
    ) -> dict[str, Any]:
        tools = self.tool_hashes("iq_pack.py", "strata_tokenizer.py", "gguf_reader.py", "_paths.py")
        producer = self.build
        old = receipt(self.donor)
        record = artifact_receipt(self.donor).get("pack") if old else None
        if old and record is None and legacy_tools_match(old["image"], self.build):
            # Legacy receipts excluded the projector but could include its BF16 source.
            previous = pack_inputs(old["models"], self.projector)
            record = {"inputs": previous, "tools": tools, "producer": old["image"]}
        dest = stage / PACK
        if record and record["inputs"] == self.pack and record["tools"] == tools:
            source = self.donor / PACK
            source_files = output_inventory(
                source, PACK_FILES, record.get("files"), verify=self.verify
            )
            validate_pack(source, self.pack)
            files = stage_files(source, dest, source_files, allow_copy=self.allow_copy)
            producer = record["producer"]
            print(f"{self.root.name}: reused target pack from {self.donor}", flush=True)
        else:
            print(
                f"{self.root.name}: rebuilding target pack (no matching inputs and pack format)",
                flush=True,
            )
            run("iq_pack.py", *pack_args(stage))
            files = output_inventory(dest, PACK_FILES, None, verify=False)
            validate_pack(dest, self.pack)
        return {"inputs": self.pack, "tools": tools, "producer": producer, "files": files}

    def mtp_donors(self) -> list[Path]:
        recipes = self.data / "recipes"
        candidates = [*sorted(recipes.glob(f"*/prepared/{self.final.name}/prepared.json"))]
        candidates += [self.donor / "prepared.json"]
        candidates += sorted(recipes.glob("*/prepared/*/prepared.json"))
        candidates += sorted(recipes.glob("*/prepared.json"))
        return list(dict.fromkeys(path.parent for path in candidates if path.parent != self.final))

    def prepare_mtp(self, stage: Path, run: Callable[..., None]) -> dict[str, Any]:
        inputs = {**self.mtp, "tensors": self.tensors}
        pack_tools = self.tool_hashes("mtp_pack.py", "_paths.py")
        tools = {**pack_tools, **self.tool_hashes("mtp_rt.py", "_paths.py")}
        dest = stage / MTP
        vocab_digest = sha256(self.vocab)
        intermediate = None
        for donor in self.mtp_donors():
            old = receipt(donor)
            if not old or "mtp" not in old.get("models", {}):
                continue
            records = artifact_receipt(donor)
            record = records.get("mtp")
            if (
                record is None
                and legacy_tools_match(old["image"], self.build)
                and mtp_inputs(old["models"]) == self.mtp
            ):
                record = {"inputs": inputs, "tools": tools, "producer": old["image"]}
            if record and record["inputs"] == inputs and record["tools"] == tools:
                source = donor / MTP
                source_files = output_inventory(
                    source, MTP_FILES, record.get("files"), verify=self.verify
                )
                validate_mtp(source, self.mtp["expert_quantization"])
                vocab_matches = source_files[VOCAB]["sha256"] == vocab_digest
                if not vocab_matches:
                    del source_files[VOCAB]
                files = stage_files(source, dest, source_files, allow_copy=self.allow_copy)
                if not vocab_matches:
                    shutil.copyfile(self.vocab, dest / VOCAB)
                    files.update(inventory(dest, [VOCAB]))
                print(
                    f"{self.root.name}: reused MTP runtime from {donor}"
                    f"{'' if vocab_matches else ' (updated vocabulary only)'}",
                    flush=True,
                )
                return {"mtp": {**record, "files": files, "vocabulary": vocab_digest}}
            gguf = records.get("mtp_gguf")
            if (
                intermediate is None
                and gguf
                and gguf["inputs"] == inputs
                and gguf["tools"] == pack_tools
            ):
                intermediate = (donor, gguf)
        return self.rebuild_mtp(stage, run, inputs, pack_tools, tools, vocab_digest, intermediate)

    def local_mtp_source(self) -> Path:
        repo, revision = self.mtp["repository"], self.mtp["revision"]
        url = f"https://huggingface.co/{repo}/resolve/{revision}/"
        cached = cache_path(self.data, repo, revision)
        if cached.exists():
            validate(cached, url, self.tensors)
            return cached
        for donor in self.mtp_donors():
            source = donor / "mtp"
            if (source / "mtp-manifest.json").is_file() and source.resolve() == source:
                old = (receipt(donor) or {}).get("models", {}).get("mtp", {})
                if old.get("repository") == repo and old.get("revision") == revision:
                    validate(source, url, self.tensors)
                    return source
        raise ValueError(f"Missing local MTP tensors: {cached}")

    def rebuild_mtp(
        self,
        stage: Path,
        run: Callable[..., None],
        inputs: dict[str, Any],
        pack_tools: dict[str, Any],
        tools: dict[str, Any],
        vocab_digest: str,
        intermediate: tuple[Path, dict[str, Any]] | None,
    ) -> dict[str, Any]:
        quant = self.mtp["expert_quantization"]
        dest = stage / MTP
        folder = dest.parent
        folder.mkdir()
        name = f"mtp-{quant}.gguf"
        if intermediate:
            donor, old = intermediate
            verify_inventory(donor / "mtp", old["files"], verify=self.verify)
            gguf_files = stage_files(
                donor / "mtp", folder, old["files"], allow_copy=self.allow_copy
            )
            producer = old["producer"]
            print(
                f"{self.root.name}: rebuilding MTP runtime from the existing quantized GGUF",
                flush=True,
            )
        else:
            source = self.local_mtp_source()
            print(
                f"{self.root.name}: rebuilding MTP runtime from verified local tensors", flush=True
            )
            run(
                "mtp_pack.py", "--src", str(source), "--experts", quant, "--out", str(folder / name)
            )
            gguf_files = inventory(folder, [name])
            producer = self.build
        run("mtp_rt.py", "--gguf", str(folder / name), "--out", str(dest))
        shutil.copyfile(self.vocab, dest / VOCAB)
        validate_mtp(dest, quant)
        files = output_inventory(dest, MTP_FILES, None, verify=False)
        return {
            "mtp": {
                "inputs": inputs,
                "tools": tools,
                "producer": self.build,
                "files": files,
                "vocabulary": vocab_digest,
            },
            "mtp_gguf": {
                "inputs": inputs,
                "tools": pack_tools,
                "producer": producer,
                "files": gguf_files,
            },
        }
