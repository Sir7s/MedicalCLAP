# Implementation Conformance Report — P&lt;NN&gt;

> Per Implementation Appendix v1.1 **IMP-GOV-001/002**: report every mandatory
> clause individually with evidence — never mark a whole spec "implemented" in
> bulk. Before the Freeze Run, all mandatory clauses must be `implemented`
> (or have an approved, non-security-weakening `deviation_approved`).

## Summary

| Metric | Value |
|---|---|
| Mandatory clauses in scope this phase | &lt;n&gt; |
| Implemented | &lt;n&gt; |
| Partially implemented | &lt;n&gt; |
| Not implemented | &lt;n&gt; |
| Not applicable (justified) | &lt;n&gt; |
| Deviation approved | &lt;n&gt; |
| Mandatory clause coverage | &lt;%&gt; |

## Per-clause evidence

Each clause as a JSON record (IMP-GOV-001 shape):

```json
{
  "clause_id": "IMP-EXEC-010",
  "status": "implemented",
  "evidence": {
    "code_paths": [],
    "test_ids": [],
    "migration_ids": [],
    "config_paths": []
  },
  "deviation": null
}
```

Status values: `implemented` · `partially_implemented` · `not_implemented` ·
`not_applicable` · `deviation_approved`.

## Notes

- Clauses with no applicable dynamic test must cite static analysis, migration,
  or code-review evidence (Freeze Profile §8).
- Security-critical clauses may **not** be satisfied via deviation.
