"use client";

import { useCallback, useEffect, useState } from "react";

import { useI18n } from "@/components/LanguageProvider";
import { apiFetch } from "@/lib/api";
import { actionLabel, type TranslationKey } from "@/lib/i18n";
import type { Capabilities } from "@/lib/types";

type Health = { status?: string; detail?: string };

const SERVICES = [
  { name: "FastAPI", url: "http://localhost:8000/docs", port: 8000 },
  { name: "Next.js", url: "http://localhost:3000", port: 3000 },
  { name: "Airflow", url: "http://localhost:8081", port: 8081 },
  { name: "Ollama", url: "http://localhost:11434", port: 11434 },
];

const STEP_KEYS: TranslationKey[] = [
  "system.step1",
  "system.step2",
  "system.step3",
  "system.step4",
];

export default function SystemPage() {
  const { locale, t } = useI18n();
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
      setError(
        err instanceof Error ? err.message : t("system.loadError"),
      );
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <p className="eyebrow">{t("system.eyebrow")}</p>
          <h1>{t("system.title")}</h1>
          <p className="lede">{t("system.lede")}</p>
        </div>
        <button className="ghost" type="button" onClick={() => void load()}>
          {t("common.refresh")}
        </button>
      </div>

      {error ? (
        <p className="error">
          {t("common.error")}: {error}
        </p>
      ) : null}

      <section className="split">
        <div className="card">
          <h2>{t("system.agent")}</h2>
          <dl className="kv">
            <div>
              <dt>{t("system.apiStatus")}</dt>
              <dd>
                <span
                  className={`status-dot ${
                    health?.status === "ok" ? "ok" : "bad"
                  }`}
                />
                {health?.status ?? health?.detail ?? t("common.unknown")}
              </dd>
            </div>
            <div>
              <dt>{t("system.version")}</dt>
              <dd>{capabilities?.version ?? "—"}</dd>
            </div>
            <div>
              <dt>{t("system.localModel")}</dt>
              <dd>{capabilities?.model ?? "—"}</dd>
            </div>
            <div>
              <dt>{t("system.emailMode")}</dt>
              <dd>
                {capabilities?.email_mode === "smtp"
                  ? t("system.smtp")
                  : t("system.eml")}
              </dd>
            </div>
            <div>
              <dt>{t("system.actions")}</dt>
              <dd>
                {capabilities?.actions
                  .map((action) => actionLabel(locale, action))
                  .join(", ") ?? "—"}
              </dd>
            </div>
            <div>
              <dt>{t("system.artifacts")}</dt>
              <dd>
                {t("common.fileCount", { count: capabilities?.artifacts_total ?? 0 })}
              </dd>
            </div>
            <div>
              <dt>{t("system.maxDataset")}</dt>
              <dd>
                {capabilities
                  ? t("system.chars", {
                      count: capabilities.max_data_chars.toLocaleString(
                        locale === "fr" ? "fr-FR" : "en-GB",
                      ),
                    })
                  : "—"}
              </dd>
            </div>
          </dl>
        </div>

        <div className="card">
          <h2>{t("system.services")}</h2>
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
                <span className="service-open">{t("system.open")}</span>
              </a>
            ))}
          </div>
          <p className="hint">{t("system.hint")}</p>
        </div>
      </section>

      <section className="card">
        <h2>{t("system.how")}</h2>
        <ol className="steps">
          {STEP_KEYS.map((key) => (
            <li key={key}>{t(key)}</li>
          ))}
        </ol>
      </section>
    </div>
  );
}
