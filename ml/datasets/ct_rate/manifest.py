"""Canonical dataset manifest + root hash (P7, SPEC-06 §7.3).

Root hash form (SPEC-06 §7.3):
    line = UTF8(NFC-normalized relative POSIX path) + NUL
         + decimal_size + NUL + lowercase_sha256 + LF
    sort lines by UTF-8 bytes of the path, then SHA-256 the concatenation.

This makes the hash stable across platforms, path separators, and Unicode
normalization (FR-DATA-001).
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path

DATA_ROOT = Path("data/ct_rate")
VOL_DEST = DATA_ROOT / "volumes"
MANIFEST_JSON = DATA_ROOT / "MANIFEST.json"


@dataclass
class FileEntry:
    path: str          # NFC-normalized relative POSIX path
    size: int
    sha256: str


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_line(entry: FileEntry) -> bytes:
    norm = unicodedata.normalize("NFC", entry.path)
    return (
        norm.encode("utf-8") + b"\x00"
        + str(entry.size).encode("ascii") + b"\x00"
        + entry.sha256.lower().encode("ascii") + b"\n"
    )


def root_hash(entries: list[FileEntry]) -> str:
    ordered = sorted(entries, key=lambda e: unicodedata.normalize("NFC", e.path).encode("utf-8"))
    h = hashlib.sha256()
    for e in ordered:
        h.update(canonical_line(e))
    return h.hexdigest()


def scan(root: Path = VOL_DEST) -> list[FileEntry]:
    entries: list[FileEntry] = []
    for p in sorted(root.rglob("*.nii.gz")):
        rel = p.relative_to(root).as_posix()
        entries.append(FileEntry(rel, p.stat().st_size, sha256_file(p)))
    return entries


def build_manifest() -> dict:
    entries = scan()
    manifest = {
        "dataset": "CT-RATE",
        "source_variant": "train_fixed",
        "hash_form": "NFC(path) + NUL + size + NUL + lower_sha256 + LF; sorted by utf8(path)",
        "file_count": len(entries),
        "total_bytes": sum(e.size for e in entries),
        "root_sha256": root_hash(entries),
        "files": [{"path": e.path, "size": e.size, "sha256": e.sha256} for e in entries],
    }
    MANIFEST_JSON.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    m = build_manifest()
    print(f"files={m['file_count']} total={m['total_bytes']/1e9:.1f} GB "
          f"root_sha256={m['root_sha256']}")
