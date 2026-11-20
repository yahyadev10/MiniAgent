"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import {
  artifactHref,
  formatBytes,
  formatTime,
  type FileInfo,
} from "@/lib/types";

const KIND_LABEL: Record<string, string> = {
  pdf: "PDF report",
  html: "HTML report",
  eml: "Email file",
};

export default function FilesPage() {
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
      setError(err instanceof Error ? err.message : "Unable to load files");
    } finally {
      setLoading(false);
    }
  }, []);

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
          <p className="eyebrow">Files</p>
          <h1>Artifact library</h1>
          <p className="lede">
            Every PDF, HTML report and .eml email produced by the agent, ready to
            download.
          </p>
        </div>
        <button className="ghost" type="button" onClick={() => void load()}>
          Refresh
        </button>
      </div>

      <section className="stats">
        <div className="stat">
          <span className="stat-value">{files.length}</span>
          <span className="stat-label">Total files</span>
        </div>
        <div className="stat">
          <span className="stat-value">{counts.pdf ?? 0}</span>
          <span className="stat-label">PDF</span>
        </div>
        <div className="stat">
          <span className="stat-value">{counts.html ?? 0}</span>
          <span className="stat-label">HTML</span>
        </div>
        <div className="stat">
          <span className="stat-value">{counts.eml ?? 0}</span>
          <span className="stat-label">EML</span>
        </div>
      </section>

      {error ? <p className="error">Error: {error}</p> : null}

      {loading ? (
        <p className="hint">Loading files…</p>
      ) : files.length === 0 ? (
        <section className="card empty">
          <p>No artifacts yet. Run a report or email task first.</p>
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
              <strong>{KIND_LABEL[file.kind] ?? file.kind}</strong>
              <span className="file-name">{file.filename}</span>
              <span className="file-meta">
                {formatBytes(file.size)} · {formatTime(file.modified_at)}
              </span>
              <em>Download →</em>
            </a>
          ))}
        </section>
      )}
    </div>
  );
}
