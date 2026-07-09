import { useCallback, useEffect, useRef, useState } from "react";

const API =
  (import.meta.env.VITE_BACKEND_URL as string | undefined) ?? "http://127.0.0.1:8000";
const WS_BASE = API.replace(/^http/, "ws");

type TaskStatus = {
  task_id: string;
  task_state: string;
  attempt_state: string | null;
  job_state: string | null;
  lease_revision: number | null;
};
type WsEvent = { event_sequence: number; event_type: string; aggregate_type: string };

export default function Dashboard() {
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [tasks, setTasks] = useState<TaskStatus[]>([]);
  const [events, setEvents] = useState<WsEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const lastSeq = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);

  const createWorkspace = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/workspaces`, { method: "POST" });
      const body = await r.json();
      setWorkspaceId(body.workspace_id);
      setTasks([]);
      setEvents([]);
      lastSeq.current = 0;
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const createTask = useCallback(async () => {
    if (!workspaceId) return;
    try {
      const r = await fetch(`${API}/api/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: workspaceId, task_type: "mock_retrieval" }),
      });
      const body = await r.json();
      setTasks((t) => [
        { task_id: body.task_id, task_state: "queued", attempt_state: null,
          job_state: null, lease_revision: null },
        ...t,
      ]);
    } catch (e) {
      setError(String(e));
    }
  }, [workspaceId]);

  // Poll task states.
  useEffect(() => {
    if (tasks.length === 0) return;
    const id = setInterval(async () => {
      const updated = await Promise.all(
        tasks.map(async (t) => {
          const r = await fetch(`${API}/api/tasks/${t.task_id}`);
          return r.ok ? ((await r.json()) as TaskStatus) : t;
        }),
      );
      setTasks(updated);
    }, 1500);
    return () => clearInterval(id);
  }, [tasks]);

  // WebSocket event stream with sequence dedup + gap-safe reconnect.
  useEffect(() => {
    if (!workspaceId) return;
    const ws = new WebSocket(`${WS_BASE}/ws/${workspaceId}?after=${lastSeq.current}`);
    wsRef.current = ws;
    ws.onmessage = (msg) => {
      const ev = JSON.parse(msg.data) as WsEvent;
      if (ev.event_sequence > lastSeq.current) {
        lastSeq.current = ev.event_sequence;
        setEvents((es) => [ev, ...es].slice(0, 50));
      }
    };
    return () => ws.close();
  }, [workspaceId]);

  return (
    <section style={{ marginTop: "2rem" }}>
      <h2 style={{ fontSize: "1.1rem" }}>Control-plane dashboard (P6 demo)</h2>
      <div style={{ display: "flex", gap: "0.5rem", margin: "0.75rem 0" }}>
        <button onClick={createWorkspace}>New workspace</button>
        <button onClick={createTask} disabled={!workspaceId}>
          Run mock retrieval task
        </button>
      </div>
      {workspaceId && <p style={{ fontSize: "0.8rem" }}>workspace: <code>{workspaceId}</code></p>}
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
        <div>
          <h3 style={{ fontSize: "0.9rem" }}>Tasks</h3>
          {tasks.map((t) => (
            <div key={t.task_id} style={{ border: "1px solid #ddd", borderRadius: 6,
                                          padding: "0.5rem", marginBottom: "0.5rem" }}>
              <code style={{ fontSize: "0.7rem" }}>{t.task_id.slice(0, 8)}</code>
              <div style={{ fontSize: "0.85rem" }}>
                task <b>{t.task_state}</b> · attempt {t.attempt_state ?? "—"} · job{" "}
                {t.job_state ?? "—"} · lease r{t.lease_revision ?? "—"}
              </div>
            </div>
          ))}
        </div>
        <div>
          <h3 style={{ fontSize: "0.9rem" }}>Events (live via WebSocket)</h3>
          <ol style={{ fontSize: "0.8rem", paddingLeft: "1.2rem" }}>
            {events.map((e) => (
              <li key={e.event_sequence}>
                #{e.event_sequence} {e.event_type} ({e.aggregate_type})
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
