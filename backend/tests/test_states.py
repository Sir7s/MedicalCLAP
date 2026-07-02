"""P2 unit tests — state machine legality (no DB)."""
from __future__ import annotations

import pytest

from app.db import states


def test_legal_transition():
    states.assert_transition("task", "created", "queued")
    states.assert_transition("command", "pending", "dispatching")
    states.assert_transition("model_job", "leased", "loading_model")


def test_illegal_transition_raises():
    with pytest.raises(states.IllegalTransition):
        states.assert_transition("task", "created", "completed")
    with pytest.raises(states.IllegalTransition):
        states.assert_transition("command", "resolved", "pending")  # terminal


def test_unknown_state_raises():
    with pytest.raises(states.IllegalTransition):
        states.assert_transition("task", "bogus", "queued")


def test_terminal_detection():
    assert states.is_terminal("task", "completed")
    assert states.is_terminal("command", "resolved")
    assert not states.is_terminal("task", "created")


@pytest.mark.parametrize("machine", ["workspace", "task", "attempt", "model_job", "command"])
def test_transition_targets_are_known_states(machine):
    """Every transition target must itself be a declared state (no typos)."""
    table = states.transitions_for(machine)
    known = set(table)
    for src, targets in table.items():
        for dst in targets:
            assert dst in known, f"{machine}: {src} -> {dst} targets unknown state"


def test_every_state_has_transition_entry():
    """State tuples and transition tables must agree."""
    pairs = [
        (states.WORKSPACE_STATES, states.WORKSPACE_TRANSITIONS),
        (states.TASK_STATES, states.TASK_TRANSITIONS),
        (states.ATTEMPT_STATES, states.ATTEMPT_TRANSITIONS),
        (states.MODEL_JOB_STATES, states.MODEL_JOB_TRANSITIONS),
        (states.COMMAND_STATES, states.COMMAND_TRANSITIONS),
    ]
    for state_tuple, table in pairs:
        assert set(state_tuple) == set(table)
