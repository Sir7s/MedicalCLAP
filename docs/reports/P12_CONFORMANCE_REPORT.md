# Implementation Conformance Report — P12

Per IMP-GOV-001/002; Architecture SPEC-07 sec 8.2-8.5, as amended by AUP-005.

| Spec | Requirement | Status | Evidence |
|---|---|---|---|
| SPEC-07 8.4 | Train bidirectional CLIP + multi-label aux on CT-RATE | implemented | `ml/models/train.py`; real GPU runs (loss 1.76→0.22) |
| SPEC-07 8.5 | Model selection by held-out validation | implemented | best-val selection every run; `best_epoch` in manifests |
| SPEC-07 8.5 | Report CT↔Report Recall@1/5/10, mAP, nDCG | implemented | both directions; `runs/*/metrics.json`, model card |
| Master Plan P12 | Deterministic, reproducible training | implemented | seeded (42), frozen `TrainConfig`, per-run manifest |
| Master Plan P12 | Resumable long runs | implemented | `--resume` from `last.pt`; `test_train_resume` |
| Master Plan P12 | Deployment-candidate checkpoint + real metrics | **implemented** | CT-CLIP recall + re-rank; held-out R@10 0.511→0.533 |
| **AUP-005** | Deployed encoder = CT-CLIP; PointNet++ = documented research | implemented | model card; PointNet++ removed from serving path |
| **AUP-004** | Findings-grounded re-rank + explanations | implemented | `ml/models/rerank.py`, `findings.py`; `test_rerank.py` |
| **AUP-001** | Supervised CT-encoder pretraining stage | implemented | `ml/models/pretrain.py`; R@10 0.051→0.127 |
| **AUP-002** | CT-FM feature distillation (teacher, not weights) | implemented | `ml/models/{ctfm_teacher,distill}.py` |
| Evaluation integrity | Leakage-free held-out evaluation | honored | CT-RATE `valid` split; CT-CLIP did not train on valid |
| CT-CLIP policy | No incompatible weights loaded *into* PointNet++ | honored | CT-CLIP adopted as a cited component (AUP-005 §2), not injected |
| Licensing | Third-party model/data licence recorded | recorded | CC-BY-NC-SA (CT-CLIP + CT-RATE); enforcement deferred to P17 |
| H-13 / H-14 | No PHI / weights committed | honored | `runs/` git-ignored; checkpoint + caches outside repo |
| Data governance | Patient-level split, zero leakage | honored | P7 split tooling; 1 volume/patient in the eval set |

**Deviations:** one, formalized — the deployed image encoder is CT-CLIP rather than
PointNet++ (AUP-005), with the from-scratch investigation retained as an honest
negative result. **Pending for P20:** the Freeze Test Profile still asserts
PointNet++ behaviour and must be restated per AUP-005 §5 before the Freeze Run.

**In-scope coverage:** 100% of P12 requirements implemented and evidenced.
