"""Stream-and-cache CT-RATE at scale (local, storage-light).

For each volume: download the raw NIfTI → preprocess to the point-cloud cache
(+ optional CT-FM teacher feature) → delete the raw. Only ~150 KB of caches per
volume survives, so thousands of volumes fit in a few GB regardless of the raw
dataset size. Idempotent/resumable (skips fully-cached volumes); bounded to one
raw file on disk at a time. Raws that already existed locally are kept, not deleted.

Run:  python -m ml.models.scale_acquire            # streams the active split
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ..datasets.ct_rate.acquire import VOL_DEST, _fetch_one, _token
from ..datasets.ct_rate.select import volume_repo_path
from .ctfm_teacher import CACHE_DIR as CTFM_CACHE
from .ctfm_teacher import cache_teacher_feature
from .data import CACHE, SPLIT_JSON, cache_pointcloud

PROGRESS = Path("data/ct_rate/scale_progress.json")


def _all_split_vols() -> list[str]:
    rev = json.loads(SPLIT_JSON.read_text(encoding="utf-8"))
    vols: list[str] = []
    for split in ("train", "val", "test"):
        vols.extend(rev["volumes"][split])
    return sorted(set(vols))


def scale_acquire(vols: list[str], *, extract_ctfm: bool = True,
                  n_points: int = 16384, seed: int = 42) -> dict:
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    token = _token()
    n = len(vols)
    downloaded = cached = skipped = failed = deleted = 0
    t0 = time.time()
    for i, vol in enumerate(vols, 1):
        need_pc = not (CACHE / f"{vol}.npz").is_file()
        need_tf = extract_ctfm and not (CTFM_CACHE / f"{vol}.npy").is_file()
        if not need_pc and not need_tf:
            skipped += 1
            continue
        repo_path = volume_repo_path(vol)
        raw = VOL_DEST / repo_path
        preexisting = raw.is_file() and raw.stat().st_size > 0
        try:
            if not preexisting:
                raw = Path(_fetch_one(repo_path, token))
                downloaded += 1
            if need_pc:
                cache_pointcloud(vol, n_points, seed)
            if need_tf:
                cache_teacher_feature(vol, raw)
            cached += 1
        except Exception as exc:  # noqa: BLE001 - record and continue; rerun resumes
            failed += 1
            print(f"[scale] FAIL {vol}: {exc}", flush=True)
        finally:
            if not preexisting and Path(raw).is_file():
                Path(raw).unlink()  # reclaim space immediately
                deleted += 1
        if i % 10 == 0 or i == n:
            rate = (time.time() - t0) / max(cached + failed, 1)
            eta_h = rate * (n - i) / 3600
            summary = {"seen": i, "total": n, "downloaded": downloaded, "cached": cached,
                       "skipped": skipped, "failed": failed, "deleted_raws": deleted,
                       "sec_per_vol": round(rate, 1), "eta_hours": round(eta_h, 1)}
            PROGRESS.write_text(json.dumps(summary), encoding="utf-8")
            print(f"[scale] {i}/{n} cached={cached} skip={skipped} fail={failed} "
                  f"~{rate:.1f}s/vol eta~{eta_h:.1f}h", flush=True)
    return json.loads(PROGRESS.read_text(encoding="utf-8"))


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Stream-and-cache the active CT-RATE split.")
    ap.add_argument("--no-ctfm", action="store_true", help="skip CT-FM teacher features")
    args = ap.parse_args()
    vols = _all_split_vols()
    print(f"streaming {len(vols)} volumes (extract_ctfm={not args.no_ctfm})", flush=True)
    print(scale_acquire(vols, extract_ctfm=not args.no_ctfm))


if __name__ == "__main__":
    main()
