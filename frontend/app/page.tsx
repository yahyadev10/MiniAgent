"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import {
  ACTION_LABEL,
  formatMs,
  formatTime,
  type Capabilities,
  type Dashboard,
} from "@/lib/types";

const QUICK_ACTIONS = [
  {
    href: "/new?action=email",
    title: "Send an email",
    text: "Recipient, subject and body. Falls back to a .eml file without SMTP.",
  },
  {
    href: "/new?action=report",
    title: "Build a report",
    text: "PDF + HTML report with charts, insights and numeric summary.",
  },
  {
    href: "/new?action=both",
    title: "Email + report",
    text: "Generate the report first, then attach it to the email.",
  },
  {
    href: "/new?action=auto",
    title: "Auto mode",
    text: "Describe the task in natural language and let the local LLM decide.",
  },
];

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [dashRes, capRes] = await Promise.all([
        apiFetch("/dashboard?limit=8"),
        apiFetch("/capabilities"),
      ]);
      if (!dashRes.ok) {
        throw new Error(`Dashboard HTTP ${dashRes.status}`);
      }
      setDashboard((await dashRes.json()) as Dashboard);
      if (capRes.ok) {
        setCapabilities((await capRes.json()) as Capabilities);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load dashboard");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const stats = dashboard?.stats;
  const items = dashboard?.items ?? [];

  return (
    <div className="stack">
      <section className="hero">
        <div>
          <p className="eyebrow">Local automation workspace</p>
          <h1>Send emails and build real reports with a private agent.</h1>
          <p className="lede">
            LangGraph plans the task, MCP tools produce PDF/HTML/EML artifacts,
            and every run is stored with its full trace.
          </p>
          <div className="actions">
            <Link className="primary" href="/new">
              Start a task
            </Link>
            <Link className="ghost" href="/history">
              Browse history
            </Link>
          </div>
        </div>
        <div className="hero-card">
          <span className="live">
            <span className="live-dot" /> backend online
          </span>
          <dl>
            <div>
              <dt>Model</dt>
              <dd>{capabilities?.model ?? "loading…"}</dd>
            </div>
            <div>
              <dt>Email mode</dt>
              <dd>
                {capabilities?.email_mode === "smtp"
                  ? "SMTP delivery"
                  : "EML fallback"}
              </dd>
            </div>
            <div>
              <dt>API version</dt>
              <dd>{capabilities?.version ?? "—"}</dd>
            </div>
          </dl>
        </div>
      </section>

      {error ? <p className="error">Error: {error}</p> : null}

      <section className="stats">
        <div className="stat">
          <span className="stat-value">{stats?.total ?? 0}</span>
          <span className="stat-label">Runs</span>
        </div>
        <div className="stat">
          <span className="stat-value">
            {formatMs(stats?.avg_duration_ms ?? 0)}
          </span>
          <span className="stat-label">Average latency</span>
        </div>
        <div className="stat">
          <span className="stat-value">{stats?.artifacts_total ?? 0}</span>
          <span className="stat-label">Artifacts</span>
        </div>
        <div className="stat">
          <span className="stat-value">
            {(stats?.by_action.email ?? 0) + (stats?.by_action.both ?? 0)}
          </span>
          <span className="stat-label">Emails</span>
        </div>
      </section>

      <section className="quick-grid">
        {QUICK_ACTIONS.map((action) => (
          <Link key={action.href} href={action.href} className="quick-card">
            <strong>{action.title}</strong>
            <span>{action.text}</span>
            <em>Open →</em>
          </Link>
        ))}
      </section>

      <section className="card">
        <div className="section-head">
          <h2>Recent runs</h2>
          <Link className="ghost small" href="/history">
            View all
          </Link>
        </div>
        {items.length === 0 ? (
          <p className="hint">
            No runs yet. Start with an email or a report to populate history.
          </p>
        ) : (
          <div className="run-table">
            {items.map((run) => (
              <Link key={run.id} href={`/history/${run.id}`} className="run-row">
                <span className={`badge badge-${run.action} small`}>
                  {ACTION_LABEL[run.action] ?? run.action}
                </span>
                <span className="run-row-message">{run.message}</span>
                <span className="run-row-meta">
                  {run.artifacts.length} file(s)
                </span>
                <span className="run-row-meta">{formatMs(run.duration_ms)}</span>
                <span className="run-row-meta">{formatTime(run.created_at)}</span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
