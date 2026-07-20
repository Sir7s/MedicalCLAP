"""P17 — public-repository hardening: nothing sensitive tracked, licences honest.

These assertions run in CI on every push, so a future commit that leaks a weight,
a dataset, a secret, or that quietly drops the non-commercial notice, fails the build.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True,
                         text=True, check=True).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


# --- nothing sensitive is tracked ------------------------------------------

def test_no_model_weights_tracked():
    bad = [f for f in _tracked()
           if f.endswith((".pt", ".pth", ".ckpt", ".onnx", ".safetensors", ".bin"))]
    assert bad == [], f"model weights must never be committed (H-14): {bad}"


def test_no_medical_volumes_or_caches_tracked():
    bad = [f for f in _tracked()
           if f.endswith((".nii", ".nii.gz", ".dcm", ".npz", ".npy"))]
    assert bad == [], f"restricted data must never be committed (H-13): {bad}"


def test_no_env_or_secret_files_tracked():
    allowed = {"infra/.env.example"}
    pattern = re.compile(r"(^|/)\.env($|\.)|secret|credential|\.pem$|\.key$", re.I)
    bad = [f for f in _tracked() if pattern.search(f) and f not in allowed]
    assert bad == [], f"secrets must never be committed: {bad}"


def test_run_artifacts_not_tracked():
    bad = [f for f in _tracked() if f.startswith(("runs/", "data/ct_rate/"))]
    assert bad == [], f"run artifacts / datasets must stay out of git: {bad}"


# --- licence honesty --------------------------------------------------------

def test_third_party_notices_exist_and_name_the_restricted_components():
    notices = (REPO / "THIRD_PARTY_NOTICES.md")
    assert notices.is_file(), "THIRD_PARTY_NOTICES.md is required for a public repo"
    text = notices.read_text(encoding="utf-8")
    for token in ("CT-CLIP", "CT-RATE", "CC-BY-NC-SA"):
        assert token in text, f"third-party notices must document {token}"


def test_readme_declares_non_commercial_restriction():
    """MIT covers our code; the deployed stack is CC-BY-NC-SA. Saying only 'MIT'
    would misrepresent the terms a user is actually bound by."""
    text = (REPO / "README.md").read_text(encoding="utf-8")
    assert "CC-BY-NC-SA" in text
    assert "non-commercial" in text.lower()
    assert "THIRD_PARTY_NOTICES.md" in text


def test_security_policy_documents_data_and_network_posture():
    text = (REPO / "SECURITY.md").read_text(encoding="utf-8")
    assert "127.0.0.1" in text
    assert "PHI" in text
    for token in ("gitleaks", "bandit", "pip-audit"):
        assert token in text, f"security policy should state the {token} control"


def test_security_policy_is_honest_about_missing_auth():
    """The app has no auth layer yet; the policy must say so rather than imply one."""
    text = (REPO / "SECURITY.md").read_text(encoding="utf-8").lower()
    assert "known limitations" in text
    assert "no auth" in text or "not yet implemented" in text


# --- disclaimer surfaces ----------------------------------------------------

def test_medical_disclaimer_present_in_user_facing_surfaces():
    readme = (REPO / "README.md").read_text(encoding="utf-8").lower()
    assert "disclaimer" in readme
    i18n = (REPO / "frontend/src/i18n.ts").read_text(encoding="utf-8")
    assert "disclaimer" in i18n, "the UI must render a research-use disclaimer"
