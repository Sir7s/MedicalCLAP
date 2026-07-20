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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue

from ..datasets.ct_rate.acquire import REPO, VOL_DEST, _token
from ..datasets.ct_rate.select import volume_repo_path
from .ctfm_teacher import CACHE_DIR as CTFM_CACHE
from .ctfm_teacher import cache_teacher_feature
from .data import CACHE, SPLIT_JSON, cache_pointcloud

PROGRESS = Path("data/ct_rate/scale_progress.json")


def _fetch_via_hub(repo_path: str, token: str, attempts: int = 4) -> Path:
    """Fast path: hf_hub_download (hf_transfer parallel chunks), resetting the
    cached session between attempts so a poisoned 'client has been closed' state
    doesn't stick."""
    from huggingface_hub import hf_hub_download
    from huggingface_hub.utils._http import close_session
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            p = hf_hub_download(REPO, repo_path, repo_type="dataset",
                                local_dir=str(VOL_DEST), token=token)
            return Path(p)
        except Exception as exc:  # noqa: BLE001 - retry transient network errors
            last = exc
            try:
                close_session()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"hub: {last}")


def _download(repo_path: str, token: str) -> Path:
    """Fast hub download, falling back to a fresh-session requests stream."""
    try:
        return _fetch_via_hub(repo_path, token)
    except Exception:  # noqa: BLE001 - fall back to the slow-but-reliable path
        return _robust_download(repo_path, token)


def _robust_download(repo_path: str, token: str, attempts: int = 8) -> Path:
    """Download one file with a FRESH requests session per attempt.

    huggingface_hub reuses a session that gets poisoned ("client has been closed")
    after an SSL drop, so all its internal retries then fail. A new session each
    attempt sidesteps that and tolerates the flaky HF CDN.
    """
    import requests
    url = f"https://huggingface.co/datasets/{REPO}/resolve/main/{repo_path}"
    dest = VOL_DEST / repo_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Bearer {token}"}
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with requests.Session() as s:
                r = s.get(url, headers=headers, stream=True, timeout=(30, 120))
                r.raise_for_status()
                tmp = dest.with_name(dest.name + ".part")
                with tmp.open("wb") as fh:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        if chunk:
                            fh.write(chunk)
                if tmp.stat().st_size == 0:
                    raise OSError("empty download")
                tmp.replace(dest)
                return dest
        except Exception as exc:  # noqa: BLE001 - retry transient network errors
            last = exc
            time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"{repo_path}: failed after {attempts} attempts: {last}")


def _all_split_vols() -> list[str]:
    rev = json.loads(SPLIT_JSON.read_text(encoding="utf-8"))
    vols: list[str] = []
    for split in ("train", "val", "test"):
        vols.extend(rev["volumes"][split])
    return sorted(set(vols))


def scale_acquire(vols: list[str], *, extract_ctfm: bool = True, n_points: int = 16384,
                  seed: int = 42, workers: int = 8, buffer: int = 16) -> dict:
    """Producer/consumer: `workers` threads download concurrently into a bounded
    buffer (disk-capped to ~(workers+buffer) raws); the main thread preprocesses
    and deletes. Concurrency hides the flaky-CDN per-file retry latency, so the
    run is preprocessing-bound rather than download-bound."""
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"  # parallel-chunk accelerated download
    token = _token()

    todo = []
    skipped = 0
    for vol in vols:
        need_pc = not (CACHE / f"{vol}.npz").is_file()
        need_tf = extract_ctfm and not (CTFM_CACHE / f"{vol}.npy").is_file()
        if need_pc or need_tf:
            todo.append((vol, need_pc, need_tf))
        else:
            skipped += 1
    n = len(todo)
    q: Queue = Queue(maxsize=buffer)
    counters = {"downloaded": 0, "failed": 0}
    lock = threading.Lock()

    def produce(item):
        vol = item[0]
        repo_path = volume_repo_path(vol)
        raw = VOL_DEST / repo_path
        preexisting = raw.is_file() and raw.stat().st_size > 0
        try:
            if not preexisting:
                raw = _download(repo_path, token)
                with lock:
                    counters["downloaded"] += 1
            q.put((item, raw, preexisting))
        except Exception as exc:  # noqa: BLE001 - record; consumer still counts this item
            with lock:
                counters["failed"] += 1
            print(f"[scale] FAIL dl {vol}: {exc}", flush=True)
            q.put((item, None, preexisting))

    cached = deleted = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for item in todo:
            ex.submit(produce, item)
        for i in range(1, n + 1):
            (vol, need_pc, need_tf), raw, preexisting = q.get()
            if raw is not None:
                try:
                    if need_pc:
                        cache_pointcloud(vol, n_points, seed)
                    if need_tf:
                        cache_teacher_feature(vol, raw)
                    cached += 1
                except Exception as exc:  # noqa: BLE001 - record and continue; rerun resumes
                    with lock:
                        counters["failed"] += 1
                    print(f"[scale] FAIL prep {vol}: {exc}", flush=True)
                finally:
                    if not preexisting and Path(raw).is_file():
                        Path(raw).unlink()  # reclaim space immediately
                        deleted += 1
            if i % 10 == 0 or i == n:
                rate = (time.time() - t0) / max(i, 1)
                eta_h = rate * (n - i) / 3600
                summary = {"seen": i, "total": n, "downloaded": counters["downloaded"],
                           "cached": cached, "skipped": skipped, "failed": counters["failed"],
                           "deleted_raws": deleted, "sec_per_vol": round(rate, 1),
                           "eta_hours": round(eta_h, 1)}
                PROGRESS.write_text(json.dumps(summary), encoding="utf-8")
                print(f"[scale] {i}/{n} cached={cached} fail={counters['failed']} "
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
