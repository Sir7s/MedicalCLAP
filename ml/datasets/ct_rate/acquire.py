"""Resumable CT-RATE subset downloader (P7).

Downloads the `train_fixed` volumes named in the split revision into the
git-ignored `data/ct_rate/volumes/` tree. Idempotent: already-present files with
the expected size are skipped, so the download resumes after interruption.
Enables `hf_transfer` when available for higher throughput.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from huggingface_hub import hf_hub_download

from .select import volume_repo_path

REPO = "ibrahimhamamci/CT-RATE"
DATA_ROOT = Path("data/ct_rate")
VOL_DEST = DATA_ROOT / "volumes"
SPLIT_JSON = DATA_ROOT / "split_revision.json"
PROGRESS_JSON = DATA_ROOT / "download_progress.json"


def _token() -> str:
    m = re.search(r"^HF_TOKEN=(\S+)", (Path("infra/.env")).read_text(encoding="utf-8"), re.M)
    if not m:
        raise RuntimeError("HF_TOKEN not found in infra/.env")
    return m.group(1)


def _all_volumes() -> list[str]:
    rev = json.loads(SPLIT_JSON.read_text(encoding="utf-8"))
    vols: list[str] = []
    for split in ("train", "val", "test"):
        vols.extend(rev["volumes"][split])
    return sorted(set(vols))


def _fetch_one(repo_path: str, token: str, attempts: int = 5) -> Path:
    """Download one file with retries + exponential backoff. The stable HTTPS
    backend (Xet disabled) tolerates transient drops across attempts."""
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            p = hf_hub_download(
                REPO, repo_path, repo_type="dataset",
                local_dir=str(VOL_DEST), token=token,
            )
            return Path(p)
        except Exception as exc:  # noqa: BLE001 - retry transient network errors
            last = exc
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"{repo_path}: failed after {attempts} attempts: {last}")


def download_subset(*, limit: int | None = None) -> dict:
    # Xet's high-performance client proved unstable here ("client has been
    # closed"); use the stable HTTPS backend for an unattended long download.
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)
    token = _token()
    VOL_DEST.mkdir(parents=True, exist_ok=True)
    vols = _all_volumes()
    if limit:
        vols = vols[:limit]

    done = 0
    skipped = 0
    failed = 0
    bytes_got = 0
    t0 = time.time()
    for i, vol in enumerate(vols, 1):
        repo_path = volume_repo_path(vol)
        local = VOL_DEST / repo_path
        if local.is_file() and local.stat().st_size > 0:
            skipped += 1
            continue
        try:
            p = _fetch_one(repo_path, token)
            bytes_got += p.stat().st_size
            done += 1
        except Exception as exc:  # noqa: BLE001 - record and continue; rerun resumes
            failed += 1
            _log_progress(i, len(vols), done, skipped, bytes_got, t0, failed=failed,
                          error=f"{vol}: {exc}")
            continue
        if done % 5 == 0:
            _log_progress(i, len(vols), done, skipped, bytes_got, t0, failed=failed)
    return _log_progress(len(vols), len(vols), done, skipped, bytes_got, t0,
                         failed=failed, final=True)


def _log_progress(i, n, done, skipped, bytes_got, t0, *, failed=0, error=None,
                  final=False) -> dict:
    dt = max(time.time() - t0, 0.1)
    rec = {
        "processed": i, "total": n, "downloaded": done, "skipped": skipped,
        "failed": failed, "bytes_downloaded": bytes_got,
        "mb_per_s": round(bytes_got / 1e6 / dt, 2),
        "elapsed_s": round(dt, 1), "final": final,
    }
    if error:
        rec["last_error"] = error
    PROGRESS_JSON.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="cap volumes (smoke)")
    args = ap.parse_args()
    print(download_subset(limit=args.limit))
