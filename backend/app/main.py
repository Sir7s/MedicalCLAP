"""3D Medical CLIP — FastAPI control-plane entrypoint (P1).

Provides a healthy app skeleton with structured logging, config, CORS, a
liveness probe (/health) and a datastore-aware readiness probe (/health/ready).
Persistent control-plane logic (tasks, outbox, migrations) arrives in P2+.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .health import readiness
from .logging_config import configure_logging, get_logger

DISCLAIMER = (
    "Research and demonstration use only. "
    "Not intended for clinical diagnosis or treatment decisions."
)

settings = get_settings()
configure_logging(settings.log_level)
log = get_logger("medclip.backend")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info("backend starting version=%s", __version__)
    if os.environ.get("MEDCLIP_RUN_CONTROLPLANE", "0") == "1":
        from .controlplane.runner import start_background_runner

        start_background_runner()
        log.info("control-plane runner started")
    yield


app = FastAPI(title="3D Medical CLIP API", version=__version__, lifespan=lifespan)

from .controlplane.api import router as controlplane_router  # noqa: E402
from .controlplane.ws import router as ws_router  # noqa: E402
from .history.api import router as history_router  # noqa: E402
from .viewer.api import router as viewer_router  # noqa: E402

app.include_router(history_router)
app.include_router(controlplane_router)
app.include_router(ws_router)
app.include_router(viewer_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """Liveness probe — the process is up and serving."""
    return {"status": "ok", "service": "backend", "version": __version__}


@app.get("/health/ready")
def health_ready(response: Response) -> dict:
    """Readiness probe — reports each datastore dependency; 503 if any is down."""
    ok, deps = readiness(settings)
    if not ok:
        response.status_code = 503
    return {"status": "ok" if ok else "degraded", "dependencies": deps}


@app.get("/")
def root() -> dict:
    return {
        "name": "3D Medical CLIP API",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
        "ready": "/health/ready",
        "disclaimer": DISCLAIMER,
    }
