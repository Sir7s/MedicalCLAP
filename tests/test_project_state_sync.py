"""P0 critical test — PROJECT_STATE consistency.

Criticality: CRITICAL (state-authority class, Master Plan sec 12 / PROJECT_STATE
sec 12). PROJECT_STATE.md and project_state.json must never disagree on the
core phase facts; a mismatch must trigger a consistency audit, so CI fails fast.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = REPO_ROOT / "project_state.json"
MD_PATH = REPO_ROOT / "PROJECT_STATE.md"


def _state() -> dict:
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def _md() -> str:
    return MD_PATH.read_text(encoding="utf-8")


def test_both_state_files_exist():
    assert JSON_PATH.is_file() and MD_PATH.is_file()


def test_required_section_10_1_fields_present():
    """Master Plan sec 10.1 required PROJECT_STATE fields."""
    s = _state()
    for key in [
        "architecture_version",
        "master_plan_version",
        "current_phase",
        "current_subphase",
        "completed_phases",
        "active_branch",
        "last_approved_exit_report",
        "critical_tests",
        "known_issues" if "known_issues" in s else "current_known_issues",
        "pending_decisions",
        "next_entry_gate",
    ]:
        assert key in s, f"missing required PROJECT_STATE field: {key}"


def test_phase_agrees_across_files():
    s = _state()
    md = _md()
    assert s["current_phase"] == "P0"
    assert "P0" in md
    # active branch in json must be mentioned in the markdown
    assert s["active_branch"] == "phase/P0-bootstrap"
    assert "phase/P0-bootstrap" in md


def test_versions_agree_across_files():
    s = _state()
    md = _md()
    assert s["architecture_version"] == "2.4.5"
    assert re.search(r"2\.4\.5", md)
    assert s["master_plan_version"] == "1.0"


def test_repository_consistent():
    s = _state()
    assert s.get("repository") == "Sir7s/MedicalCLAP"
    assert "Sir7s/MedicalCLAP" in _md()


def test_phase_not_marked_complete_before_approval():
    """Guard: P0 must not be in completed/approved lists until merged & approved."""
    s = _state()
    assert "P0" not in s["completed_phases"]
    assert "P0" not in s.get("approved_phases", [])
    assert s["last_approved_exit_report"] is None


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
