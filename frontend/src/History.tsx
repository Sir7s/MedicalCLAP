import { useCallback, useEffect, useState } from "react";
import type { Lang } from "./i18n";
import { t } from "./i18n";

const API =
  (import.meta.env.VITE_BACKEND_URL as string | undefined) ?? "http://127.0.0.1:8000";

type HistoryItem = {
  id: string;
  title: string;
  profile: string;
  state: string;
  created_at: string;
};

type HistoryDetail = HistoryItem & {
  payload: { query?: string; results?: Array<Record<string, unknown>> };
};

/** P15 — saved searches: list, inspect, export (JSON/CSV). */
export default function History({ lang }: { lang: Lang }) {
  const s = t(lang);
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [detail, setDetail] = useState<HistoryDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/history`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setItems((await r.json()) as HistoryItem[]);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const open = useCallback(async (id: string) => {
    try {
      const r = await fetch(`${API}/api/history/${id}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setDetail((await r.json()) as HistoryDetail);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const exportUrl = (id: string, fmt: "json" | "csv") =>
    `${API}/api/history/${id}/export?format=${fmt}`;

  const results = (detail?.payload?.results ?? []) as Array<Record<string, unknown>>;

  return (
    <div className="panes">
      <section className="pane">
        <h2 className="section">
          {s.historyTitle}
          {items.length > 0 && <span style={{ color: "var(--text-dim)" }}> · {items.length}</span>}
        </h2>

        {error && <p className="error">{error}</p>}
        {items.length === 0 && !error && <p className="empty">{s.historyEmpty}</p>}

        {items.map((it) => (
          <div
            key={it.id}
            className={`result${detail?.id === it.id ? " selected" : ""}`}
            onClick={() => void open(it.id)}
          >
            <div className="result-head">
              <span className="vol">{it.title}</span>
              <span className="score">{new Date(it.created_at).toLocaleString()}</span>
            </div>
          </div>
        ))}
      </section>

      <section className="pane">
        <h2 className="section">{s.historyDetail}</h2>
        {!detail && <p className="empty">{s.historySelectHint}</p>}
        {detail && (
          <>
            <div className="rowline" style={{ marginBottom: "0.8rem" }}>
              <a className="tab" href={exportUrl(detail.id, "json")} download>
                {s.exportJson}
              </a>
              <a className="tab" href={exportUrl(detail.id, "csv")} download>
                {s.exportCsv}
              </a>
            </div>

            {detail.payload?.query && (
              <p style={{ color: "var(--text-dim)", fontSize: 13 }}>
                {s.queryLabel}: <span style={{ color: "var(--text)" }}>{detail.payload.query}</span>
              </p>
            )}

            {results.map((r, i) => (
              <div className="result" key={i} style={{ cursor: "default" }}>
                <div className="result-head">
                  <span className="rank">#{String(r.rank ?? i + 1)}</span>
                  <span className="vol">{String(r.volume ?? "")}</span>
                  <span className="score">{Number(r.score ?? 0).toFixed(3)}</span>
                </div>
                {Array.isArray(r.explanation) && r.explanation.length > 0 && (
                  <div className="chips">
                    {(r.explanation as string[]).map((f) => (
                      <span className="chip" key={f}>
                        {f}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </>
        )}
      </section>
    </div>
  );
}

/** Save a completed search into history (used by the Search panel). */
export async function saveSearch(
  workspaceId: string,
  title: string,
  payload: Record<string, unknown>,
): Promise<string> {
  const r = await fetch(`${API}/api/history/save`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ workspace_id: workspaceId, title, payload }),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }));
    throw new Error(d.detail ?? `HTTP ${r.status}`);
  }
  return (await r.json()).history_record_id as string;
}
