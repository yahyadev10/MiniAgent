"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import type { Capabilities } from "@/lib/types";

type Health = { status?: string; detail?: string };

const SERVICES = [
  { name: "FastAPI", url: "http://localhost:8000/docs", port: 8000 },
  { name: "Next.js", url: "http://localhost:3000", port: 3000 },
  { name: "Airflow", url: "http://localhost:8081", port: 8081 },
  { name: "Ollama", url: "http://localhost:11434", port: 11434 },
];

export default function SystemPage() {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [capRes, healthRes] = await Promise.all([
        apiFetch("/capabilities"),
        apiFetch("/health"),
      ]);
      const capData = await capRes.json().catch(() => ({}));
      const healthData = await healthRes.json().catch(() => ({}));

      if (!capRes.ok) {
        throw new Error(capData?.detail ?? `HTTP ${capRes.status}`);
      }
      setCapabilities(capData as Capabilities);
      setHealth(healthData as Health);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load system info");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <p className="eyebrow">System</p>
          <h1>Runtime and capabilities</h1>
          <p className="lede">
            Everything runs locally with Docker. No cloud API key is required.
          </p>
        </div>
        <button className="ghost" type="button" onClick={() => void load()}>
          Refresh
        </button>
      </div>

      {error ? <p className="error">Error: {error}</p> : null}

      <section className="split">
        <div className="card">
          <h2>Agent</h2>
          <dl className="kv">
            <div>
              <dt>API status</dt>
              <dd>
                <span
                  className={`status-dot ${
                    health?.status === "ok" ? "ok" : "bad"
                  }`}
                />
                {health?.status ?? health?.detail ?? "unknown"}
              </dd>
            </div>
            <div>
              <dt>Version</dt>
              <dd>{capabilities?.version ?? "—"}</dd>
            </div>
            <div>
              <dt>Local model</dt>
              <dd>{capabilities?.model ?? "—"}</dd>
            </div>
            <div>
              <dt>Email mode</dt>
              <dd>
                {capabilities?.email_mode === "smtp"
                  ? "SMTP delivery"
                  : "EML fallback (no SMTP configured)"}
              </dd>
            </div>
            <div>
              <dt>Actions</dt>
              <dd>{capabilities?.actions.join(", ") ?? "—"}</dd>
            </div>
            <div>
              <dt>Artifacts</dt>
              <dd>{capabilities?.artifacts_total ?? 0} file(s)</dd>
            </div>
            <div>
              <dt>Max dataset</dt>
              <dd>
                {capabilities
                  ? `${capabilities.max_data_chars.toLocaleString("fr-FR")} chars`
                  : "—"}
              </dd>
            </div>
          </dl>
        </div>

        <div className="card">
          <h2>Services</h2>
          <div className="service-list">
            {SERVICES.map((service) => (
              <a
                key={service.name}
                className="service"
                href={service.url}
                target="_blank"
                rel="noreferrer"
              >
                <span>{service.name}</span>
                <span className="service-port">:{service.port}</span>
                <span className="service-open">Open ↗</span>
              </a>
            ))}
          </div>
          <p className="hint">
            Airflow runs the scheduled workflow and calls the same API. History
            is stored in SQLite inside the API volume.
          </p>
        </div>
      </section>

      <section className="card">
        <h2>How artifacts are produced</h2>
        <ol className="steps">
          <li>LangGraph classifies the request (or uses your explicit action).</li>
          <li>The report MCP tool builds a PDF and an HTML file with ReportLab.</li>
          <li>The email MCP tool sends via SMTP or writes a .eml fallback.</li>
          <li>Files are written to the shared volume and linked in history.</li>
        </ol>
      </section>
    </div>
  );
}
