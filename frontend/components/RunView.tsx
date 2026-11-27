"use client";

import { useI18n } from "@/components/LanguageProvider";
import { actionLabel } from "@/lib/i18n";
import {
  artifactHref,
  formatBytes,
  formatMs,
  formatTime,
  type Run,
} from "@/lib/types";

export default function RunView({ run }: { run: Run }) {
  const { locale, t } = useI18n();
  const savedEmail = run.artifacts.some((artifact) => artifact.kind === "eml");

  return (
    <section className="card">
      <div className="result-head">
        <span className={`badge badge-${run.action}`}>
          {actionLabel(locale, run.action)}
        </span>
        <span className="meta">#{run.id}</span>
        <span className="meta">{formatMs(run.duration_ms)}</span>
        <span className="meta">{formatTime(run.created_at, locale)}</span>
        <a className="download" href={`/api/report/${run.id}`}>
          {t("run.report")}
        </a>
      </div>

      <p className="run-message">{run.message}</p>

      <h3 className="panel-title">{t("run.trace")}</h3>
      <ol className="timeline">
        {run.steps.map((step, index) => (
          <li key={`${step.node}-${index}`} className="timeline-item">
            <span className="dot" />
            <span className="node">{step.node}</span>
            <span className={`step-status step-${step.status}`}>
              {step.status}
            </span>
            <span className="ms">{step.ms} ms</span>
          </li>
        ))}
      </ol>

      <h3 className="panel-title">{t("run.results")}</h3>
      {run.results.length === 0 ? (
        <p className="hint">{t("run.noOutput")}</p>
      ) : (
        run.results.map((result, index) => (
          <pre key={`${index}-${result.slice(0, 24)}`}>{result}</pre>
        ))
      )}

      {run.artifacts.length > 0 ? (
        <>
          <h3 className="panel-title">{t("run.artifacts")}</h3>
          <div className="artifact-list">
            {run.artifacts.map((artifact) => (
              <a
                key={artifact.filename}
                className="artifact"
                href={artifactHref(artifact.filename)}
              >
                <span className="artifact-kind">{artifact.kind}</span>
                <span className="artifact-name">{artifact.filename}</span>
                <span className="artifact-size">
                  {formatBytes(artifact.size, locale)}
                </span>
              </a>
            ))}
          </div>
        </>
      ) : null}

      {savedEmail ? <p className="hint">{t("run.smtpHint")}</p> : null}

      {run.citations?.length ? (
        <>
          <h3 className="panel-title">{t("run.citations")}</h3>
          <ol className="timeline">
            {run.citations.map((citation, index) => (
              <li key={`${citation.url}-${index}`} className="timeline-item">
                <span className="dot" />
                <a href={citation.url} target="_blank" rel="noreferrer">
                  [{index + 1}] {citation.title}
                </a>
              </li>
            ))}
          </ol>
        </>
      ) : null}

      <h3 className="panel-title">{t("run.final")}</h3>
      <p className="final">{run.final}</p>
    </section>
  );
}
