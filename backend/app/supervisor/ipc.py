"""GPU worker IPC protocol + startup-nonce validation (P4, IMP-EXEC-008/009).

Every child→supervisor message must carry the exact job id, lease revision,
startup nonce, child process UUID, and a strictly increasing message sequence.
Any mismatch is dropped (and counted); a stale nonce — i.e. a replayed message
from a previous child — is rejected (FR-EXEC-012).
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass, field


def new_startup_nonce() -> str:
    """Cryptographically random 128-bit challenge, hex-encoded (IMP-EXEC-008)."""
    return secrets.token_hex(16)


def nonce_hash(nonce: str) -> str:
    """Only the hash is persisted; the nonce itself never touches the DB."""
    return hashlib.sha256(nonce.encode("utf-8")).hexdigest()


def make_message(
    *,
    msg_type: str,
    model_job_id: str,
    lease_revision: int,
    nonce: str,
    child_uuid: str,
    sequence: int,
    payload: dict | None = None,
) -> dict:
    return {
        "type": msg_type,
        "model_job_id": model_job_id,
        "execution_lease_revision": lease_revision,
        "worker_startup_nonce": nonce,
        "child_process_uuid": child_uuid,
        "message_sequence": sequence,
        "payload": payload or {},
    }


@dataclass
class IpcValidator:
    """Supervisor-side validator for one child process (IMP-EXEC-009)."""

    model_job_id: str
    lease_revision: int
    nonce: str
    child_uuid: str
    last_sequence: int = 0
    rejected_count: int = 0
    reject_threshold: int = 5
    rejections: list[str] = field(default_factory=list)

    def validate(self, msg: dict) -> tuple[bool, str]:
        """Returns (ok, reason). Invalid messages are counted, never applied."""
        reason = ""
        if not isinstance(msg, dict):
            reason = "not_a_dict"
        elif msg.get("model_job_id") != self.model_job_id:
            reason = "job_id_mismatch"
        elif msg.get("execution_lease_revision") != self.lease_revision:
            reason = "lease_revision_mismatch"
        elif msg.get("worker_startup_nonce") != self.nonce:
            reason = "nonce_mismatch"  # includes replays from an older child
        elif msg.get("child_process_uuid") != self.child_uuid:
            reason = "child_uuid_mismatch"
        elif int(msg.get("message_sequence", -1)) <= self.last_sequence:
            reason = "sequence_not_monotonic"

        if reason:
            self.rejected_count += 1
            self.rejections.append(reason)
            return False, reason

        self.last_sequence = int(msg["message_sequence"])
        return True, ""

    @property
    def should_terminate_child(self) -> bool:
        """IMP-EXEC-009: too many invalid messages ⇒ terminate the child."""
        return self.rejected_count >= self.reject_threshold


def new_child_identity() -> tuple[str, str]:
    """(startup_nonce, child_process_uuid) for one spawn attempt."""
    return new_startup_nonce(), str(uuid.uuid4())
