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
    """The current phase and active branch in JSON must be reflected in the MD."""
    s = _state()
    md = _md()
    assert s["current_phase"] in md, "current_phase must appear in PROJECT_STATE.md"
    assert s["active_branch"] in md, "active_branch must appear in PROJECT_STATE.md"


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


def test_current_phase_not_also_completed():
    """A phase cannot be simultaneously 'current' and already completed."""
    s = _state()
    assert s["current_phase"] not in s["completed_phases"]


def test_completion_and_approval_records_consistent():
    """If any phase is completed, an approved exit report must be recorded; and
    completed/approved lists must not disagree."""
    s = _state()
    completed = s["completed_phases"]
    approved = s.get("approved_phases", [])
    if completed:
        assert s["last_approved_exit_report"], (
            "completed phases require a recorded last_approved_exit_report"
        )
        # every completed phase must also be approved (approval precedes merge)
        for ph in completed:
            assert ph in approved, f"completed phase {ph} missing from approved_phases"
    else:
        assert s["last_approved_exit_report"] is None


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
