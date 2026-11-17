"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import RunView from "@/components/RunView";
import type { Run } from "@/lib/types";

export default function RunDetailPage() {
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
          setError(err instanceof Error ? err.message : "Unable to load run");
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <p className="eyebrow">Run detail</p>
          <h1>{id ? `Run #${id}` : "Run"}</h1>
          <p className="lede">
            Trace, tool output, artifacts and the final answer for this run.
          </p>
        </div>
        <Link className="ghost" href="/history">
          ← Back to history
        </Link>
      </div>

      {error ? <p className="error">Error: {error}</p> : null}
      {run ? (
        <RunView run={run} />
      ) : !error ? (
        <section className="card empty">
          <p>Loading run…</p>
        </section>
      ) : null}
    </div>
  );
}
