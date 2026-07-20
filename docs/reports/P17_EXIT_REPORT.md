# Phase Exit Report — P17 · Security, Privacy & Public Repository Hardening

> **Status: COMPLETE — auto-merge on green CI.**

| Field | Value |
|---|---|
| Phase ID | P17 · report v1.0 |
| Branch | `phase/P17-security` |
| Date | 2026-07-21 |
| Prerequisite | P15 merged (P16 dropped, AUP-005) |

## 1. Objective (met)
Make the repository safe to be public and make its licensing **honest**, now that the
deployed stack depends on third-party components with terms stricter than our own.

## 2. The material finding: a licence mismatch
The repository is MIT. The **deployed retrieval stack depends on CT-CLIP and CT-RATE,
both CC-BY-NC-SA 4.0** — non-commercial, attribution, share-alike. Publishing an
MIT-badged repo without stating this would imply commercial rights the project cannot
grant. Resolved as follows:

- **MIT still covers our source code** — that is accurate and unchanged.
- **README now carries an explicit non-commercial warning** stating that running the
  system with CT-CLIP/CT-RATE is non-commercial only, and that MIT cannot grant
  rights over third-party assets.
- **`THIRD_PARTY_NOTICES.md`** documents every third-party model, dataset and key
  library with its licence, plus the required CT-RATE/CT-CLIP citation.
- **Nothing third-party is redistributed** — weights and datasets are downloaded by
  the user and git-ignored, which keeps the repository itself clean.

## 3. Deliverables
- **`THIRD_PARTY_NOTICES.md`** — per-component licences (CT-CLIP CC-BY-NC-SA,
  CT-RATE CC-BY-NC-SA, CT-FM MIT, BiomedVLP-CXR-BERT MSR, Whisper/Argos MIT, and the
  library set), the non-commercial warning, and the citation block.
- **`README.md`** — corrected licence section + tightened data/privacy statement.
- **`SECURITY.md`** — delivered posture: supply chain (gitleaks, bandit, pip-audit,
  digest-pinned images), data handling (no PHI, no committed weights/data, CSV
  injection hardening), network exposure (loopback-only; the CT-CLIP service must not
  be exposed), failure behaviour (503, never fabricated results), and licence
  compliance — plus an explicit **Known limitations** section.
- **`tests/test_security_hardening.py`** — 9 CI-enforced assertions.

## 4. Honesty note (deliberate)
`SECURITY.md` previously described auth, CSRF and bootstrap-nonce protections as
baseline guarantees. Those are **targets, not implemented** — the app is a single-user
local prototype with no auth layer. The policy now says so plainly and warns against
deploying on a shared host, and a test asserts that admission stays in the document.
Overstating security posture on a public medical-adjacent repo would be worse than
having the gap.

## 5. Exit-gate evidence
- **Hardening tests (9, CI):** no weights (`.pt/.pth/.ckpt/.onnx/.safetensors/.bin`),
  no medical volumes or caches (`.nii/.nii.gz/.dcm/.npz/.npy`), no `.env`/secret/key
  files (except `infra/.env.example`), no `runs/` or `data/ct_rate/` artifacts
  tracked; third-party notices exist and name the restricted components; README
  declares the non-commercial restriction; SECURITY.md documents data/network posture
  and admits the missing auth; the UI carries a research-use disclaimer.
- **bandit** `-ll` over `scripts` + `backend/app`: clean.
- **pip-audit** across all three requirement files: clean (CI).
- **gitleaks**: clean (CI). ruff clean; governance suite green.

## 6. Known limitations
- No authentication/CSRF layer yet (recorded above and in `SECURITY.md`).
- The CT-CLIP inference service is unauthenticated by design and must remain
  loopback-only.

## 7. Governance
`PROJECT_STATE.*` updated. Unlocks **P18** — Backup, Restore & Failure Recovery.
