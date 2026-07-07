"""Atomic artifact finalize (P5, SPEC-04 §5.2/5.3).

    write .partial -> flush -> fsync(file) -> SHA-256
    -> atomic rename -> fsync(parent, best-effort on Windows)
    -> sidecar manifest JSON

An artifact is visible iff its final name exists; readers never see partial
content. Finalized files are made read-only (immutability, SPEC-04 §5.2).
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from .. import failpoints


class ArtifactError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _fsync_dir(directory: Path) -> None:
    try:  # POSIX only; Windows cannot open directories for fsync.
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def finalize_artifact(directory: Path, name: str, data: bytes) -> dict:
    """Atomically materialize `data` as `directory/name`. Returns the manifest."""
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / name
    partial = directory / f"{name}.partial"
    if final.exists():
        raise ArtifactError(f"artifact already finalized: {final}")

    with partial.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    digest = sha256_file(partial)

    failpoints.trip("FP-ARTIFACT-BEFORE-RENAME")  # crash => only .partial exists

    os.replace(partial, final)  # atomic on the same filesystem
    _fsync_dir(directory)
    final.chmod(final.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))

    manifest = {
        "name": name,
        "size_bytes": len(data),
        "sha256": digest,
        "finalized": True,
    }
    mpath = directory / f"{name}.manifest.json"
    tmp = directory / f"{name}.manifest.json.partial"
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, mpath)
    _fsync_dir(directory)
    return manifest


def verify_artifact(directory: Path, name: str) -> bool:
    """True iff the finalized file exists and matches its manifest hash."""
    final, mpath = directory / name, directory / f"{name}.manifest.json"
    if not final.is_file() or not mpath.is_file():
        return False
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    return sha256_file(final) == manifest["sha256"]


def is_visible(directory: Path, name: str) -> bool:
    """Readers must never observe partial artifacts."""
    return (directory / name).is_file()
