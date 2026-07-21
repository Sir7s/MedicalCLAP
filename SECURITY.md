# Security Policy

## Scope

3D Medical CLIP is a **single-user, local-first research prototype**. It is not
a clinical system. Security hardening is delivered progressively, with the
formal baseline established in **P17 — Security, Privacy & Public Repository
Hardening** (Architecture v2.4.5 SPEC-08).

## Baseline guarantees (target)

- All services bind to `127.0.0.1`; PostgreSQL/Redis/Qdrant are never exposed
  on a public interface.
- Host-header, Origin, and forwarded-header validation; DNS-rebinding protection.
- One-time bootstrap nonce; HttpOnly + SameSite=Strict session cookie; CSRF tokens.
- Admin token created via CLI, stored `600`, never logged or sent to the frontend.

## Never commit

- Restricted datasets (CT-RATE, ReXGroundingCT, BIMCV-R) or any PHI.
- Model weights / checkpoints.
- Secrets, API tokens, cookies, `.env` files, or un-sanitized reports.

These are blocked by `.gitignore`, scanned in CI (gitleaks), and asserted by
`tests/test_repo_structure.py`.

---

## Delivered posture (P17)

### Supply chain
- **Secret scanning** (gitleaks) on every push; **SAST** (bandit `-ll` over
  `scripts` and `backend/app`); **dependency audit** (pip-audit) across
  `requirements-dev.txt`, `backend/requirements.txt` and `ml/requirements.txt`.
- Container images are pinned by **digest**, not tag.

### Data handling
- **No PHI is processed.** CT-RATE is de-identified public research data. The system
  neither ingests nor stores identifiers.
- **Model weights and datasets are never committed.** The CT-CLIP checkpoint
  (~1.7 GB), embedding caches and training runs live outside the repository and are
  git-ignored; CI asserts nothing sensitive is tracked.
- **Exports are user-scoped.** History exports contain only the user's own saved
  searches, and every exported file embeds the research-use disclaimer.
- **CSV exports are injection-hardened** — cells beginning `=`, `+`, `-` or `@` are
  escaped so spreadsheets treat radiology text as data, not formulas (P15).

### Network exposure
- All services bind to `127.0.0.1` (compose publishes loopback-only ports).
- The CT-CLIP inference service listens on loopback and is reachable only by the
  backend. It performs no authentication because it is not network-reachable —
  **do not expose it on a public interface.**

### Failure behaviour
- If the inference service is unavailable the API returns **503**; it never returns
  fabricated or silently degraded retrieval results.

### Third-party licence compliance
The deployed stack includes **CC-BY-NC-SA** components (CT-CLIP, CT-RATE), making the
running system **non-commercial**, attribution-bearing and share-alike. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Known limitations (honest)
- Authentication, CSRF and the bootstrap-nonce flow described above are **targets**,
  not yet implemented: the app is a single-user local prototype and currently has no
  auth layer. Do not deploy it on a shared or public host.
- Not a medical device; no clinical validation.
- **SAST debt in research code.** The CI gate scans the serving path (`scripts`,
  `backend/app`) and is clean. The `ml/` research and training code carries 17 medium
  bandit findings — `torch.load` without `weights_only=True` and Hugging Face downloads
  without a pinned revision. That code is not part of the deployed system and runs
  against the operator's own checkpoints, but loading an untrusted checkpoint with it
  would be unsafe. Recorded at freeze; see
  [P20_FREEZE_RUN.md](docs/reports/P20_FREEZE_RUN.md) §6.

## Reporting

This is a personal portfolio project. If you discover a secret or PHI exposure
in the repository history, open a **private** report to the maintainer
(`Maxqiuh@gmail.com`) rather than a public issue, and do not include the exposed
material in the report.
