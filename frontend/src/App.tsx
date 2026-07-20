import { useState } from "react";
import "./theme.css";
import Dashboard from "./Dashboard";
import Search, { useRetrievalStatus } from "./Search";
import Viewer from "./Viewer";
import type { Lang } from "./i18n";
import { t } from "./i18n";

type Tab = "search" | "viewer" | "tasks";

/** P14 — Clinical Workstation shell (see docs/reports/P14_DESIGN_DECISION.md). */
export default function App() {
  const [lang, setLang] = useState<Lang>("en");
  const [tab, setTab] = useState<Tab>("search");
  const s = t(lang);
  const status = useRetrievalStatus();

  const engineOk = status?.embedder_available ?? false;
  const indexed = status?.volumes_indexed ?? 0;

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">
          {s.brand}
          <small>{s.tagline}</small>
        </span>

        <nav className="tabs" style={{ marginLeft: "1rem" }}>
          <button
            className={`tab${tab === "search" ? " active" : ""}`}
            onClick={() => setTab("search")}
          >
            {s.tabSearch}
          </button>
          <button
            className={`tab${tab === "viewer" ? " active" : ""}`}
            onClick={() => setTab("viewer")}
          >
            {s.tabViewer}
          </button>
          <button
            className={`tab${tab === "tasks" ? " active" : ""}`}
            onClick={() => setTab("tasks")}
          >
            {s.tabTasks}
          </button>
        </nav>

        <span className="spacer" />

        <span className="status" title={engineOk ? s.engineOk : s.engineDown}>
          <span className={`dot ${engineOk ? "ok" : "err"}`} />
          {engineOk ? s.engineOk : s.engineDown}
          {status && (
            <span style={{ marginLeft: "0.5rem" }}>
              · {indexed} {s.indexed}
            </span>
          )}
        </span>

        <button
          className="tab"
          onClick={() => setLang(lang === "en" ? "zh" : "en")}
          aria-label="toggle language"
        >
          {lang === "en" ? "中文" : "EN"}
        </button>
      </header>

      {tab === "search" && <Search lang={lang} />}

      {tab === "viewer" && (
        <div className="pane" style={{ flex: 1 }}>
          <Viewer />
        </div>
      )}

      {tab === "tasks" && (
        <div className="pane" style={{ flex: 1 }}>
          <Dashboard />
        </div>
      )}

      <footer className="disclaimer">{s.disclaimer}</footer>
    </div>
  );
}
