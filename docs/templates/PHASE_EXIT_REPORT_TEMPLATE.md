# Phase Exit Report — P&lt;NN&gt; &lt;Phase Name&gt;

> Authoritative phase record once **approved by the user and merged into `main`**
> (Master Plan §5.3, §10.2). Until then this report is a candidate.

| Field | Value |
|---|---|
| Phase ID / version | P&lt;NN&gt; · report v&lt;x.y&gt; |
| Architecture bundle | v2.4.5 |
| Branch | `phase/P&lt;NN&gt;-&lt;short&gt;` |
| Pull Request | #&lt;id&gt; (&lt;url&gt;) |
| Head commit | `&lt;sha&gt;` |
| Date | &lt;YYYY-MM-DD&gt; |

## 1. Subphase completion

| Subphase | Description | Status | Evidence |
|---|---|---|---|
| S1 | … | ✅ / ❌ | test ids / artifacts |

## 2. File-change summary
&lt;added / modified / moved / deleted, grouped by area&gt;

## 3. Test results & CI evidence

| Test | Class (critical/non-critical) | Result | Basis |
|---|---|---|---|
| … | … | passed/failed | … |

- CI run: &lt;url&gt; · overall: passed/failed
- Coverage: &lt;scope &amp; numbers&gt; (risk-based, justified)
- Security scan: &lt;gitleaks / bandit / dep-audit summary&gt;
- Downloadable artifacts: &lt;links&gt;

## 4. Clause-level conformance
&lt;Reference CONFORMANCE_REPORT for the per-clause table; summarize mandatory
clause coverage %&gt;

## 5. Known issues / test exceptions
&lt;None, or reference KNOWN_ISSUES report&gt;

## 6. Architecture deviation
**none** / **approved** (reference the approval). Must be one of these two.

## 7. State & governance

- `PROJECT_STATE.md` / `project_state.json` updated: ✅
- User approval status: ⬜ pending / ✅ approved
- PR merge status: ⬜ open / ✅ merged
- Next phase entry gate: &lt;condition&gt;

## 8. Suggested commit message & PR description
&lt;included in the PR&gt;
