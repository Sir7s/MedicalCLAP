"""P18 — backup integrity, corruption detection, and restore refusal.

Runs in CI without Postgres/Qdrant: those components degrade to `skipped` and the
manifest records why, which is itself part of the contract being tested.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import backup  # noqa: E402


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace_data"
    (root / "ws-1").mkdir(parents=True)
    (root / "ws-1" / "artifact.bin").write_bytes(b"chunk-payload" * 100)
    (root / "ws-1" / "notes.json").write_text('{"k": "v"}', encoding="utf-8")
    return root


def test_create_produces_verifiable_backup(tmp_path, workspace):
    target = backup.create_backup(tmp_path / "out", workspace_root=workspace)
    assert (target / backup.MANIFEST).is_file()
    result = backup.verify_backup(target)
    assert result["ok"], result["problems"]
    assert result["checked"] >= 1          # the workspace archive at minimum


def test_workspace_contents_round_trip(tmp_path, workspace):
    import tarfile
    target = backup.create_backup(tmp_path / "out", workspace_root=workspace)
    with tarfile.open(target / backup.WORKSPACE_TAR, "r:gz") as tar:
        names = tar.getnames()
    assert any(n.endswith("artifact.bin") for n in names)
    assert any(n.endswith("notes.json") for n in names)


def test_verify_detects_corruption(tmp_path, workspace):
    target = backup.create_backup(tmp_path / "out", workspace_root=workspace)
    tar_path = target / backup.WORKSPACE_TAR
    data = bytearray(tar_path.read_bytes())
    data[-1] ^= 0xFF                        # flip a bit: same size, different bytes
    tar_path.write_bytes(bytes(data))

    result = backup.verify_backup(target)
    assert not result["ok"]
    assert any("checksum" in p for p in result["problems"])


def test_verify_detects_missing_file(tmp_path, workspace):
    target = backup.create_backup(tmp_path / "out", workspace_root=workspace)
    (target / backup.WORKSPACE_TAR).unlink()
    result = backup.verify_backup(target)
    assert not result["ok"]
    assert any("missing" in p for p in result["problems"])


def test_restore_refuses_corrupt_backup(tmp_path, workspace):
    """A bad restore is worse than no restore — it must refuse, loudly."""
    target = backup.create_backup(tmp_path / "out", workspace_root=workspace)
    tar_path = target / backup.WORKSPACE_TAR
    data = bytearray(tar_path.read_bytes())
    data[-1] ^= 0xFF
    tar_path.write_bytes(bytes(data))

    with pytest.raises(SystemExit):
        backup.restore_backup(target, confirm=True)


def test_restore_dry_run_reports_plan_without_touching_anything(tmp_path, workspace):
    target = backup.create_backup(tmp_path / "out", workspace_root=workspace)
    plan = backup.restore_backup(target, confirm=False)
    assert plan["dry_run"] is True
    assert "workspace" in plan["restore"]
    assert "ct-clip-checkpoint" in plan["refetch"]   # large asset is re-fetched, not unpacked


def test_manifest_records_external_artifact_provenance(tmp_path, workspace):
    """The 1.7 GB checkpoint is not copied; the backup must still make it restorable."""
    target = backup.create_backup(tmp_path / "out", workspace_root=workspace)
    manifest = json.loads((target / backup.MANIFEST).read_text(encoding="utf-8"))
    ext = {a["name"]: a for a in manifest["external_artifacts"]}
    ck = ext["ct-clip-checkpoint"]
    assert ck["source"].startswith("https://")
    assert "CC-BY-NC-SA" in ck["licence"]     # licence-aware: not redistributed
    assert ck["restore"]


def test_unavailable_components_are_recorded_not_silently_dropped(tmp_path, workspace):
    """Postgres/Qdrant are absent in CI; the manifest must say so with a reason."""
    target = backup.create_backup(tmp_path / "out", workspace_root=workspace)
    manifest = json.loads((target / backup.MANIFEST).read_text(encoding="utf-8"))
    by_name = {c["name"]: c for c in manifest["components"]}
    assert set(by_name) == {"postgres", "workspace", "qdrant"}
    for name in ("postgres", "qdrant"):
        comp = by_name[name]
        if comp["status"] != "ok":
            assert comp.get("note"), f"{name} was skipped without recording why"


def test_missing_workspace_is_skipped_with_reason(tmp_path):
    target = backup.create_backup(tmp_path / "out", workspace_root=tmp_path / "nope")
    manifest = json.loads((target / backup.MANIFEST).read_text(encoding="utf-8"))
    ws = next(c for c in manifest["components"] if c["name"] == "workspace")
    assert ws["status"] == "skipped" and ws["note"]
