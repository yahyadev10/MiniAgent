"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useI18n } from "@/components/LanguageProvider";
import { apiFetch } from "@/lib/api";
import { actionLabel, type TranslationKey } from "@/lib/i18n";
import {
  formatMs,
  formatTime,
  type Capabilities,
  type Dashboard,
} from "@/lib/types";

const QUICK_ACTIONS: {
  href: string;
  title: TranslationKey;
  text: TranslationKey;
}[] = [
  {
    href: "/new?action=email",
    title: "dashboard.quick1.title",
    text: "dashboard.quick1.text",
  },
  {
    href: "/new?action=report",
    title: "dashboard.quick2.title",
    text: "dashboard.quick2.text",
  },
  {
    href: "/new?action=both",
    title: "dashboard.quick3.title",
    text: "dashboard.quick3.text",
  },
  {
    href: "/new?action=auto",
    title: "dashboard.quick4.title",
    text: "dashboard.quick4.text",
  },
];

export default function DashboardPage() {
  const { locale, t } = useI18n();
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
      setError(
        err instanceof Error ? err.message : t("dashboard.loadError"),
      );
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const stats = dashboard?.stats;
  const items = dashboard?.items ?? [];

  return (
    <div className="stack">
      <section className="hero">
        <div>
          <p className="eyebrow">{t("dashboard.eyebrow")}</p>
          <h1>{t("dashboard.title")}</h1>
          <p className="lede">{t("dashboard.lede")}</p>
          <div className="actions">
            <Link className="primary" href="/new">
              {t("dashboard.start")}
            </Link>
            <Link className="ghost" href="/history">
              {t("dashboard.browse")}
            </Link>
          </div>
        </div>
        <div className="hero-card">
          <span className="live">
            <span className="live-dot" /> {t("dashboard.backendOnline")}
          </span>
          <dl>
            <div>
              <dt>{t("dashboard.model")}</dt>
              <dd>{capabilities?.model ?? "loading…"}</dd>
            </div>
            <div>
              <dt>{t("dashboard.emailMode")}</dt>
              <dd>
                {capabilities?.email_mode === "smtp"
                  ? t("dashboard.smtp")
                  : t("dashboard.eml")}
              </dd>
            </div>
            <div>
              <dt>{t("dashboard.apiVersion")}</dt>
              <dd>{capabilities?.version ?? "—"}</dd>
            </div>
          </dl>
        </div>
      </section>

      {error ? (
        <p className="error">
          {t("common.error")}: {error}
        </p>
      ) : null}

      <section className="stats">
        <div className="stat">
          <span className="stat-value">{stats?.total ?? 0}</span>
          <span className="stat-label">{t("dashboard.runs")}</span>
        </div>
        <div className="stat">
          <span className="stat-value">
            {formatMs(stats?.avg_duration_ms ?? 0)}
          </span>
          <span className="stat-label">{t("dashboard.latency")}</span>
        </div>
        <div className="stat">
          <span className="stat-value">{stats?.artifacts_total ?? 0}</span>
          <span className="stat-label">{t("dashboard.artifacts")}</span>
        </div>
        <div className="stat">
          <span className="stat-value">
            {(stats?.by_action.email ?? 0) + (stats?.by_action.both ?? 0)}
          </span>
          <span className="stat-label">{t("dashboard.emails")}</span>
        </div>
      </section>

      <section className="quick-grid">
        {QUICK_ACTIONS.map((action) => (
          <Link key={action.href} href={action.href} className="quick-card">
            <strong>{t(action.title)}</strong>
            <span>{t(action.text)}</span>
            <em>{t("common.open")} →</em>
          </Link>
        ))}
      </section>

      <section className="card">
        <div className="section-head">
          <h2>{t("dashboard.recent")}</h2>
          <Link className="ghost small" href="/history">
            {t("dashboard.viewAll")}
          </Link>
        </div>
        {items.length === 0 ? (
          <p className="hint">{t("dashboard.noRuns")}</p>
        ) : (
          <div className="run-table">
            {items.map((run) => (
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
