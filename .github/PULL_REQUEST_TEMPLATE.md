# Phase P&lt;NN&gt; — &lt;Phase Name&gt;

> One pull request per phase (GitHub Flow). Do not merge until CI is green,
> required tests pass, and the user explicitly approves (Hard Constraint H-15).

## Summary
&lt;what this phase delivers&gt;

## Subphases completed
- [ ] S1 — …
- [ ] S2 — …

## Test summary
| Test | Class | Result |
|---|---|---|
| … | critical / non-critical | passed / failed |

- CI run: &lt;link&gt;
- Coverage (risk-based): &lt;scope + numbers&gt;
- Security scan (gitleaks / bandit / dep-audit): &lt;summary&gt;

## Change log
&lt;added / changed / moved / removed&gt;

## Conformance & deviations
- Clause-level conformance: &lt;link to report&gt;
- Architecture deviation: **none** / **approved (ref)**

## Checklist
- [ ] No restricted data, weights, secrets, or PHI committed (H-13/H-14)
- [ ] `PROJECT_STATE.md` and `project_state.json` updated and consistent
- [ ] Phase Exit Report attached
- [ ] Known Issues report attached (if any non-critical failures)
- [ ] `bash scripts/ci_local.sh` is green locally

## Linked
Closes #&lt;issue&gt; (if any)
