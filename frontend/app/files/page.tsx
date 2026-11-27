"use client";

import { useCallback, useEffect, useState } from "react";

import { useI18n } from "@/components/LanguageProvider";
import { apiFetch } from "@/lib/api";
import type { TranslationKey } from "@/lib/i18n";
import {
  artifactHref,
  formatBytes,
  formatTime,
  type FileInfo,
} from "@/lib/types";

const KIND_LABEL: Record<string, TranslationKey> = {
  pdf: "files.kindPdf",
  html: "files.kindHtml",
  eml: "files.kindEml",
};

export default function FilesPage() {
  const { locale, t } = useI18n();
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch("/files?limit=200");
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail ?? `HTTP ${res.status}`);
      }
      setFiles(data as FileInfo[]);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("files.loadError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const counts = files.reduce<Record<string, number>>((acc, file) => {
    acc[file.kind] = (acc[file.kind] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <p className="eyebrow">{t("files.eyebrow")}</p>
          <h1>{t("files.title")}</h1>
          <p className="lede">{t("files.lede")}</p>
        </div>
        <button className="ghost" type="button" onClick={() => void load()}>
          {t("common.refresh")}
        </button>
      </div>

      <section className="stats">
        <div className="stat">
          <span className="stat-value">{files.length}</span>
          <span className="stat-label">{t("files.total")}</span>
        </div>
        <div className="stat">
          <span className="stat-value">{counts.pdf ?? 0}</span>
          <span className="stat-label">{t("files.pdf")}</span>
        </div>
        <div className="stat">
          <span className="stat-value">{counts.html ?? 0}</span>
          <span className="stat-label">{t("files.html")}</span>
        </div>
        <div className="stat">
          <span className="stat-value">{counts.eml ?? 0}</span>
          <span className="stat-label">{t("files.eml")}</span>
        </div>
      </section>

      {error ? (
        <p className="error">
          {t("common.error")}: {error}
        </p>
      ) : null}

      {loading ? (
        <p className="hint">{t("files.loading")}</p>
      ) : files.length === 0 ? (
        <section className="card empty">
          <p>{t("files.empty")}</p>
        </section>
      ) : (
        <section className="file-grid">
          {files.map((file) => (
            <a
              key={file.filename}
              className="file-card"
              href={artifactHref(file.filename)}
            >
              <span className="artifact-kind">{file.kind}</span>
              <strong>{t(KIND_LABEL[file.kind] ?? "files.total")}</strong>
              <span className="file-name">{file.filename}</span>
              <span className="file-meta">
                {formatBytes(file.size, locale)} ·{" "}
                {formatTime(file.modified_at, locale)}
              </span>
              <em>{t("common.download")} →</em>
            </a>
          ))}
        </section>
      )}
    </div>
  );
}
