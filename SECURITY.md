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

## Reporting

This is a personal portfolio project. If you discover a secret or PHI exposure
in the repository history, open a **private** report to the maintainer
(`Maxqiuh@gmail.com`) rather than a public issue, and do not include the exposed
material in the report.
