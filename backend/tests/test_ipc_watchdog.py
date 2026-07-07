"""P4 unit tests — IPC nonce/sequence validation and stage watchdog (no DB)."""
from __future__ import annotations

from app.supervisor.ipc import IpcValidator, make_message, new_child_identity, nonce_hash
from app.supervisor.watchdog import StageWatch, watch_for


def _msg(v: IpcValidator, seq: int, **over) -> dict:
    base = make_message(
        msg_type="stage",
        model_job_id=v.model_job_id,
        lease_revision=v.lease_revision,
        nonce=v.nonce,
        child_uuid=v.child_uuid,
        sequence=seq,
        payload={"stage": "running"},
    )
    base.update(over)
    return base


def _validator() -> IpcValidator:
    nonce, child = new_child_identity()
    return IpcValidator(model_job_id="job-1", lease_revision=3, nonce=nonce, child_uuid=child)


def test_valid_message_accepted_and_sequence_advances():
    v = _validator()
    ok, _ = v.validate(_msg(v, 1))
    assert ok and v.last_sequence == 1
    ok, _ = v.validate(_msg(v, 2))
    assert ok and v.last_sequence == 2


def test_nonce_replay_rejected():
    """FR-EXEC-012: a message carrying an older child's nonce is rejected."""
    v = _validator()
    old_nonce, _ = new_child_identity()  # a different (stale) nonce
    ok, reason = v.validate(_msg(v, 1, worker_startup_nonce=old_nonce))
    assert not ok and reason == "nonce_mismatch"


def test_sequence_replay_rejected():
    v = _validator()
    assert v.validate(_msg(v, 1))[0]
    assert v.validate(_msg(v, 2))[0]
    ok, reason = v.validate(_msg(v, 2))  # replayed sequence
    assert not ok and reason == "sequence_not_monotonic"


def test_lease_revision_mismatch_rejected():
    v = _validator()
    ok, reason = v.validate(_msg(v, 1, execution_lease_revision=99))
    assert not ok and reason == "lease_revision_mismatch"


def test_child_uuid_mismatch_rejected():
    v = _validator()
    ok, reason = v.validate(_msg(v, 1, child_process_uuid="other-child"))
    assert not ok and reason == "child_uuid_mismatch"


def test_reject_threshold_flags_termination():
    v = _validator()
    for i in range(v.reject_threshold):
        v.validate(_msg(v, i + 1, worker_startup_nonce="bad"))
    assert v.should_terminate_child


def test_nonce_hash_is_sha256_and_stable():
    h = nonce_hash("abc")
    assert len(h) == 64 and h == nonce_hash("abc")


# --- watchdog (FR-EXEC-009 semantics, unit level) ---------------------------

def test_long_stage_with_progress_not_killed():
    w = StageWatch(stage="preprocessing", policy="progress_and_deadline",
                   deadline_seconds=100.0, progress_timeout_seconds=1.0)
    w.started_at = 0.0
    w.last_progress_at = 49.5  # kept reporting progress
    assert w.check(now=50.0) == "ok"


def test_stalled_stage_detected():
    w = StageWatch(stage="preprocessing", policy="progress_and_deadline",
                   deadline_seconds=100.0, progress_timeout_seconds=1.0)
    w.started_at = 0.0
    w.last_progress_at = 10.0
    assert w.check(now=20.0) == "progress_stalled"


def test_hard_deadline_enforced_even_with_progress():
    w = StageWatch(stage="running", policy="deadline_only", deadline_seconds=30.0)
    w.started_at = 0.0
    w.last_progress_at = 29.9
    assert w.check(now=31.0) == "deadline_exceeded"


def test_deadline_only_ignores_progress_silence():
    w = watch_for("running", deadline_seconds=30.0, progress_timeout_seconds=1.0)
    w.started_at = 0.0
    w.last_progress_at = 0.0
    assert w.policy == "deadline_only"
    assert w.check(now=20.0) == "ok"  # silent but within deadline
