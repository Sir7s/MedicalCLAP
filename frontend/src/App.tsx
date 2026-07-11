import { useEffect, useState } from "react";
import Dashboard from "./Dashboard";
import Viewer from "./Viewer";

const BACKEND_URL =
  (import.meta.env.VITE_BACKEND_URL as string | undefined) ?? "http://127.0.0.1:8000";

type Health = { status: string; service: string; version: string };

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${BACKEND_URL}/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setHealth)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: 640, margin: "3rem auto", padding: "0 1rem" }}>
      <h1>3D Medical CLIP</h1>
      <p>Local chest-CT ↔ report retrieval platform — developer skeleton (P1).</p>

      <section style={{ marginTop: "1.5rem" }}>
        <h2 style={{ fontSize: "1rem" }}>Backend status</h2>
        {health && (
          <p style={{ color: "green" }}>
            ● {health.service} ok (v{health.version})
          </p>
        )}
        {error && <p style={{ color: "crimson" }}>● backend unreachable: {error}</p>}
        {!health && !error && <p>Checking…</p>}
      </section>

      <Viewer />

      <Dashboard />

      <footer style={{ marginTop: "2rem", fontSize: "0.8rem", color: "#666" }}>
        Research and demonstration use only. Not intended for clinical diagnosis or
        treatment decisions.
      </footer>
    </main>
  );
}
