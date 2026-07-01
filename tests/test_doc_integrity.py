"""P0 critical test — authoritative document integrity.

Criticality: CRITICAL (architecture-consistency class, Master Plan sec 6).
A drift between an on-disk authoritative document and the locked
SPEC_MANIFEST.json must fail CI and force the Architecture Update Flow
(Architecture v2.4.5 sec 14.2) instead of a silent edit (Hard Constraint H-04).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import spec_manifest  # noqa: E402

MANIFEST_PATH = REPO_ROOT / "docs" / "specs" / "SPEC_MANIFEST.json"


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_exists():
    assert MANIFEST_PATH.is_file(), "SPEC_MANIFEST.json must exist after P0/S1"


def test_all_four_authoritative_documents_present():
    docs = _manifest()["documents"]
    ids = {d["spec_id"] for d in docs}
    assert ids == {"DOC-ARCH", "DOC-MASTER", "DOC-APPENDIX", "DOC-FREEZE"}
    for d in docs:
        assert (REPO_ROOT / d["path"]).is_file(), f"missing document file: {d['path']}"


def test_no_document_hash_drift():
    problems = spec_manifest.check_manifest()
    assert not problems, "specification lock drift detected:\n" + "\n".join(problems)


def test_documents_root_hash_matches_normative_form():
    manifest = _manifest()
    recomputed = spec_manifest.bundle_root_hash(manifest["documents"])
    assert recomputed == manifest["documents_root_sha256"]


def test_locked_versions_match_project_state():
    """The locked doc versions must agree with project_state.json."""
    manifest = _manifest()
    state = json.loads((REPO_ROOT / "project_state.json").read_text(encoding="utf-8"))
    by_id = {d["spec_id"]: d["version"] for d in manifest["documents"]}
    assert by_id["DOC-ARCH"] == state["architecture"]["bundle_version"]
    gov = state["execution_governance"]
    assert by_id["DOC-MASTER"] == gov["master_plan_version"]
    assert by_id["DOC-APPENDIX"] == gov["implementation_appendix_version"]
    assert by_id["DOC-FREEZE"] == gov["freeze_test_profile_version"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
