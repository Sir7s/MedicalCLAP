"""Client for the CT-CLIP embedding service (P13, AUP-005).

CT-CLIP inference is the *real* GPU worker that replaces P4's mock. It runs as a
separate host-side process (its research-code dependency stack and CUDA build are
kept out of the API container), and the backend talks to it over loopback HTTP.

If the service is down the backend degrades honestly: search returns a clear
503 rather than silently producing meaningless results.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

DEFAULT_URL = os.environ.get("MEDCLIP_CTCLIP_URL", "http://127.0.0.1:8077")
TIMEOUT = float(os.environ.get("MEDCLIP_CTCLIP_TIMEOUT", "120"))


class EmbedderUnavailable(RuntimeError):
    """Raised when the CT-CLIP service cannot be reached or errors."""


@dataclass
class VolumeEmbedding:
    vector: list[float]
    findings: list[float]


class CtClipEmbedder:
    def __init__(self, base_url: str = DEFAULT_URL, timeout: float = TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/health", timeout=5)
            return r.status_code == 200 and r.json().get("model_loaded") is True
        except Exception:  # noqa: BLE001 - unavailable is a normal, reportable state
            return False

    def embed_text(self, text: str) -> list[float]:
        try:
            r = httpx.post(f"{self.base_url}/embed/text", json={"text": text},
                           timeout=self.timeout)
            r.raise_for_status()
            return [float(x) for x in r.json()["vector"]]
        except Exception as exc:  # noqa: BLE001
            raise EmbedderUnavailable(f"CT-CLIP text embedding failed: {exc}") from exc

    def embed_volume(self, path: str) -> VolumeEmbedding:
        try:
            r = httpx.post(f"{self.base_url}/embed/volume", json={"path": path},
                           timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            return VolumeEmbedding(
                vector=[float(x) for x in data["vector"]],
                findings=[float(x) for x in data.get("findings", [])],
            )
        except Exception as exc:  # noqa: BLE001
            raise EmbedderUnavailable(f"CT-CLIP volume embedding failed: {exc}") from exc
