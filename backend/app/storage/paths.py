"""Workspace volume layout (P5, SPEC-04).

Artifact paths embed the lease revision (SPEC-04 §5.3) so a stale supervisor
can never overwrite a newer lease's output:
    {root}/model_jobs/{job_id}/lease-{revision}/...
"""
from __future__ import annotations

import os
from pathlib import Path


def workspace_root() -> Path:
    root = Path(os.environ.get("MEDCLIP_WORKSPACE_ROOT", "./workspace_data")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def workspace_dir(workspace_id: str) -> Path:
    p = workspace_root() / "workspaces" / workspace_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def job_artifact_dir(job_id: str, lease_revision: int) -> Path:
    p = workspace_root() / "model_jobs" / job_id / f"lease-{lease_revision}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def snapshot_dir(save_operation_id: str) -> Path:
    p = workspace_root() / "snapshots" / save_operation_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def filesystem_identity(path: Path) -> str:
    """Stable identity for per-filesystem reservations (IMP-STOR-003)."""
    anchor = Path(path.resolve().anchor or "/")
    return f"fs:{anchor}"
