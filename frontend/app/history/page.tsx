"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useI18n } from "@/components/LanguageProvider";
import { apiFetch } from "@/lib/api";
import { actionLabel } from "@/lib/i18n";
import {
  ACTIONS,
  formatMs,
  formatTime,
  type Run,
} from "@/lib/types";

export default function HistoryPage() {
  const { locale, t } = useI18n();
  const [runs, setRuns] = useState<Run[]>([]);
  const [action, setAction] = useState("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (nextAction: string, nextQuery: string) => {
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
        setError(
          err instanceof Error ? err.message : t("history.loadError"),
        );
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

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
          <p className="eyebrow">{t("history.eyebrow")}</p>
          <h1>{t("history.title")}</h1>
          <p className="lede">{t("history.lede")}</p>
        </div>
        <Link className="primary" href="/new">
          {t("common.newTask")}
        </Link>
      </div>

      <section className="card">
        <div className="filters">
          <div className="field">
            <label htmlFor="search">{t("history.search")}</label>
            <input
              id="search"
              className="input"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("history.searchPlaceholder")}
            />
          </div>
          <div className="field">
            <label htmlFor="action-filter">{t("new.action")}</label>
            <select
              id="action-filter"
              className="input"
              value={action}
              onChange={(event) => setAction(event.target.value)}
            >
              <option value="all">{t("history.all")}</option>
              {ACTIONS.filter((item) => item.value !== "auto").map((item) => (
                <option key={item.value} value={item.value}>
                  {actionLabel(locale, item.value)}
                </option>
              ))}
              <option value="unknown">{t("action.unsupported")}</option>
            </select>
          </div>
          <div className="filters-status">
            <span className="hint">
              {loading
                ? t("common.loading")
                : t("common.runCount", { count: runs.length })}
            </span>
          </div>
        </div>

        {error ? (
          <p className="error">
            {t("common.error")}: {error}
          </p>
        ) : null}

        {runs.length === 0 && !loading ? (
          <p className="hint">{t("history.noMatches")}</p>
        ) : (
          <div className="run-table">
            {runs.map((run) => (
              <Link key={run.id} href={`/history/${run.id}`} className="run-row">
                <span className={`badge badge-${run.action} small`}>
                  {actionLabel(locale, run.action)}
                </span>
                <span className="run-row-message">{run.message}</span>
                <span className="run-row-meta">
                  {t("common.fileCount", { count: run.artifacts.length })}
                </span>
                <span className="run-row-meta">{formatMs(run.duration_ms)}</span>
                <span className="run-row-meta">
                  {formatTime(run.created_at, locale)}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
