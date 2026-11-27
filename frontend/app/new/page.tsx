"use client";

import { ChangeEvent, FormEvent, Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";

import { useI18n } from "@/components/LanguageProvider";
import RunView from "@/components/RunView";
import { apiFetch, streamTask } from "@/lib/api";
import { actionLabel, statusLabel } from "@/lib/i18n";
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

function NewTaskForm() {
  const { locale, t } = useI18n();
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

  const examples: Example[] = [
    {
      label: t("action.email"),
      action: "email",
      to: "john@example.com",
      subject: t("new.subjectPlaceholder"),
      body: t("new.exampleEmailBody"),
    },
    {
      label: t("action.report"),
      action: "report",
      title: t("new.titlePlaceholder"),
      content: t("new.contentPlaceholder"),
    },
    {
      label: t("action.both"),
      action: "both",
      to: "john@example.com",
      subject: t("new.titlePlaceholder"),
      body: t("new.exampleBothBody"),
      title: t("new.titlePlaceholder"),
      content: t("new.contentPlaceholder"),
    },
  ];

  async function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) {
      return;
    }

    const dot = file.name.lastIndexOf(".");
    const extension = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
    if (!ALLOWED_EXTENSIONS.includes(extension)) {
      setFileError(t("new.errFormats"));
      return;
    }
    if (file.size > MAX_UPLOAD) {
      setFileError(t("new.errTooLarge"));
      return;
    }

    try {
      const text = await file.text();
      if (text.length > MAX_UPLOAD) {
        setFileError(t("new.errContentTooLarge"));
        return;
      }
      setFileData(text);
      setFileName(file.name);
      setFileSize(file.size);
      setFileError(null);
    } catch {
      setFileError(t("new.errRead"));
    }
  }

  function clearFile() {
    setFileData("");
    setFileName("");
    setFileSize(0);
    setFileError(null);
  }

  function applyExample(index: number) {
    const example = examples[index];
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
      setError(t("new.errDescribe"));
      return;
    }
    if (wantsEmail && !to.trim()) {
      setError(t("new.errRecipient"));
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
            setLive([t("new.started")]);
            return;
          }
          if (event === "status") {
            setLive((current) => [
              ...current,
              statusLabel(
                locale,
                (value as { message?: string })?.message ?? t("new.working"),
              ),
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
              ...(messages.length
                ? messages
                : [t("new.nodeUpdated", { node: data.node ?? "node" })]),
            ]);
            return;
          }
          if (event === "done") {
            setRun(value as Run);
            return;
          }
          if (event === "error") {
            throw new Error(
              (value as { error?: string })?.error ?? t("new.streamFailed"),
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
      setError(err instanceof Error ? err.message : t("new.unknownError"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <p className="eyebrow">{t("new.eyebrow")}</p>
          <h1>{t("new.title")}</h1>
          <p className="lede">{t("new.lede")}</p>
        </div>
      </div>

      <form className="card form" onSubmit={onSubmit}>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="action">{t("new.action")}</label>
            <select
              id="action"
              className="input"
              value={action}
              onChange={(event) => setAction(event.target.value)}
              disabled={loading}
            >
              {ACTIONS.map((item) => (
                <option key={item.value} value={item.value}>
                  {actionLabel(locale, item.value)}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label>{t("new.examples")}</label>
            <div className="actions">
              {examples.map((example, index) => (
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
            <label htmlFor="message">{t("new.message")}</label>
            <textarea
              id="message"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder={t("new.messagePlaceholder")}
              disabled={loading}
            />
            <span className="hint">{t("new.messageHint")}</span>
          </div>
        ) : null}

        {wantsEmail ? (
          <fieldset className="fieldset">
            <legend>{t("new.email")}</legend>
            <div className="form-grid">
              <div className="field">
                <label htmlFor="to">{t("new.to")}</label>
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
                <label htmlFor="subject">{t("new.subject")}</label>
                <input
                  id="subject"
                  className="input"
                  value={subject}
                  onChange={(event) => setSubject(event.target.value)}
                  placeholder={t("new.subjectPlaceholder")}
                  disabled={loading}
                />
              </div>
            </div>
            <div className="field">
              <label htmlFor="body">{t("new.body")}</label>
              <textarea
                id="body"
                value={body}
                onChange={(event) => setBody(event.target.value)}
                placeholder={t("new.bodyPlaceholder")}
                disabled={loading}
              />
            </div>
          </fieldset>
        ) : null}

        {wantsReport ? (
          <fieldset className="fieldset">
            <legend>{t("new.report")}</legend>
            <div className="field">
              <label htmlFor="title">{t("new.titleField")}</label>
              <input
                id="title"
                className="input"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder={t("new.titlePlaceholder")}
                disabled={loading}
              />
            </div>
            <div className="field">
              <label htmlFor="content">{t("new.content")}</label>
              <textarea
                id="content"
                value={content}
                onChange={(event) => setContent(event.target.value)}
                placeholder={t("new.contentPlaceholder")}
                disabled={loading}
              />
            </div>
          </fieldset>
        ) : null}

        <fieldset className="fieldset">
          <legend>{t("new.dataset")}</legend>
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
                {t("new.remove", {
                  name: fileName,
                  size: formatBytes(fileSize, locale),
                })}
              </button>
            ) : (
              <span className="hint">{t("new.datasetHint")}</span>
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
            {loading ? t("new.running") : t("new.run")}
          </button>
          <span className="hint">{t("new.artifactsHint")}</span>
        </div>
        {error ? (
          <p className="error">
            {t("common.error")}: {error}
          </p>
        ) : null}
      </form>

      {live.length ? (
        <section className="card">
          <h2>{t("new.live")}</h2>
          <pre className="preview">{live.join("\n")}</pre>
        </section>
      ) : null}

      <div id="result">
        {run ? (
          <RunView run={run} />
        ) : (
          <section className="card empty">
            <p>{t("new.empty")}</p>
          </section>
        )}
      </div>
    </div>
  );
}

export default function NewTaskPage() {
  const { t } = useI18n();
  return (
    <Suspense fallback={<p className="hint">{t("common.loading")}</p>}>
      <NewTaskForm />
    </Suspense>
  );
}
