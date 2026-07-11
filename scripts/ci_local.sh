#!/usr/bin/env bash
# Local mirror of the GitHub Actions CI (P0 smoke baseline).
# Runs the same governance/lint/type/test/security checks locally so a phase
# can be validated without pushing.
#
# Override the interpreter if `python` on PATH lacks the dev toolchain:
#   PYTHON=/c/path/to/python.exe bash scripts/ci_local.sh
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2
PYTHON="${PYTHON:-python}"

fail=0
run() {
  echo ""
  echo "=== $1 ==="
  shift
  if "$@"; then
    echo "PASS"
  else
    echo "FAIL ($*)"
    fail=1
  fi
}

run "lint (ruff)"                 "$PYTHON" -m ruff check . backend --no-cache
run "type check (mypy, root)"     "$PYTHON" -m mypy scripts tests ml
run "type check (mypy, backend)"  bash -c "cd '$(pwd)/backend' && '$PYTHON' -m mypy app"
run "spec manifest integrity"     "$PYTHON" scripts/spec_manifest.py --check
run "unit tests + coverage"       "$PYTHON" -m pytest --cov --cov-report=term-missing
run "backend unit tests"          bash -c "cd '$(pwd)/backend' && '$PYTHON' -m pytest -q"
run "SAST (bandit)"               "$PYTHON" -m bandit -r scripts backend/app -ll
run "dependency audit (pip-audit)" "$PYTHON" -m pip_audit -r requirements-dev.txt

echo ""
if [ "$fail" -eq 0 ]; then
  echo "==================== CI LOCAL: ALL GREEN ===================="
else
  echo "==================== CI LOCAL: FAILURES ABOVE ===================="
fi
exit "$fail"
