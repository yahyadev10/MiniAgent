"use client";

import { ChangeEvent, FormEvent, Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";

import RunView from "@/components/RunView";
import { apiFetch, streamTask } from "@/lib/api";
import {
  ACTIONS,
  formatBytes,
  type Run,
} from "@/lib/types";

const MAX_UPLOAD = 200_000;
const ALLOWED_EXTENSIONS = [".csv", ".tsv", ".txt", ".json", ".md"];

type Example = {
  label: string;
  action: string;
  to?: string;
  subject?: string;
  body?: string;
  title?: string;
  content?: string;
};

const EXAMPLES: Example[] = [
  {
    label: "Email",
    action: "email",
    to: "john@example.com",
    subject: "Project update",
    body: "Hello John,\n\nThe Q3 analysis is ready. Let me know if you need the raw data.\n\nBest,",
  },
  {
    label: "Report",
    action: "report",
    title: "Q3 sales report",
    content: "Summarize the uploaded data and highlight the strongest columns.",
  },
  {
    label: "Email + report",
    action: "both",
    to: "john@example.com",
    subject: "Q3 report attached",
    body: "Hello John,\n\nPlease find the Q3 report attached.\n\nBest,",
    title: "Q3 sales report",
    content: "Summarize the uploaded data and highlight the strongest columns.",
  },
];

function NewTaskForm() {
  const searchParams = useSearchParams();
  const requested = searchParams.get("action");
  const initialAction = ACTIONS.some((item) => item.value === requested)
    ? (requested as string)
    : "auto";

  const [action, setAction] = useState(initialAction);
  const [message, setMessage] = useState("");
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");

  const [fileData, setFileData] = useState("");
  const [fileName, setFileName] = useState("");
  const [fileSize, setFileSize] = useState(0);
  const [fileError, setFileError] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [live, setLive] = useState<string[]>([]);

  const wantsEmail = action === "email" || action === "both";
  const wantsReport = action === "report" || action === "both";

  async function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) {
      return;
    }

    const dot = file.name.lastIndexOf(".");
    const extension = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
    if (!ALLOWED_EXTENSIONS.includes(extension)) {
      setFileError("Accepted formats: CSV, TSV, TXT, JSON, MD.");
      return;
    }
    if (file.size > MAX_UPLOAD) {
      setFileError("File too large (200 KB max).");
      return;
    }

    try {
      const text = await file.text();
      if (text.length > MAX_UPLOAD) {
        setFileError("Content too large (200,000 characters max).");
        return;
      }
      setFileData(text);
      setFileName(file.name);
      setFileSize(file.size);
      setFileError(null);
    } catch {
      setFileError("Unable to read this file.");
    }
  }

  function clearFile() {
    setFileData("");
    setFileName("");
    setFileSize(0);
    setFileError(null);
  }

  function applyExample(index: number) {
    const example = EXAMPLES[index];
    setAction(example.action);
    setTo(example.to ?? "");
    setSubject(example.subject ?? "");
    setBody(example.body ?? "");
    setTitle(example.title ?? "");
    setContent(example.content ?? "");
    setMessage("");
    setError(null);
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading) {
      return;
    }

    if (action === "auto" && !message.trim()) {
      setError("Describe the task in the message field.");
      return;
    }
    if (wantsEmail && !to.trim()) {
      setError("A recipient is required to send an email.");
      return;
    }

    setLoading(true);
    setError(null);
    setRun(null);
    setLive([]);

    const payload: Record<string, unknown> = { action };
    if (message.trim()) payload.message = message.trim();
    if (wantsEmail) {
      payload.to = to.trim();
      payload.subject = subject.trim();
      payload.body = body.trim();
    }
    if (wantsReport) {
      payload.title = title.trim();
      payload.content = content.trim();
    }
    if (fileData) {
      payload.data = fileData;
      payload.filename = fileName;
    }

    try {
      if (!fileData) {
        await streamTask(payload, (event, value) => {
          if (event === "start") {
            setLive(["Task started"]);
            return;
          }
          if (event === "status") {
            setLive((current) => [
              ...current,
              (value as { message?: string })?.message ?? "Working…",
            ]);
            return;
          }
          if (event === "step") {
            const data = value as {
              node?: string;
              steps?: { node: string; status: string; ms: number }[];
            };
            const messages = (data.steps ?? []).map(
              (step) => `${step.node}: ${step.status} (${step.ms} ms)`,
            );
            setLive((current) => [
              ...current,
              ...(messages.length ? messages : [`${data.node ?? "node"} updated`]),
            ]);
            return;
          }
          if (event === "done") {
            setRun(value as Run);
            return;
          }
          if (event === "error") {
            throw new Error(
              (value as { error?: string })?.error ?? "Stream failed",
            );
          }
        });
      } else {
        const res = await apiFetch("/tasks", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data?.detail ?? `HTTP ${res.status}`);
        }
        setRun(data as Run);
      }
      document
        .getElementById("result")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <p className="eyebrow">New task</p>
          <h1>Compose a real task</h1>
          <p className="lede">
            Pick an action, fill the fields you care about, and optionally attach
            a dataset for the report.
          </p>
        </div>
      </div>

      <form className="card form" onSubmit={onSubmit}>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="action">Action</label>
            <select
              id="action"
              className="input"
              value={action}
              onChange={(event) => setAction(event.target.value)}
              disabled={loading}
            >
              {ACTIONS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label>Examples</label>
            <div className="actions">
              {EXAMPLES.map((example, index) => (
                <button
                  key={example.label}
                  className="chip"
                  type="button"
                  disabled={loading}
                  onClick={() => applyExample(index)}
                >
                  {example.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {action === "auto" ? (
          <div className="field">
            <label htmlFor="message">Message</label>
            <textarea
              id="message"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="Ex: Send an email to John and generate a report about Q3 sales"
              disabled={loading}
            />
            <span className="hint">
              The local LLM classifies this text and extracts the fields.
            </span>
          </div>
        ) : null}

        {wantsEmail ? (
          <fieldset className="fieldset">
            <legend>Email</legend>
            <div className="form-grid">
              <div className="field">
                <label htmlFor="to">To</label>
                <input
                  id="to"
                  className="input"
                  type="email"
                  value={to}
                  onChange={(event) => setTo(event.target.value)}
                  placeholder="john@example.com"
                  disabled={loading}
                  required
                />
              </div>
              <div className="field">
                <label htmlFor="subject">Subject</label>
                <input
                  id="subject"
                  className="input"
                  value={subject}
                  onChange={(event) => setSubject(event.target.value)}
                  placeholder="Project update"
                  disabled={loading}
                />
              </div>
            </div>
            <div className="field">
              <label htmlFor="body">Body</label>
              <textarea
                id="body"
                value={body}
                onChange={(event) => setBody(event.target.value)}
                placeholder="Hello John, ..."
                disabled={loading}
              />
            </div>
          </fieldset>
        ) : null}

        {wantsReport ? (
          <fieldset className="fieldset">
            <legend>Report</legend>
            <div className="field">
              <label htmlFor="title">Title</label>
              <input
                id="title"
                className="input"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Q3 sales report"
                disabled={loading}
              />
            </div>
            <div className="field">
              <label htmlFor="content">Content / instructions</label>
              <textarea
                id="content"
                value={content}
                onChange={(event) => setContent(event.target.value)}
                placeholder="Summarize the uploaded data and highlight key numbers."
                disabled={loading}
              />
            </div>
          </fieldset>
        ) : null}

        <fieldset className="fieldset">
          <legend>Dataset (optional)</legend>
          <div className="file-row">
            <input
              id="data-file"
              type="file"
              accept={ALLOWED_EXTENSIONS.join(",")}
              onChange={(event) => void onFileChange(event)}
              disabled={loading}
            />
            {fileName ? (
              <button
                className="chip"
                type="button"
                onClick={clearFile}
                disabled={loading}
              >
                Remove {fileName} ({formatBytes(fileSize)})
              </button>
            ) : (
              <span className="hint">
                CSV, TSV, TXT, JSON or MD — 200 KB max. Used for charts and the
                numeric summary.
              </span>
            )}
          </div>
          {fileError ? <p className="error">{fileError}</p> : null}
          {fileData ? (
            <pre className="preview">{fileData.slice(0, 800)}</pre>
          ) : null}
        </fieldset>

        <div className="actions">
          <button className="primary" type="submit" disabled={loading}>
            {loading ? <span className="spinner" /> : null}
            {loading ? "Running…" : "Run task"}
          </button>
          <span className="hint">
            Artifacts are stored server-side and listed under Files.
          </span>
        </div>
        {error ? <p className="error">Error: {error}</p> : null}
      </form>

      {live.length ? (
        <section className="card">
          <h2>Live progress</h2>
          <pre className="preview">{live.join("\n")}</pre>
        </section>
      ) : null}

      <div id="result">
        {run ? (
          <RunView run={run} />
        ) : (
          <section className="card empty">
            <p>Run a task to see its trace and downloadable artifacts here.</p>
          </section>
        )}
      </div>
    </div>
  );
}

export default function NewTaskPage() {
  return (
    <Suspense fallback={<p className="hint">Loading form…</p>}>
      <NewTaskForm />
    </Suspense>
  );
}
