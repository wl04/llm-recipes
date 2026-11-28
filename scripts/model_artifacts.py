"""Inventory and stage immutable preparation artifacts without copying model payloads."""

import errno
import fcntl
import hashlib
import json
import os
import shutil
import stat
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import TypedDict

FICLONE = 0x40049409
UNSUPPORTED_LINK = {errno.EXDEV, errno.EPERM, errno.EACCES, errno.EMLINK, errno.EOPNOTSUPP}
UNSUPPORTED_CLONE = UNSUPPORTED_LINK | {errno.ENOTTY, errno.EINVAL, errno.ENOSYS}
PAYLOAD_SUFFIXES = {".bin", ".gguf", ".safetensors"}


class FileRecord(TypedDict):
    size: int
    mtime_ns: int
    sha256: str


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def artifact_path(root: Path, name: str) -> Path:
    relative = Path(name)
    path = root / relative
    if relative.is_absolute() or ".." in relative.parts or path.absolute() != path.resolve():
        raise ValueError(f"Redirected preparation artifact: {path}")
    return path


def file_info(path: Path) -> os.stat_result:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not info.st_size:
        raise ValueError(f"Missing or empty preparation artifact: {path}")
    return info


def inventory(root: Path, names: Iterable[str] | None = None) -> dict[str, FileRecord]:
    """Record complete file identities for a trusted, finished preparation."""
    if names is None:
        names = (
            path.relative_to(root).as_posix()
            for path in sorted(root.rglob("*"))
            if path.is_symlink() or not path.is_dir()
        )
    result: dict[str, FileRecord] = {}
    for name in names:
        path = artifact_path(root, name)
        info = file_info(path)
        result[name] = {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "sha256": sha256(path)}
    if not result:
        raise ValueError(f"Empty preparation inventory: {root}")
    return result


def verify_inventory(
    root: Path,
    records: Mapping[str, FileRecord],
    *,
    verify: bool = False,
    sizes_only: bool = False,
) -> None:
    """Verify sizes and rehash changed files, or every file on explicit verification."""
    if not records:
        raise ValueError(f"Empty preparation inventory: {root}")
    for name, record in records.items():
        path = artifact_path(root, name)
        info = file_info(path)
        if info.st_size != record["size"]:
            raise ValueError(f"Preparation size mismatch: {path}")
        if (
            not sizes_only
            and (verify or info.st_mtime_ns != record["mtime_ns"])
            and sha256(path) != record["sha256"]
        ):
            raise ValueError(f"Preparation checksum mismatch: {path}")


def verify_output_receipt(folder: Path, layout: Mapping[str, str]) -> None:
    """Check that a versioned preparation still contains every recorded serving file."""
    metadata = artifact_path(folder, "artifacts.json")
    try:
        receipt = json.loads(metadata.read_text())
        if receipt.get("schema") != 1:
            raise ValueError("unsupported artifact schema")
        for artifact, relative in layout.items():
            verify_inventory(folder / relative, receipt[artifact]["files"], sizes_only=True)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"Invalid artifact receipt {metadata}: {error}") from error


def stage_files(
    donor: Path,
    candidate: Path,
    records: Mapping[str, FileRecord],
    *,
    allow_copy: bool = False,
) -> dict[str, FileRecord]:
    """Stage verified files into a private directory; only payloads may share inodes."""
    result: dict[str, FileRecord] = {}
    for name, record in records.items():
        source = artifact_path(donor, name)
        dest = artifact_path(candidate, name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix in PAYLOAD_SUFFIXES:
            _stage_payload(source, dest, record["size"], allow_copy=allow_copy)
        else:
            shutil.copyfile(source, dest)
        info = file_info(dest)
        if info.st_size != record["size"]:
            raise ValueError(f"Preparation size changed while staging: {source}")
        if (
            source.suffix not in PAYLOAD_SUFFIXES or info.st_mtime_ns != record["mtime_ns"]
        ) and sha256(dest) != record["sha256"]:
            raise ValueError(f"Preparation checksum changed while staging: {source}")
        result[name] = {**record, "mtime_ns": info.st_mtime_ns}
    return result


def _stage_payload(source: Path, dest: Path, size: int, *, allow_copy: bool) -> None:
    try:
        os.link(source, dest, follow_symlinks=False)
    except OSError as error:
        if error.errno not in UNSUPPORTED_LINK:
            raise
    else:
        return
    try:
        with source.open("rb") as reader, dest.open("xb") as writer:
            fcntl.ioctl(writer.fileno(), FICLONE, reader.fileno())
    except OSError as error:
        if error.errno not in UNSUPPORTED_CLONE:
            raise
        dest.unlink(missing_ok=True)
    else:
        return
    if not allow_copy:
        raise ValueError(f"Copying {source} requires {size:,} bytes; retry with --allow-copy")
    shutil.copyfile(source, dest)


@contextmanager
def staged_preparation(final: Path, owner: Mapping[str, object]) -> Iterator[Path]:
    """Publish a complete versioned preparation by renaming its private staging directory."""
    stage = final.with_name(f".{final.name}.partial")
    artifact_path(final.parent, final.name)
    artifact_path(final.parent, stage.name)
    marker = stage / "preparing.json"
    if stage.exists():
        has_payload = any(path != marker for path in stage.iterdir())
        if has_payload:
            try:
                previous = json.loads(artifact_path(stage, marker.name).read_text())
            except (OSError, ValueError) as error:
                raise ValueError(
                    f"Cannot verify partial preparation at {stage}: {error}"
                ) from error
            if previous != owner:
                raise ValueError(f"Conflicting partial preparation at {stage}")
        try:
            shutil.rmtree(stage)
        except OSError as error:
            raise ValueError(f"Cannot clear partial preparation at {stage}: {error}") from error
    stage.mkdir(parents=True)
    marker.write_text(json.dumps(dict(owner)) + "\n")
    yield stage
    stage.rename(final)
    (final / marker.name).unlink()
