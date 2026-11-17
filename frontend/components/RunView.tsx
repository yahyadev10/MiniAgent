"use client";

import {
  ACTION_LABEL,
  artifactHref,
  formatBytes,
  formatMs,
  formatTime,
  type Run,
} from "@/lib/types";

export default function RunView({ run }: { run: Run }) {
  const savedEmail = run.artifacts.some((artifact) => artifact.kind === "eml");

  return (
    <section className="card">
      <div className="result-head">
        <span className={`badge badge-${run.action}`}>
          {ACTION_LABEL[run.action] ?? run.action}
        </span>
        <span className="meta">#{run.id}</span>
        <span className="meta">{formatMs(run.duration_ms)}</span>
        <span className="meta">{formatTime(run.created_at)}</span>
        <a className="download" href={`/api/report/${run.id}`}>
          Report .md
        </a>
      </div>

      <p className="run-message">{run.message}</p>

      <h3 className="panel-title">Execution trace</h3>
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

      <h3 className="panel-title">Results</h3>
      {run.results.length === 0 ? (
        <p className="hint">No tool output for this run.</p>
      ) : (
        run.results.map((result, index) => (
          <pre key={`${index}-${result.slice(0, 24)}`}>{result}</pre>
        ))
      )}

      {run.artifacts.length > 0 ? (
        <>
          <h3 className="panel-title">Downloadable artifacts</h3>
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
                  {formatBytes(artifact.size)}
                </span>
              </a>
            ))}
          </div>
        </>
      ) : null}

      {savedEmail ? (
        <p className="hint">
          SMTP is not configured: the email was saved as an .eml file and can be
          sent from any mail client.
        </p>
      ) : null}

      <h3 className="panel-title">Final answer</h3>
      <p className="final">{run.final}</p>
    </section>
  );
}
