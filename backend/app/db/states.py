"""Control-plane state machines (P2).

State sets and legal transitions transcribed from Architecture v2.4.5:
- Workspace          SPEC-02 sec 3.3
- Application Task   SPEC-02 sec 3.4
- Task Attempt       SPEC-02 sec 3.4 / SPEC-03 sec 4.4
- Model Job          SPEC-02 sec 3.4
- Command            SPEC-03 sec 4.2

`assert_transition` enforces legality; an illegal transition raises
`IllegalTransition` (used by the repository layer to reject bad writes and by
the freeze-time state-trace validator).
"""
from __future__ import annotations


class IllegalTransition(ValueError):
    """Raised when a state transition is not permitted by the state machine."""


# --- Workspace (SPEC-02 §3.3) ---------------------------------------------
WORKSPACE_STATES = (
    "active", "recovering", "cleanup_pending", "deleted", "error",
)
WORKSPACE_TRANSITIONS: dict[str, set[str]] = {
    "active": {"recovering", "cleanup_pending", "error"},
    "recovering": {"active", "cleanup_pending", "error"},
    "cleanup_pending": {"deleted", "error"},
    "error": {"recovering", "cleanup_pending"},
    "deleted": set(),
}

# --- Application Task (SPEC-02 §3.4) ---------------------------------------
TASK_STATES = (
    "created", "queued", "running", "cancelling",
    "completed", "failed", "cancelled", "discarded",
)
TASK_TRANSITIONS: dict[str, set[str]] = {
    "created": {"queued", "cancelled", "discarded"},
    "queued": {"running", "cancelling", "cancelled", "failed"},
    "running": {"completed", "failed", "cancelling"},
    "cancelling": {"cancelled", "completed", "failed"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
    "discarded": set(),
}

# --- Task Attempt (SPEC-02 §3.4 / SPEC-03 §4.4) ----------------------------
ATTEMPT_STATES = (
    "created", "command_pending", "dispatched", "lease_acquired", "running",
    "committing", "succeeded", "failed_retryable", "failed_final", "cancelled",
)
ATTEMPT_TRANSITIONS: dict[str, set[str]] = {
    "created": {"command_pending", "cancelled"},
    "command_pending": {"dispatched", "failed_retryable", "cancelled"},
    "dispatched": {"lease_acquired", "failed_retryable", "cancelled"},
    "lease_acquired": {"running", "failed_retryable", "cancelled"},
    "running": {"committing", "failed_retryable", "failed_final", "cancelled"},
    "committing": {"succeeded", "failed_retryable", "failed_final"},
    "succeeded": set(),
    "failed_retryable": set(),
    "failed_final": set(),
    "cancelled": set(),
}

# --- Model Job (SPEC-02 §3.4) ----------------------------------------------
MODEL_JOB_STATES = (
    "queued", "leased", "loading_model", "preprocessing", "running",
    "postprocessing", "finalizing_artifacts", "completed", "lease_suspect",
    "takeover_pending", "recovery_required", "cancelling", "cancelled",
    "cancelled_forced", "discarded", "failed",
)
_JOB_INTERRUPTS = {"lease_suspect", "recovery_required", "cancelling", "failed"}
MODEL_JOB_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"leased", "cancelling", "discarded", "failed"},
    "leased": {"loading_model"} | _JOB_INTERRUPTS,
    "loading_model": {"preprocessing"} | _JOB_INTERRUPTS,
    "preprocessing": {"running"} | _JOB_INTERRUPTS,
    "running": {"postprocessing"} | _JOB_INTERRUPTS,
    "postprocessing": {"finalizing_artifacts"} | _JOB_INTERRUPTS,
    "finalizing_artifacts": {"completed"} | _JOB_INTERRUPTS,
    "completed": set(),
    "lease_suspect": {"takeover_pending", "recovery_required", "failed"},
    "takeover_pending": {"leased", "recovery_required", "failed"},
    "recovery_required": {"queued", "discarded", "failed"},
    "cancelling": {"cancelled", "cancelled_forced", "failed"},
    "cancelled": set(),
    "cancelled_forced": set(),
    "discarded": set(),
    "failed": set(),
}

# --- Command (SPEC-03 §4.2) ------------------------------------------------
COMMAND_STATES = (
    "pending", "dispatching", "dispatched", "worker_received", "lease_acquired",
    "execution_started", "resolved", "failed_retryable", "failed_final",
    "cancelled", "superseded",
)
_CMD_EXC = {"failed_retryable", "cancelled", "superseded"}
COMMAND_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"dispatching"} | {"cancelled", "superseded"},
    "dispatching": {"dispatched"} | _CMD_EXC,
    "dispatched": {"worker_received"} | _CMD_EXC,
    "worker_received": {"lease_acquired"} | _CMD_EXC,
    "lease_acquired": {"execution_started"} | _CMD_EXC,
    "execution_started": {"resolved", "failed_retryable", "failed_final", "cancelled"},
    "resolved": set(),
    "failed_retryable": {"dispatching", "failed_final", "cancelled", "superseded"},
    "failed_final": set(),
    "cancelled": set(),
    "superseded": set(),
}

COMMAND_RESOLUTION_TYPES = ("succeeded", "cancelled", "discarded", "failed")
DEAD_LETTER_RESOLUTIONS = (
    "unresolved", "acknowledged", "replayed", "discarded", "resolved",
)

_MACHINES: dict[str, dict[str, set[str]]] = {
    "workspace": WORKSPACE_TRANSITIONS,
    "task": TASK_TRANSITIONS,
    "attempt": ATTEMPT_TRANSITIONS,
    "model_job": MODEL_JOB_TRANSITIONS,
    "command": COMMAND_TRANSITIONS,
}


def transitions_for(machine: str) -> dict[str, set[str]]:
    if machine not in _MACHINES:
        raise KeyError(f"unknown state machine: {machine}")
    return _MACHINES[machine]


def is_terminal(machine: str, state: str) -> bool:
    return len(transitions_for(machine).get(state, set())) == 0


def can_transition(machine: str, src: str, dst: str) -> bool:
    table = transitions_for(machine)
    if src not in table:
        raise IllegalTransition(f"{machine}: unknown source state {src!r}")
    if dst not in table:
        raise IllegalTransition(f"{machine}: unknown target state {dst!r}")
    return dst in table[src]


def assert_transition(machine: str, src: str, dst: str) -> None:
    if not can_transition(machine, src, dst):
        raise IllegalTransition(f"{machine}: illegal transition {src!r} -> {dst!r}")
