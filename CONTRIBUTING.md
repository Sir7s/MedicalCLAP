# Contributing & Execution Protocol

This repository follows a **strict phased execution contract** defined by the
authoritative documents in [`docs/specs/`](docs/specs/). Contributions must
respect it.

## Golden rules (Hard Constraints)

1. **Do not skip, reorder, or pre-implement future phases** (H-01).
2. **Do not fabricate** command output, test results, coverage, or metrics (H-02).
3. **Do not weaken/skip/delete tests** to force a pass (H-03).
4. **Do not fix an architecture problem in code first.** Architecture issues
   trigger the Architecture Update Flow (update the spec → review → user
   approval → then implementation) (H-04, Architecture v2.4.5 §14.2).
5. **Never commit** restricted datasets, model weights, PHI, secrets, or tokens
   (H-13, H-14).
6. **No irreversible data deletion / overwrite** without user approval (H-06).

## Workflow (GitHub Flow, one branch per phase)

```
main
 └── phase/PXX-short-name
       └── Pull Request → CI green → user approval → merge to main
```

- Subphases execute **strictly sequentially**, never in parallel.
- Each subphase is independently tested with saved evidence.
- A phase is submitted for review only after **all** subphases finish.
- The merged, approved **Phase Exit Report** is the authoritative phase record.

## Before opening a PR

```bash
bash scripts/ci_local.sh   # must be green
```

Every phase PR must include: test summary, change log, execution report,
updated `PROJECT_STATE.*`, and a Phase Exit Report
(template in [`docs/templates/`](docs/templates/)).

## Branch / commit conventions

- Branch: `phase/PXX-short-name` (e.g. `phase/P0-bootstrap`).
- Commits: imperative mood, reference the subphase where useful
  (e.g. `P0/S1: lock spec manifest`).

## Security

See [`SECURITY.md`](SECURITY.md). Report suspected secret/PHI exposure before
anything else.
