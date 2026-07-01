"""P0 critical test — repository structure & public-repo safety.

Criticality: CRITICAL (security + data-integrity class, Master Plan sec 6).
Guards Hard Constraints H-13 (no restricted data / weights) and H-14
(no secrets / tokens / PHI) and verifies the mandatory medical disclaimer.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "LICENSE",
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    ".gitignore",
    ".gitattributes",
    "PROJECT_STATE.md",
    "project_state.json",
    "docs/specs/SPEC_MANIFEST.json",
    "docs/specs/VERSION_LOCK.md",
    "docs/templates/PHASE_EXIT_REPORT_TEMPLATE.md",
    "docs/templates/KNOWN_ISSUES_TEMPLATE.md",
    "docs/templates/CONFORMANCE_REPORT_TEMPLATE.md",
    "docs/governance/BRANCH_PROTECTION.md",
    ".github/workflows/ci.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    "scripts/spec_manifest.py",
    "scripts/ci_local.sh",
]

REQUIRED_DIRS = [
    "backend",
    "frontend",
    "services",
    "ml",
    "infra",
    "scripts",
    "docs",
    "tests",
]

# Files that must never appear anywhere in the working tree (public-repo safety).
FORBIDDEN_GLOBS = [
    "*.nii", "*.nii.gz", "*.dcm",          # medical volumes
    "*.ckpt", "*.pt", "*.pth", "*.onnx", "*.safetensors",  # weights
    "*.pem", "*.key",                       # crypto material
    "admin_token", "admin_token.*",         # admin token
]

# Directories excluded from the forbidden-content scan.
SCAN_EXCLUDE = {".git", "node_modules", ".venv", "venv", "__pycache__",
                ".mypy_cache", ".ruff_cache", ".pytest_cache"}


def _iter_files():
    for p in REPO_ROOT.rglob("*"):
        if any(part in SCAN_EXCLUDE for part in p.relative_to(REPO_ROOT).parts):
            continue
        if p.is_file():
            yield p


@pytest.mark.parametrize("rel", REQUIRED_FILES)
def test_required_file_exists(rel):
    assert (REPO_ROOT / rel).is_file(), f"required file missing: {rel}"


@pytest.mark.parametrize("rel", REQUIRED_DIRS)
def test_required_dir_exists(rel):
    assert (REPO_ROOT / rel).is_dir(), f"required directory missing: {rel}"


def test_mit_license():
    txt = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in txt
    assert "Sir7s" in txt


def test_readme_has_medical_disclaimer():
    txt = (REPO_ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "not intended for clinical diagnosis" in txt
    assert "research and demonstration use only" in txt


def test_no_forbidden_data_or_weight_files():
    offenders = []
    for pat in FORBIDDEN_GLOBS:
        for hit in REPO_ROOT.rglob(pat):
            if any(part in SCAN_EXCLUDE for part in hit.relative_to(REPO_ROOT).parts):
                continue
            offenders.append(str(hit.relative_to(REPO_ROOT)))
    assert not offenders, f"forbidden data/weight files present (H-13): {offenders}"


def test_no_env_files_committed():
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in REPO_ROOT.rglob(".env*")
        if p.is_file() and p.name != ".env.example"
        and not any(part in SCAN_EXCLUDE for part in p.relative_to(REPO_ROOT).parts)
    ]
    assert not offenders, f".env files must not be committed (H-14): {offenders}"


def test_gitignore_blocks_sensitive_paths():
    txt = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for needle in [".env", "*.nii", "checkpoints/", "data/", "*.pt"]:
        assert needle in txt, f".gitignore must ignore {needle}"


# Heuristic secret scan over text files (defense-in-depth alongside gitleaks).
SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),                       # AWS access key id
    re.compile(r"ghp_[A-Za-z0-9]{36}"),                    # GitHub PAT
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]
TEXT_SUFFIXES = {".py", ".md", ".json", ".yml", ".yaml", ".sh", ".txt", ".toml",
                 ".js", ".ts", ".tsx", ".cfg", ".ini", ".env", ".example"}


def test_no_obvious_secrets_in_text():
    offenders = []
    for p in _iter_files():
        if p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for rx in SECRET_PATTERNS:
            if rx.search(txt):
                offenders.append(f"{p.relative_to(REPO_ROOT)} :: {rx.pattern}")
    assert not offenders, f"possible secrets detected (H-14): {offenders}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
