"""Stage watchdog + forced termination (P4, SPEC-03 §4.9/§4.10).

Watchdog policies per stage:
    preprocessing        progress_and_deadline
    retrieval inference  deadline_only
    segmentation loop    progress_and_deadline
    qdrant query         external_health_check
    artifact finalize    progress_and_deadline

A legitimately long stage that keeps reporting progress is NOT killed
(FR-EXEC-009); a stage that exceeds its hard deadline, or goes silent past its
progress timeout, is.

Forced termination ladder (SPEC-03 §4.10):
    cooperative stop -> grace -> terminate -> grace -> kill -> join
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

STAGE_POLICIES: dict[str, str] = {
    "preprocessing": "progress_and_deadline",
    "running": "deadline_only",  # retrieval inference
    "segmentation": "progress_and_deadline",
    "qdrant_query": "external_health_check",
    "finalizing_artifacts": "progress_and_deadline",
}


@dataclass
class StageWatch:
    """Deadline/progress tracking for one execution stage."""

    stage: str
    policy: str
    deadline_seconds: float
    progress_timeout_seconds: float | None = None
    started_at: float = field(default_factory=time.monotonic)
    last_progress_at: float = field(default_factory=time.monotonic)

    def progress(self) -> None:
        self.last_progress_at = time.monotonic()

    def check(self, now: float | None = None) -> str:
        """Returns 'ok', 'deadline_exceeded', or 'progress_stalled'."""
        now = time.monotonic() if now is None else now
        if now - self.started_at > self.deadline_seconds:
            return "deadline_exceeded"
        if (
            self.policy == "progress_and_deadline"
            and self.progress_timeout_seconds is not None
            and now - self.last_progress_at > self.progress_timeout_seconds
        ):
            return "progress_stalled"
        return "ok"


def watch_for(
    stage: str, *, deadline_seconds: float, progress_timeout_seconds: float | None = None
) -> StageWatch:
    policy = STAGE_POLICIES.get(stage, "deadline_only")
    return StageWatch(
        stage=stage,
        policy=policy,
        deadline_seconds=deadline_seconds,
        progress_timeout_seconds=progress_timeout_seconds,
    )


def forced_terminate(handle, *, stop_grace: float = 1.0, term_grace: float = 1.0) -> dict:
    """Escalating termination of a worker process (SPEC-03 §4.10).

    `handle` is a WorkerHandle (process + conn). Returns a summary of the
    escalation actually needed — evidence for FR-EXEC-010.
    """
    proc = handle.process
    summary = {"cooperative": False, "terminated": False, "killed": False}

    # 1) cooperative stop
    try:
        handle.conn.send({"type": "stop"})
    except (BrokenPipeError, OSError):
        pass
    proc.join(timeout=stop_grace)
    if not proc.is_alive():
        summary["cooperative"] = True
        return summary

    # 2) terminate
    proc.terminate()
    summary["terminated"] = True
    proc.join(timeout=term_grace)
    if not proc.is_alive():
        return summary

    # 3) kill
    proc.kill()
    summary["killed"] = True
    proc.join(timeout=5.0)
    return summary
