"""P1 critical test — WSL2 named-volume presence & write permission.

Criticality: CRITICAL (data integrity / reproducibility, Master Plan sec 6,
"WSL2 path & volume permission test"). Datastores use named Docker volumes
(not host bind mounts) to avoid WSL2/Windows permission pitfalls; this test
proves the project volumes exist and that a named volume is writable by a
container under the current (WSL2) engine.

Auto-skips when the Docker CLI/daemon is unavailable.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import pytest

_DOCKER = shutil.which("docker") or r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
PROJECT = "medical-clip-3d"
EXPECTED_VOLUMES = ["pgdata", "redisdata", "qdrantdata"]
# Reuse an image the stack already pulled to avoid extra network use.
HELPER_IMAGE = "redis:7-alpine"


def _docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_DOCKER, *args], capture_output=True, text=True, timeout=90
    )


def _docker_ok() -> bool:
    if not (os.path.exists(_DOCKER) or shutil.which("docker")):
        return False
    try:
        return _docker("info").returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = pytest.mark.skipif(not _docker_ok(), reason="docker CLI/daemon unavailable")


def test_project_named_volumes_exist():
    out = _docker("volume", "ls", "--format", "{{.Name}}")
    names = out.stdout
    for v in EXPECTED_VOLUMES:
        assert f"{PROJECT}_{v}" in names, f"missing named volume {PROJECT}_{v}"


def test_named_volume_is_writable_and_persists():
    vol = "medclip_perm_test_vol"
    _docker("volume", "create", vol)
    try:
        write = _docker(
            "run", "--rm", "-v", f"{vol}:/data", HELPER_IMAGE,
            "sh", "-c", "echo medclip > /data/perm.txt",
        )
        assert write.returncode == 0, write.stderr
        # Fresh container proves persistence + read permission.
        read = _docker(
            "run", "--rm", "-v", f"{vol}:/data", HELPER_IMAGE,
            "sh", "-c", "cat /data/perm.txt",
        )
        assert read.returncode == 0 and "medclip" in read.stdout, read.stderr
    finally:
        _docker("volume", "rm", "-f", vol)
