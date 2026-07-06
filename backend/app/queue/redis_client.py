"""Redis Streams wiring (P3).

- `exec:commands`  — the execution queue (Command Outbox → Dispatcher → here).
- `events:stream`  — business events (Event Outbox → Publisher → here).
- consumer group `supervisors` on the exec stream (Model Job Supervisor in P4;
  a mock validating consumer in P3).
"""
from __future__ import annotations

import redis

from ..config import Settings, get_settings

EXEC_STREAM = "exec:commands"
EVENT_STREAM = "events:stream"
SUPERVISOR_GROUP = "supervisors"


def get_redis(s: Settings | None = None) -> redis.Redis:
    s = s or get_settings()
    return redis.Redis(host=s.redis_host, port=s.redis_port, decode_responses=True)


def ensure_group(r: redis.Redis, stream: str = EXEC_STREAM, group: str = SUPERVISOR_GROUP) -> None:
    """Create the consumer group (and the stream) if it does not exist yet."""
    try:
        r.xgroup_create(name=stream, groupname=group, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
