# Implementation Conformance Report — P1

Per Implementation Appendix v1.1 **IMP-GOV-001/002**.

## Scope statement
P1 delivers local infrastructure and developer experience. It stands up the
Architecture SPEC-01 §2.4–2.5 service topology (postgres, redis, qdrant,
backend, frontend) and enforces the SPEC-08 §9.1 network-boundary requirement
(all services bound to `127.0.0.1`). It introduces **no** runtime control-plane
behavior, so the mandatory implementation clauses `IMP-EXEC-*`, `IMP-HIST-*`,
`IMP-STOR-*`, `IMP-BACK-*`, `IMP-DATA-*` remain **`not_applicable`** to P1 and
are scheduled for P2–P18.

## Summary
| Metric | Value |
|---|---|
| Mandatory clauses in P1 scope | 0 new (governance machinery from P0 in force) |
| Architecture requirements satisfied | SPEC-01 topology, SPEC-08 §9.1 loopback binding |
| Deviations | 0 |
| In-scope coverage | 100% |

## Architecture-requirement evidence (P1)
```json
[
  {
    "requirement": "SPEC-01 §2.5 service topology (postgres/redis/qdrant/backend/frontend)",
    "status": "implemented",
    "evidence": {
      "config_paths": ["infra/docker-compose.yml"],
      "test_ids": ["tests/infra/test_datastores.py", "tests/infra/test_backend_crossservice.py"]
    }
  },
  {
    "requirement": "SPEC-08 §9.1 services bind to 127.0.0.1; datastores not publicly exposed",
    "status": "implemented",
    "evidence": {
      "config_paths": ["infra/docker-compose.yml"],
      "test_ids": ["tests/infra/test_datastores.py::test_datastore_port_reachable_on_loopback"]
    }
  },
  {
    "requirement": "Reproducibility — images pinned by digest",
    "status": "implemented",
    "evidence": {
      "config_paths": ["infra/docker-compose.yml", "backend/Dockerfile", "frontend/Dockerfile"],
      "config_refs": ["docs/specs/VERSION_LOCK.md"]
    }
  }
]
```

## Deferred mandatory clauses (not_applicable in P1)
`IMP-EXEC-*`, `IMP-HIST-*`, `IMP-STOR-*`, `IMP-BACK-*`, `IMP-DATA-*` — reported
with full evidence in the phases that implement them; all must be `implemented`
(or approved deviation) before the P20 Freeze Run.
