"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import {
  ACTION_LABEL,
  ACTIONS,
  formatMs,
  formatTime,
  type Run,
} from "@/lib/types";

export default function HistoryPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [action, setAction] = useState("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (nextAction: string, nextQuery: string) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "50" });
      if (nextAction !== "all") {
        params.set("action", nextAction);
      }
      if (nextQuery.trim()) {
        params.set("q", nextQuery.trim());
      }
      const res = await apiFetch(`/history?${params.toString()}`);
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail ?? `HTTP ${res.status}`);
      }
      setRuns(data as Run[]);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load history");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      void load(action, query);
    }, 250);
    return () => clearTimeout(timer);
  }, [action, query, load]);

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <p className="eyebrow">History</p>
          <h1>Every run, with its trace</h1>
          <p className="lede">
            Search by text or filter by action. Open a run to download its
            artifacts and Markdown report.
          </p>
        </div>
        <Link className="primary" href="/new">
          + New task
        </Link>
      </div>

      <section className="card">
        <div className="filters">
          <div className="field">
            <label htmlFor="search">Search</label>
            <input
              id="search"
              className="input"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Message or final answer…"
            />
          </div>
          <div className="field">
            <label htmlFor="action-filter">Action</label>
            <select
              id="action-filter"
              className="input"
              value={action}
              onChange={(event) => setAction(event.target.value)}
            >
              <option value="all">All actions</option>
              {ACTIONS.filter((item) => item.value !== "auto").map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
              <option value="unknown">Unsupported</option>
            </select>
          </div>
          <div className="filters-status">
            <span className="hint">
              {loading ? "Loading…" : `${runs.length} run(s)`}
            </span>
          </div>
        </div>

        {error ? <p className="error">Error: {error}</p> : null}

        {runs.length === 0 && !loading ? (
          <p className="hint">No run matches these filters.</p>
        ) : (
          <div className="run-table">
            {runs.map((run) => (
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
