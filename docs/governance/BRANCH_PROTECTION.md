# Branch Protection Policy — `main`

GitHub Flow with one protected long-lived branch (`main`) and one
branch + pull request per phase (`phase/PXX-...`). This file is the source of
truth for the protection settings to apply on the GitHub remote.

## Required settings for `main`

| Setting | Value |
|---|---|
| Require a pull request before merging | ✅ |
| Required approvals | 1 (maintainer) |
| Dismiss stale approvals on new commits | ✅ |
| Require review from Code Owners | ✅ (CODEOWNERS) |
| Require status checks to pass | ✅ |
| Required status checks | `ci` (the GitHub Actions `ci.yml` workflow) |
| Require branches up to date before merge | ✅ |
| Require conversation resolution | ✅ |
| Require linear history | ✅ |
| Do not allow bypassing the above | ✅ |
| Allow force pushes | ❌ |
| Allow deletions | ❌ |

## Phase merge gate (governance, enforced by review)

A phase PR may be merged only when **all** hold (Hard Constraint H-15):

1. CI is green (all required checks pass).
2. All **critical** tests pass; any non-critical failure has a Known Issues /
   Test Exceptions Report.
3. The Phase Exit Report is attached and complete.
4. `PROJECT_STATE.md` and `project_state.json` are updated and consistent.
5. The user has **explicitly approved**.

## How to apply

Branch protection is configured on the GitHub remote (it cannot be set from the
local working tree). Apply via the GitHub UI
(*Settings → Branches → Add rule*) or with the GitHub CLI once authenticated:

```bash
gh api -X PUT repos/Sir7s/MedicalCLAP/branches/main/protection \
  --input docs/governance/branch_protection.api.json
```

> The protection rule requires `main` to exist on the remote first (created by
> pushing the initial commit). Until then, the policy above is documentary.
