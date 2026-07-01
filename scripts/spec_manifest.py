#!/usr/bin/env python3
"""Deterministic specification version-lock manifest tool (P0 / Subphase 1).

Implements the normative bundle-hash form mandated by the Architecture
Specification Bundle v2.4.5 (SPEC-01 sec 1.1) and the Freeze Test Profile
v1.1 (sec 2 "Normative Test Artifacts"):

    line     = SPEC_ID + NUL + VERSION + NUL + lowercase_hex_sha256 + LF
    bundle   = SHA-256( concat(sorted_by_spec_id(line)) )

The manifest pins the four authoritative governance documents so that any
later drift (an edited or swapped PDF) is detected by `--check`. State files
(PROJECT_STATE.*) are intentionally NOT pinned here: they are living phase
state, not immutable specifications.

Usage:
    python scripts/spec_manifest.py --write    # regenerate SPEC_MANIFEST.json
    python scripts/spec_manifest.py --check     # verify on-disk == manifest (exit 1 on drift)
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "specs" / "SPEC_MANIFEST.json"

# The four authoritative governance documents (the locked specification bundle).
# spec_id / name / version / status / repo-relative path / mandatory.
DOCUMENTS = [
    {
        "spec_id": "DOC-ARCH",
        "name": "Architecture Specification Bundle",
        "version": "2.4.5",
        "status": "final_freeze_candidate",
        "path": "docs/specs/3D_Medical_CLIP_Architecture_v2.4.5_CN.pdf",
        "mandatory": True,
    },
    {
        "spec_id": "DOC-MASTER",
        "name": "Master Phased AI Execution Plan",
        "version": "1.0",
        "status": "approved_execution_baseline",
        "path": "docs/specs/3D_Medical_CLIP_Master_Plan_v1.0_CN.pdf",
        "mandatory": True,
    },
    {
        "spec_id": "DOC-APPENDIX",
        "name": "Implementation Appendix",
        "version": "1.1",
        "status": "implementation_ready",
        "path": "docs/specs/3D_Medical_CLIP_Implementation_Appendix_v1.1_CN.pdf",
        "mandatory": True,
    },
    {
        "spec_id": "DOC-FREEZE",
        "name": "Freeze Test Profile",
        "version": "1.1",
        "status": "ready_for_execution",
        "path": "docs/specs/3D_Medical_CLIP_Freeze_Test_Profile_v1.1_CN.pdf",
        "mandatory": True,
    },
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def bundle_root_hash(entries: list[dict]) -> str:
    """Concatenate the normative line for each entry (sorted by spec_id) and hash."""
    h = hashlib.sha256()
    for e in sorted(entries, key=lambda x: x["spec_id"]):
        line = f"{e['spec_id']}\x00{e['version']}\x00{e['sha256'].lower()}\n"
        h.update(line.encode("utf-8"))
    return h.hexdigest()


def build_manifest() -> dict:
    docs = []
    missing = []
    for d in DOCUMENTS:
        fp = REPO_ROOT / str(d["path"])
        if not fp.is_file():
            missing.append(d["path"])
            continue
        entry = dict(d)
        entry["size_bytes"] = fp.stat().st_size
        entry["sha256"] = sha256_file(fp)
        docs.append(entry)
    if missing:
        raise FileNotFoundError(f"Authoritative documents missing: {missing}")
    return {
        "manifest_version": "1.0",
        "generated_for_phase": "P0",
        "architecture_bundle_version": "2.4.5",
        "hash_algorithm": "sha256",
        "bundle_line_format": "SPEC_ID + NUL + VERSION + NUL + lowercase_hex_sha256 + LF",
        "documents": docs,
        "documents_root_sha256": bundle_root_hash(docs),
    }


def write_manifest() -> dict:
    manifest = build_manifest()
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def check_manifest() -> list[str]:
    """Return a list of discrepancies; empty means the lock holds."""
    problems: list[str] = []
    if not MANIFEST_PATH.is_file():
        return [f"manifest not found: {MANIFEST_PATH}"]
    stored = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fresh = build_manifest()

    stored_by_id = {d["spec_id"]: d for d in stored.get("documents", [])}
    fresh_by_id = {d["spec_id"]: d for d in fresh["documents"]}

    if set(stored_by_id) != set(fresh_by_id):
        problems.append(
            f"document set mismatch: manifest={sorted(stored_by_id)} disk={sorted(fresh_by_id)}"
        )
    for spec_id, fresh_doc in fresh_by_id.items():
        sd = stored_by_id.get(spec_id)
        if not sd:
            continue
        if sd.get("sha256") != fresh_doc["sha256"]:
            problems.append(
                f"{spec_id} hash drift: manifest={sd.get('sha256')} disk={fresh_doc['sha256']}"
            )
        if sd.get("version") != fresh_doc["version"]:
            problems.append(
                f"{spec_id} version drift: "
                f"manifest={sd.get('version')} disk-entry={fresh_doc['version']}"
            )
    if stored.get("documents_root_sha256") != fresh["documents_root_sha256"]:
        problems.append(
            "documents_root_sha256 drift: "
            f"manifest={stored.get('documents_root_sha256')} "
            f"computed={fresh['documents_root_sha256']}"
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true", help="regenerate the manifest")
    g.add_argument("--check", action="store_true", help="verify on-disk docs match the manifest")
    args = ap.parse_args(argv)

    if args.write:
        m = write_manifest()
        print(f"wrote {MANIFEST_PATH.relative_to(REPO_ROOT)}")
        print(f"documents_root_sha256 = {m['documents_root_sha256']}")
        return 0

    problems = check_manifest()
    if problems:
        print("SPEC MANIFEST CHECK FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("SPEC manifest check OK: all authoritative documents match the lock.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
