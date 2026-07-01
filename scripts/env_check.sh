#!/usr/bin/env bash
# 3D Medical CLIP — environment preflight (P1).
# Verifies the host can run the local stack. Exit non-zero if a hard
# requirement is missing.
set -uo pipefail

fail=0
ok()   { echo "  [ ok ] $1"; }
bad()  { echo "  [FAIL] $1"; fail=1; }
warn() { echo "  [warn] $1"; }

echo "== Docker =="
if command -v docker >/dev/null 2>&1; then
  ok "docker: $(docker --version | awk '{print $3}' | tr -d ,)"
else
  bad "docker not found on PATH"
fi

if docker compose version >/dev/null 2>&1; then
  ok "docker compose: $(docker compose version --short 2>/dev/null)"
else
  bad "docker compose plugin not available"
fi

if docker info >/dev/null 2>&1; then
  ok "docker daemon reachable ($(docker info --format '{{.OSType}}/{{.Architecture}}' 2>/dev/null))"
else
  bad "docker daemon not reachable (is Docker Desktop running?)"
fi

echo "== WSL2 =="
if grep -qi microsoft /proc/version 2>/dev/null; then
  ok "running inside WSL2"
else
  warn "not inside WSL2 (fine on Windows/Git Bash with Docker Desktop)"
fi

echo "== Ports (should be free or owned by our stack) =="
for p in 5432 6379 6333 6334 8000 5173; do
  if (exec 3<>/dev/tcp/127.0.0.1/"$p") 2>/dev/null; then
    warn "port $p in use (ok if it's our stack)"
    exec 3>&- 2>/dev/null || true
  else
    ok "port $p free"
  fi
done

echo "== Disk (workspace drive) =="
avail=$(df -Pm . 2>/dev/null | awk 'NR==2{print $4}')
if [ -n "${avail:-}" ]; then
  if [ "$avail" -ge 5120 ]; then ok "free space: ${avail} MB"; else warn "low free space: ${avail} MB (<5 GB)"; fi
fi

echo ""
if [ "$fail" -eq 0 ]; then
  echo "environment preflight: PASS"
else
  echo "environment preflight: FAIL (resolve [FAIL] items above)"
fi
exit "$fail"
