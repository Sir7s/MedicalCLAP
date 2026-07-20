import { useCallback, useEffect, useState } from "react";
import type { Lang } from "./i18n";
import { t } from "./i18n";

const API =
  (import.meta.env.VITE_BACKEND_URL as string | undefined) ?? "http://127.0.0.1:8000";

export type SearchResult = {
  rank: number;
  volume: string;
  score: number;
  recall_score: number;
  findings_match: number;
  report: string;
  explanation: string[];
  why: string;
};

type SearchResponse = {
  query_type: string;
  query: string;
  recall_pool: number;
  alpha: number;
  results: SearchResult[];
};

type Status = {
  volumes_indexed: number;
  reports_indexed: number;
  embedder_available: boolean;
  default_alpha: number;
};

export default function Search({ lang }: { lang: Lang }) {
  const s = t(lang);
  const [query, setQuery] = useState("");
  const [alpha, setAlpha] = useState(0.9);
  const [top, setTop] = useState(10);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selected, setSelected] = useState<SearchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<Status | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/retrieval/status`);
      if (r.ok) setStatus((await r.json()) as Status);
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  const runSearch = useCallback(async () => {
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`${API}/api/retrieval/search/text`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text: query, top, alpha }),
      });
      if (!r.ok) {
        const detail = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }));
        throw new Error(detail.detail ?? `HTTP ${r.status}`);
      }
      const body = (await r.json()) as SearchResponse;
      setResults(body.results);
      setSelected(body.results[0] ?? null);
    } catch (e) {
      setError((e as Error).message);
      setResults([]);
      setSelected(null);
    } finally {
      setBusy(false);
    }
  }, [query, top, alpha]);

  const engineOk = status?.embedder_available ?? false;

  return (
    <div className="panes">
      {/* ---- left: query + ranked results ---- */}
      <section className="pane">
        <h2 className="section">{s.queryLabel}</h2>
        <div className="field">
          <textarea
            rows={3}
            value={query}
            placeholder={s.queryPlaceholder}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void runSearch();
            }}
          />
        </div>

        <div className="field">
          <label htmlFor="alpha">
            {s.balance} — <span style={{ fontFamily: "var(--mono)" }}>α={alpha.toFixed(2)}</span>
          </label>
          <div className="rowline">
            <input
              id="alpha"
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={alpha}
              onChange={(e) => setAlpha(Number(e.target.value))}
            />
          </div>
          <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>{s.balanceHint}</span>
        </div>

        <div className="field">
          <label htmlFor="top">{s.topK}</label>
          <div className="rowline">
            <input
              id="top"
              type="range"
              min={1}
              max={25}
              step={1}
              value={top}
              onChange={(e) => setTop(Number(e.target.value))}
            />
            <span style={{ fontFamily: "var(--mono)", minWidth: "2ch" }}>{top}</span>
          </div>
        </div>

        <button className="primary" onClick={() => void runSearch()} disabled={busy || !query.trim()}>
          {busy ? s.searching : s.search}
        </button>

        {!engineOk && status && (
          <p className="error" style={{ marginTop: "0.8rem" }}>
            {s.engineHelp}
          </p>
        )}
        {error && (
          <p className="error" style={{ marginTop: "0.8rem" }}>
            {error}
          </p>
        )}

        <h2 className="section" style={{ marginTop: "1.25rem" }}>
          {s.results}
          {results.length > 0 && (
            <span style={{ color: "var(--text-dim)" }}> · {results.length}</span>
          )}
        </h2>

        {results.length === 0 && !error && <p className="empty">{s.noResults}</p>}

        {results.map((r) => (
          <div
            key={`${r.rank}-${r.volume}`}
            className={`result${selected?.volume === r.volume ? " selected" : ""}`}
            onClick={() => setSelected(r)}
          >
            <div className="result-head">
              <span className="rank">#{r.rank}</span>
              <span className="vol">{r.volume}</span>
              <span className="score">{r.score.toFixed(3)}</span>
            </div>
            {/* Explanations are grounded server-side: only findings BOTH sides express. */}
            {r.explanation.length > 0 ? (
              <>
                <div className="why">
                  {s.bothShow} {r.explanation.length}
                </div>
                <div className="chips">
                  {r.explanation.map((f) => (
                    <span className="chip" key={f}>
                      {f}
                    </span>
                  ))}
                </div>
              </>
            ) : (
              <div className="why">{s.noExplanation}</div>
            )}
          </div>
        ))}
      </section>

      {/* ---- right: selected report ---- */}
      <section className="pane">
        <h2 className="section">{s.reportTitle}</h2>
        {!selected && <p className="empty">{s.selectHint}</p>}
        {selected && (
          <>
            <div className="result selected" style={{ cursor: "default" }}>
              <div className="result-head">
                <span className="vol">{selected.volume}</span>
                <span className="score">{selected.score.toFixed(3)}</span>
              </div>
              <div className="why" style={{ marginTop: "0.5rem" }}>
                <span style={{ fontFamily: "var(--mono)" }}>
                  recall {selected.recall_score.toFixed(3)} · findings{" "}
                  {selected.findings_match.toFixed(3)}
                </span>
              </div>
              {selected.explanation.length > 0 && (
                <div className="chips">
                  {selected.explanation.map((f) => (
                    <span className="chip" key={f}>
                      {f}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.55, color: "var(--text)" }}>
              {selected.report || "—"}
            </p>
          </>
        )}
      </section>
    </div>
  );
}

export function useRetrievalStatus() {
  const [status, setStatus] = useState<Status | null>(null);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await fetch(`${API}/api/retrieval/status`);
        if (r.ok && alive) setStatus((await r.json()) as Status);
      } catch {
        if (alive) setStatus(null);
      }
    };
    void load();
    const id = setInterval(() => void load(), 15000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);
  return status;
}
