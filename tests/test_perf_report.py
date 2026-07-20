"""P19 — the performance harness must measure or admit, never fabricate."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "backend"))

import perf_report  # noqa: E402


def test_rerank_benchmark_produces_real_numbers():
    r = perf_report.measure_rerank(pool=20)
    assert r["status"] == "ok"
    assert r["samples"] >= 1
    assert r["min_ms"] <= r["p50_ms"] <= r["max_ms"]
    assert r["p50_ms"] >= 0.0
    assert r["pool"] == 20


def test_unavailable_components_render_without_fake_numbers():
    """A component that could not be measured must show '—', never an estimate."""
    results = {
        "ctclip_text": {"status": "unavailable", "reason": "service down"},
        "qdrant_search": {"status": "unavailable", "reason": "qdrant unreachable"},
        "rerank": perf_report.measure_rerank(pool=10),
    }
    md = perf_report.render(results)
    ctclip_row = next(line for line in md.splitlines() if "CT-CLIP text embed" in line)
    assert "unavailable" in ctclip_row
    assert "service down" in ctclip_row
    assert "ms" not in ctclip_row.split("|")[3], "no latency may be shown for an unmeasured stage"


def test_report_states_the_vram_ceiling_and_capacity_limit():
    md = perf_report.render({"rerank": perf_report.measure_rerank(pool=10)})
    assert "2.25 GB" in md          # the measured VRAM ceiling
    assert "single-user" in md.lower()
    assert "serialises" in md or "serializes" in md   # honest concurrency limit


def test_measured_stage_renders_its_numbers():
    md = perf_report.render({"rerank": perf_report.measure_rerank(pool=10)})
    row = next(line for line in md.splitlines() if "Findings re-rank" in line)
    assert "ok" in row and "ms" in row
