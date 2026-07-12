# Implementation Conformance Report — P12

Per IMP-GOV-001/002; Architecture SPEC-07 sec 8.2-8.5.

| Spec | Requirement | Status | Evidence |
|---|---|---|---|
| SPEC-07 8.4 | Train bidirectional CLIP + multi-label aux on CT-RATE | implemented | `ml/models/train.py`; real GPU runs (loss 1.76→0.22) |
| SPEC-07 8.5 | Model selection by held-out validation | implemented | best mean-val-Recall@1 checkpoint; `best_epoch` in manifest |
| SPEC-07 8.5 | Report CT↔Report Recall@1/5/10, mAP, nDCG | implemented | `metrics.evaluate_bidirectional`; `metrics.json` |
| Master Plan P12 | Deterministic, reproducible training | implemented | seeded (42); frozen `TrainConfig`; per-run manifest |
| Master Plan P12 | Resumable long run (cloud) | implemented | `--resume` from `last.pt`; `test_train_resume` |
| Master Plan P12 | Deployment-candidate checkpoint + real metrics | **pending** | cloud run (`train_ctrate_colab.ipynb`) — user executes |
| Data strategy | Local = validate subsets; real train = Colab/Kaggle | honored | local runs data-limited; cloud notebook delivered |
| CT-CLIP policy | No CT-CLIP image weights into PointNet++ | honored | PointNet++ trained from init |
| H-13 / H-14 | No PHI / weights committed | honored | `runs/` git-ignored; `.gitignore` covers `*.pt/*.npz` |
| Point count | 32768 target | honored | local budget 16384 (documented); cloud notebook 32768 |

**In-scope coverage:** training/selection/metrics/reproducibility/resume pipeline
100% implemented and validated on real GPU + real data. **One gated item pending
by design** — the generalizing cloud checkpoint + its real held-out metrics (user
runs the notebook). No architecture deviations.
