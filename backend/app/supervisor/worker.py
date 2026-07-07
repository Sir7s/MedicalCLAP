"""Mock GPU Worker (P4, SPEC-03 §4.8; IMP-EXEC-010).

A real `multiprocessing` (spawn) child that speaks the two-phase startup
protocol. It simulates the model-execution stages — no real model is loaded
(that is P11+). The worker NEVER writes the database, never acquires a lease,
and never ACKs the queue; it only talks to its supervisor over the pipe.

Child lifecycle (IMP-EXEC-010):
    created -> initializing -> startup_ready -> waiting_for_begin
            -> executing -> stopping/exited

Behaviors (for reliability tests):
- "normal"       full happy path.
- "ignore_stop"  enters the running stage and ignores cooperative stop
                 (forces the supervisor to terminate/kill — FR-EXEC-010).
- "never_ready"  exits without ever sending startup_ready.
"""
from __future__ import annotations

import time
from typing import Any

from .ipc import make_message

STAGES = ("preprocessing", "running", "postprocessing", "finalizing_artifacts")
BEGIN_TIMEOUT_SECONDS = 20.0


def mock_worker_main(
    conn: Any,
    model_job_id: str,
    lease_revision: int,
    nonce: str,
    child_uuid: str,
    behavior: str = "normal",
    begin_timeout: float = BEGIN_TIMEOUT_SECONDS,
) -> None:
    """Child-process entrypoint (top-level so `spawn` can import it)."""
    seq = 0

    def send(msg_type: str, payload: dict | None = None) -> None:
        nonlocal seq
        seq += 1
        conn.send(
            make_message(
                msg_type=msg_type,
                model_job_id=model_job_id,
                lease_revision=lease_revision,
                nonce=nonce,
                child_uuid=child_uuid,
                sequence=seq,
                payload=payload,
            )
        )

    if behavior == "never_ready":
        return  # simulated startup crash: exit before startup_ready

    # Phase 1 — initialization complete; announce readiness and WAIT.
    send("startup_ready")

    # Phase 2 — model work may begin only after the supervisor's durable
    # execution_started commit arrives as begin_execution (IMP-EXEC-011/012).
    if not conn.poll(begin_timeout):
        send("exiting", {"reason": "begin_timeout"})
        return
    first = conn.recv()
    if not isinstance(first, dict) or first.get("type") != "begin_execution":
        send("exiting", {"reason": "unexpected_message"})
        return

    for stage in STAGES:
        if conn.poll(0):
            msg = conn.recv()
            if isinstance(msg, dict) and msg.get("type") == "stop":
                if behavior != "ignore_stop":
                    send("exiting", {"reason": "cooperative_stop"})
                    return
        if behavior == "ignore_stop" and stage == "running":
            # Simulate a wedged kernel: ignore everything until killed.
            while True:
                time.sleep(0.05)
        send("stage", {"stage": stage})

    send("result", {"result": {"mock": True, "scores": [0.91, 0.84, 0.77]}})
    send("exiting", {"reason": "completed"})
