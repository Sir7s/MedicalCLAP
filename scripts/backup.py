"""Backup / restore / verify CLI (P18).

What a backup contains
----------------------
* **PostgreSQL control plane** (`db.sql`) — tasks, jobs, outbox, history, audit.
* **Workspace storage** (`workspace.tar.gz`) — artifacts, snapshots, chunk files.
* **Qdrant index state** (`qdrant.json`) — collections and point counts, so a
  restore can tell whether the index needs re-building.
* **`manifest.json`** — sha256 + byte size of every component, plus the versions
  needed to interpret them.

What a backup deliberately does **not** contain
-----------------------------------------------
Large third-party artifacts (the ~1.7 GB CT-CLIP checkpoint, embedding caches).
Copying them into every backup would be wasteful, and their licence
(CC-BY-NC-SA) makes casual redistribution the wrong default. Instead the manifest
records their **provenance** — path, size, and how to re-obtain them — so a restore
is still complete, just re-fetching rather than unpacking. That is what "restorable"
means here, and the restore report says so explicitly.

Usage
-----
    python scripts/backup.py create  --out backups/
    python scripts/backup.py verify  backups/backup-20260721-101500
    python scripts/backup.py restore backups/backup-20260721-101500 [--yes]
    python scripts/backup.py list    backups/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MANIFEST = "manifest.json"
DB_DUMP = "db.sql"
WORKSPACE_TAR = "workspace.tar.gz"
QDRANT_STATE = "qdrant.json"

CTCLIP_SOURCE = (
    "https://huggingface.co/datasets/ibrahimhamamci/CT-RATE/"
    "resolve/main/models/CT-CLIP-Related/CT-CLIP_v2.pt"
)


# --------------------------------------------------------------------------- utils
def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while data := fh.read(chunk):
            h.update(data)
    return h.hexdigest()


def _component(path: Path, name: str, status: str = "ok", note: str = "") -> dict[str, Any]:
    entry: dict[str, Any] = {"name": name, "file": path.name, "status": status}
    if note:
        entry["note"] = note
    if path.is_file():
        entry["bytes"] = path.stat().st_size
        entry["sha256"] = sha256_file(path)
    return entry


# ----------------------------------------------------------------------- capture
def dump_postgres(dest: Path) -> dict[str, Any]:
    """pg_dump the control plane. Missing tooling/DB is recorded, not fatal."""
    url = os.environ.get(
        "MEDCLIP_PG_URL",
        "postgresql://medclip:medclip_dev_only@127.0.0.1:5432/medclip",
    )
    if shutil.which("pg_dump") is None:
        return {"name": "postgres", "file": DB_DUMP, "status": "skipped",
                "note": "pg_dump not on PATH"}
    try:
        with dest.open("wb") as fh:
            subprocess.run(["pg_dump", "--no-owner", "--no-acl", url],
                           stdout=fh, stderr=subprocess.PIPE, check=True, timeout=600)
    except Exception as exc:  # noqa: BLE001 - a backup must report, not crash
        dest.unlink(missing_ok=True)
        return {"name": "postgres", "file": DB_DUMP, "status": "failed",
                "note": str(exc)[:200]}
    return _component(dest, "postgres")


def archive_workspace(dest: Path, root: Path) -> dict[str, Any]:
    if not root.is_dir():
        return {"name": "workspace", "file": WORKSPACE_TAR, "status": "skipped",
                "note": f"no workspace root at {root}"}
    with tarfile.open(dest, "w:gz") as tar:
        tar.add(root, arcname=root.name)
    return _component(dest, "workspace")


def capture_qdrant(dest: Path) -> dict[str, Any]:
    """Record collection sizes so restore knows whether to re-index."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
        from app.retrieval.index import (  # noqa: PLC0415
            REPORT_COLLECTION,
            VOLUME_COLLECTION,
            count,
            get_client,
        )
        client = get_client()
        # Probe connectivity explicitly: count() swallows errors and returns 0, which
        # would report a healthy-looking empty index for an unreachable Qdrant.
        client.get_collections()
        state = {"collections": {VOLUME_COLLECTION: count(client, VOLUME_COLLECTION),
                                 REPORT_COLLECTION: count(client, REPORT_COLLECTION)}}
    except Exception as exc:  # noqa: BLE001
        return {"name": "qdrant", "file": QDRANT_STATE, "status": "skipped",
                "note": f"qdrant unreachable: {str(exc)[:120]}"}
    dest.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return _component(dest, "qdrant", note="index is re-buildable via scripts/index_ctclip.py")


def external_artifacts() -> list[dict[str, Any]]:
    """Large third-party assets: recorded by provenance, not copied (see module docstring)."""
    ckpt = Path(os.environ.get("MEDCLIP_CTCLIP_CKPT", "D:/ctclip_work/CT-CLIP_v2.pt"))
    return [{
        "name": "ct-clip-checkpoint",
        "path": str(ckpt),
        "present": ckpt.is_file(),
        "bytes": ckpt.stat().st_size if ckpt.is_file() else None,
        "source": CTCLIP_SOURCE,
        "licence": "CC-BY-NC-SA 4.0 — non-commercial; not redistributed in backups",
        "restore": "re-download from source (see docs/RETRIEVAL_SERVING.md)",
    }]


