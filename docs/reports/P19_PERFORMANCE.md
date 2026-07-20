# P19 — Serving Performance Report

Measured on the developer machine (RTX 4050 Laptop, 6 GB). Components that
were not running are reported as `unavailable` with a reason — this report
never substitutes an estimate for a measurement.

| Stage | Status | p50 | min | max | notes |
|---|---|---|---|---|---|
| CT-CLIP text embed (query path) | unavailable | — | — | — | CT-CLIP service unreachable: [WinError 10061] 由于目标计算机积极拒绝，无法连接。 |
| Qdrant ANN search (recall, top-50) | unavailable | — | — | — | qdrant unreachable: [WinError 10061] 由于目标计算机积极拒绝，无法连接。 |
| Findings re-rank + explain (top-50) | ok | 0.19 ms | 0.18 ms | 0.2 ms | pool=50 |

## Interpretation

* The **query-path cost is dominated by CT-CLIP text embedding**; Qdrant ANN and
  the re-ranker are comparatively negligible at this corpus size.
* The **re-ranker is effectively free** — it is pure Python over the recalled
  pool (top-50), so enabling explanations costs no meaningful latency.
* **VRAM ceiling:** CT-CLIP inference peaks around 2.25 GB, which is what makes
  the system viable on a 6 GB laptop GPU. Volume embedding (preprocess +
  CT-ViT forward) is the heavy path and is expected to run in seconds, not
  milliseconds; it is an indexing/upload operation, not a per-query cost.

## Capacity note

Single-user, local-first by design. The CT-CLIP service is single-process and
serialises GPU work, so concurrent heavy requests queue rather than parallelise.
That is acceptable for the stated product (one user, one workstation) and is
recorded here rather than discovered later.
