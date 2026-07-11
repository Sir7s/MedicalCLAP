# Implementation Conformance Report — P9

Per IMP-GOV-001/002; Architecture SPEC-07 §8.2 / §8.5.

| Spec | Requirement | Status | Evidence |
|---|---|---|---|
| SPEC-07 §8.2 | 32,768 (x,y,z,density) points | implemented | `config.N_POINTS`; exact-count test |
| SPEC-07 §8.2 | Sampling 50% body / 25% high-gradient / 25% global | implemented | `ct_pointcloud._sample`; ratio test |
| SPEC-07 §8.2 | Encoder input geometry (coords normalized) | implemented | coords→[-1,1], density→[0,1]; range test |
| SPEC-07 §8.5 | Orientation/affine priority | implemented | `as_closest_canonical` → RAS |
| SPEC-07 §8.5 | Resampling spacing + interpolation | implemented | isotropic 2mm, trilinear; spacing tests |
| SPEC-07 §8.5 | HU range + normalization + body mask + gradient | implemented | `_normalize_density`, `_body_mask`, `_gradient_magnitude` |
| SPEC-07 §8.5 | Point sampling + seed + coordinate normalization | implemented | seeded RNG; determinism test |
| SPEC-07 §8.5 | Library versions + precision policy | implemented | `manifest.build_manifest` |
| P9 gate | Determinism / no NaN-Inf / traceable manifest | implemented | 8 tests; real-CT verification |

Deterministic (seeded) throughout; container digest binding is recorded when the
preprocessing runs inside the model worker (P11+). In-scope coverage 100%;
deviations 0.