# ------------------------------------------------------------------------ create
def create_backup(out_dir: Path, workspace_root: Path | None = None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = out_dir / f"backup-{stamp}"
    target.mkdir(parents=True, exist_ok=True)
    root = workspace_root or Path(os.environ.get("MEDCLIP_WORKSPACE_ROOT", "workspace_data"))

    components = [
        dump_postgres(target / DB_DUMP),
        archive_workspace(target / WORKSPACE_TAR, root),
        capture_qdrant(target / QDRANT_STATE),
    ]
    manifest = {
        "format": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "components": components,
        "external_artifacts": external_artifacts(),
        "notes": "Large third-party assets are recorded by provenance, not copied.",
    }
    (target / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return target


# ------------------------------------------------------------------------ verify
def verify_backup(path: Path) -> dict[str, Any]:
    """Recompute checksums. Returns {ok, checked, problems[]}."""
    manifest_path = path / MANIFEST
    if not manifest_path.is_file():
        return {"ok": False, "checked": 0, "problems": [f"missing {MANIFEST}"]}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    checked = 0
    for comp in manifest.get("components", []):
        if comp.get("status") != "ok":
            continue
        f = path / comp["file"]
        if not f.is_file():
            problems.append(f"{comp['name']}: file missing ({comp['file']})")
            continue
        checked += 1
        if f.stat().st_size != comp.get("bytes"):
            problems.append(f"{comp['name']}: size mismatch")
        elif sha256_file(f) != comp.get("sha256"):
            problems.append(f"{comp['name']}: checksum mismatch (corrupted)")
    return {"ok": not problems, "checked": checked, "problems": problems}


# ----------------------------------------------------------------------- restore
def restore_plan(path: Path) -> dict[str, Any]:
    """What a restore would do — computed without touching anything."""
    manifest = json.loads((path / MANIFEST).read_text(encoding="utf-8"))
    restorable = [c["name"] for c in manifest.get("components", []) if c.get("status") == "ok"]
    unavailable = [f"{c['name']} ({c.get('note', c.get('status'))})"
                   for c in manifest.get("components", []) if c.get("status") != "ok"]
    refetch = [a["name"] for a in manifest.get("external_artifacts", [])]
    return {"restore": restorable, "unavailable": unavailable, "refetch": refetch,
            "created_at": manifest.get("created_at")}


def restore_backup(path: Path, *, confirm: bool = False) -> dict[str, Any]:
    """Refuses to run on an unverified/corrupt backup — a bad restore is worse
    than no restore."""
    check = verify_backup(path)
    if not check["ok"]:
        raise SystemExit(f"refusing to restore: {check['problems']}")
    plan = restore_plan(path)
    if not confirm:
        return {"dry_run": True, **plan}

    root = Path(os.environ.get("MEDCLIP_WORKSPACE_ROOT", "workspace_data"))
    tar_path = path / WORKSPACE_TAR
    if tar_path.is_file():
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(root.parent, filter="data")  # nosec B202 - filtered extraction
    dump = path / DB_DUMP
    if dump.is_file() and shutil.which("psql"):
        url = os.environ.get(
            "MEDCLIP_PG_URL",
            "postgresql://medclip:medclip_dev_only@127.0.0.1:5432/medclip")
        subprocess.run(["psql", url, "-f", str(dump)], check=True, timeout=900)
    return {"dry_run": False, **plan}


# -------------------------------------------------------------------------- cli
def _say(text: str) -> None:
    """Print without exploding on legacy consoles (cp1252 can't encode em dashes,
    and error notes may quote arbitrary upstream text)."""
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    sys.stdout.write(text.encode(enc, errors="replace").decode(enc, errors="replace") + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Backup / restore the local control plane.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--out", default="backups")
    v = sub.add_parser("verify")
    v.add_argument("path")
    r = sub.add_parser("restore")
    r.add_argument("path")
    r.add_argument("--yes", action="store_true")
    ls = sub.add_parser("list")
    ls.add_argument("dir", nargs="?", default="backups")
    args = ap.parse_args()

    if args.cmd == "create":
        target = create_backup(Path(args.out))
        result = verify_backup(target)
        _say(f"backup created: {target}")
        for comp in json.loads((target / MANIFEST).read_text(encoding="utf-8"))["components"]:
            note = comp.get("note", "")
            _say(f"  {comp['name']:<10} {comp['status']}{'  ' + note if note else ''}")
        _say(f"verify: {'OK' if result['ok'] else result['problems']}")
    elif args.cmd == "verify":
        res = verify_backup(Path(args.path))
        print(json.dumps(res, indent=2))
        raise SystemExit(0 if res["ok"] else 1)
    elif args.cmd == "restore":
        print(json.dumps(restore_backup(Path(args.path), confirm=args.yes), indent=2))
    elif args.cmd == "list":
        d = Path(args.dir)
        for b in sorted(d.glob("backup-*")) if d.is_dir() else []:
            ok = verify_backup(b)["ok"]
            print(f"{b.name}  {'OK' if ok else 'CORRUPT'}")


if __name__ == "__main__":
    main()
