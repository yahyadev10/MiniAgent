"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useI18n } from "@/components/LanguageProvider";
import RunView from "@/components/RunView";
import type { Run } from "@/lib/types";

export default function RunDetailPage() {
  const { t } = useI18n();
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) {
      return;
    }
    let cancelled = false;

    async function load() {
      try {
        const res = await fetch(`/api/history/${id}`, { cache: "no-store" });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data?.detail ?? `HTTP ${res.status}`);
        }
        if (!cancelled) {
          setRun(data as Run);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("detail.loadError"));
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [id, t]);

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <p className="eyebrow">{t("detail.eyebrow")}</p>
          <h1>{t("detail.title", { id: id ?? "—" })}</h1>
          <p className="lede">{t("detail.lede")}</p>
        </div>
        <Link className="ghost" href="/history">
          {t("detail.back")}
        </Link>
      </div>

      {error ? (
        <p className="error">
          {t("common.error")}: {error}
        </p>
      ) : null}
      {run ? (
        <RunView run={run} />
      ) : !error ? (
        <section className="card empty">
          <p>{t("detail.loading")}</p>
        </section>
      ) : null}
    </div>
  );
}
