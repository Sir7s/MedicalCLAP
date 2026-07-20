# 3D Medical CLIP — PROJECT STATE

**State version:** 1.0  
**Last updated:** 2026-07-21  
**Repository:** Sir7s/MedicalCLAP  
**Architecture version:** 2.4.5 (`final_freeze_candidate`) · **Master Plan:** v1.0  
**Current phase:** P19 — Full Integration, Performance and Regression
**Active branch:** `phase/P19-integration`  
**Current subphase:** —  
**Phase status:** In progress — indexing CT-CLIP embeddings in Qdrant, exposing search
(text/CT query) with findings re-ranking + explanations, and replacing the P4 **mock**
GPU worker with a real CT-CLIP inference worker (AUP-005 scope).

**P12 closed:** a deployable retriever was achieved via the **AUP-005 pivot** — CT-CLIP
recall (held-out **R@10 0.511**) + our findings-grounded explainable re-ranking
(0.522 CT→text / 0.533 text→CT). The from-scratch PointNet++ encoder is retained as a
**documented negative result** (five approaches, all 1.0–1.5× random). See
`docs/reports/P12_{EXIT_REPORT,MODEL_CARD}.md` and `docs/architecture/AUP-005_*.md`.
**Completed & merged:** P0–P18 (P18 #19 — backup/restore). P16 dropped (AUP-005)
**Next entry gate:** P13 — P12 approved & merged → Qdrant Index & Real Retrieval

---

## 1. Current authoritative versions

| Document | Version / status |
|---|---|
| Architecture Specification Bundle | v2.4.5 — `final_freeze_candidate` |
| Master Phased AI Execution Plan | v1.0 |
| Implementation Appendix | v1.1 — `implementation_ready` |
| Freeze Test Profile | v1.1 — `ready_for_execution` |
| AI Startup Prompt | v1.0 |

The architecture is not yet marked `frozen`. It becomes frozen only after the mandatory Freeze Run passes and a valid `FREEZE_PASSED` event is recorded.

---

## 2. Project objective

Build a high-quality portfolio project that can continue to be maintained and improved after the first release.

**Target:** a showcase-ready version within one month.  
**Available effort:** more than 25 hours per week.

Priority order:

1. Complete, reliable CT-to-report and report-to-CT retrieval.
2. Professional product-quality frontend.
3. History, export, voice input and bilingual user experience.
4. Text-guided 3D segmentation, provided it does not compromise retrieval quality.

---

## 3. Current phase

### P0 — Specification Lock and Repository Bootstrap

**Status:** ✅ Completed, approved, and merged to `main` (PR #1, squash `83f1adc`, 2026-07-01). Now in **P1 — Local Infrastructure and Developer Experience** (planning).

P0 should begin by:

1. Loading and validating all authoritative documents.
2. Creating the Phase Execution Plan.
3. Locking exact dependency versions and container image digests.
4. Initializing the repository and GitHub Flow.
5. Creating the initial CI pipeline.
6. Creating `PROJECT_STATE.md`, `project_state.json` and the first Phase Exit Report template.
7. Running all P0 tests.
8. Submitting the P0 Pull Request for user review.

The AI may execute P0 after showing its Phase Execution Plan. It must not enter P1 without explicit user approval and merge of the P0 Pull Request.

---

## 4. Development environment

- Windows 11
- WSL2 Ubuntu
- Docker Desktop
- Local-first execution
- Reproducible deployment on other computers using Docker
- Single-user local application
- Public GitHub repository
- MIT license

---

## 5. Git and review workflow

- GitHub Flow
- One branch and Pull Request per Phase
- Subphases execute strictly sequentially
- No parallel Subphase execution
- Every Subphase must be independently tested
- The full Phase is submitted for review only after all Subphases finish
- The user must explicitly approve every Phase
- The corresponding Pull Request must be merged into `main` before the Phase Exit Report becomes effective

Each Phase delivery must contain:

- Complete code
- File-change list
- Run commands
- Test results
- Per-file and key-design explanation
- CI summary
- Known Issues / Test Exceptions Report when applicable
- Suggested commit message
- Pull Request description
- Phase Exit Report
- Updated project state files

---

## 6. Architecture-change rule

When an architecture problem or architecture-document inconsistency is discovered:

```text
Stop the current Phase
→ explain the conflict and impact
→ propose an architecture-document update
→ recommend the appropriate version change
→ wait for user approval
→ update and review the architecture documentation
→ update the Master Plan and implementation specifications
→ only then modify implementation
→ rerun all affected tests
```

Code must never be modified first and documented afterward for architecture-related changes.

---

## 7. Data and model decisions

### Retrieval

> **Superseded in part by AUP-005** — see "Retrieval architecture — AMENDED" below.
> The deployed image encoder is **CT-CLIP (CT-ViT)**, not PointNet++. The original
> targets below are retained as the historical baseline specification.

- Primary dataset: CT-RATE
- External validation: BIMCV-R
- Image encoder: ~~PointNet++~~ → **CT-CLIP CT-ViT** (AUP-005)
- Text encoder: BioClinicalBERT (research track) / CT-CLIP text tower (deployed)
- Embedding size: 512
- CT representation: 32,768 `(x, y, z, density)` points
- Losses:
  - bidirectional CLIP-style contrastive loss
  - auxiliary multi-label classification loss
- Required evaluation:
  - Recall@1, Recall@5, Recall@10
  - mAP
  - nDCG
  - both CT-to-report and report-to-CT retrieval

CT-CLIP code and methodology may be studied, but incompatible CT image-encoder weights must not be loaded into PointNet++.

### Training resources

- Local development and small-subset validation first
- Primary cloud: Google Colab Free
- Backup cloud: Kaggle GPU
- Local storage budget: 100–250 GB

### Segmentation — **DROPPED (P16 removed, AUP-005, 2026-07-20)**

- **No longer required for the final Demo.** Dropped by user decision, consistent with
  its `planned_experimental` status and the recorded rule that retrieval takes priority
  when timing conflicts arise.
- ReXGroundingCT is no longer an acquisition target.
- Its stated design (frozen PointNet++ + text-conditioned 3D head) is moot regardless,
  since PointNet++ is no longer the deployed encoder (see Retrieval below).
- Consequences: no segmentation view (P14), no segmentation artifacts in history/export
  (P15), no segmentation paths in integration (P19) or the freeze profile (P20).

### Retrieval architecture — **AMENDED (AUP-005)**

- **Deployed recall:** CT-CLIP (CT-ViT image tower + text tower), CC-BY-NC-SA,
  local inference ~2.25 GB VRAM. Held-out **R@10 = 0.511** (90 CT-RATE `valid` volumes).
- **Original contribution:** findings-grounded **explainable re-ranking** — reorders the
  top-K by clinical-findings agreement and renders the shared findings as the reason
  ("both show pleural effusion + cardiomegaly"). Best R@10 0.522 (CT→text) / 0.533 (text→CT).
- **Superseded:** the PointNet++ point-cloud encoder (P9/P11/P12a-b) is reclassified as
  **documented research** (honest negative result — five approaches plateaued at
  1.0–1.5× random) and is **removed from the serving path**.
- **Licence obligation:** CT-CLIP + CT-RATE are **CC-BY-NC-SA** → non-commercial only,
  attribution required, derivatives share-alike (enforced in P17).

---

## 8. Product and frontend decisions

- Professional, near-product interface
- AI must first present three visual directions and key-page mockups
- User selects the visual direction before frontend implementation
- Chinese/English interface toggle
- Chinese text input translated locally into English before retrieval
- Lightweight and fast local translation model preferred
- English voice input only
- Single CT upload only
- Three orthogonal views
- WW/WL controls
- Basic 3D volume rendering
- Polygon annotation
- Full history
- PDF and JSON export
- No automatic radiology-report generation
- Display retrieved reports, similarity results and segmentation results

---

## 9. CI and quality gates

Every Phase Pull Request must run:

- Lint
- Type checking
- Unit tests
- Integration tests
- Security scanning
- Dependency vulnerability scanning
- Docker build
- Risk-based coverage checks
- Pull Request test summary
- Downloadable test artifacts

The AI determines whether a test is critical, but must state its reasoning. Architecture consistency, security, data integrity, recovery, core functionality and regression tests are critical by default.

A noncritical failed test is allowed only with a formal Known Issues / Test Exceptions Report that includes:

- Root cause
- Impact
- Risk level
- Temporary mitigation
- Repair plan
- Target Phase

---

## 10. Hard constraints

1. Do not skip or reorder Phases.
2. Do not execute Subphases in parallel.
3. Do not enter the next Phase without user approval.
4. Do not bypass, weaken or delete tests to obtain a pass.
5. Do not fabricate test, training or evaluation results.
6. Do not silently modify architecture-related behavior in code.
7. Update and review the architecture documentation before any architecture-related implementation change.
8. Do not modify database schemas without migrations and documentation.
9. Do not perform irreversible operations without user approval.
10. Do not delete important data or overwrite important files without user approval.
11. Do not merge a Phase Pull Request before required tests pass and the user approves.
12. Record config, seed, code revision and dataset revision for every training run.
13. Record every failure and exception.
14. Treat the approved and merged Phase Exit Report as the authoritative Phase-status record.

---

## 11. Pending implementation decisions

The following are intentionally deferred to their assigned Phases:

- Exact dependency versions and container digests
- Exact Celery and Redis broker settings
- Exact PointNet++ layer architecture
- Training hyperparameters
- Exact lightweight local Chinese-to-English translation model
- Final frontend visual direction

These are not permission to improvise outside the assigned Phase. Each decision must be recorded, tested and reflected in the Phase Exit Report.

---

## 12. State authority and consistency

The authoritative Phase state is the **approved and merged Phase Exit Report**.

Supporting sources:

- Git repository
- CI results
- `PROJECT_STATE.md`
- `project_state.json`

When these disagree:

```text
Stop execution
→ perform a consistency audit
→ report the conflict
→ wait for the user's decision
```

---

## 13. Next action

Start **P0 — Specification Lock and Repository Bootstrap**.

The AI must first generate a P0 Phase Execution Plan. It may then execute all P0 Subphases sequentially, run the P0 tests and submit the complete Phase for review. It must wait for explicit user approval before entering P1.
