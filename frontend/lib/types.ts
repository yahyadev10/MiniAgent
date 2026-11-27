import type { Locale } from "@/lib/i18n";

export type Step = { node: string; status: string; ms: number };

export type Citation = { title: string; url: string };

export type Artifact = {
  kind: string;
  filename: string;
  size: number;
  url: string;
};

export type Run = {
  id: string;
  message: string;
  action: string;
  results: string[];
  final: string;
  steps: Step[];
  duration_ms: number;
  created_at: string;
  artifacts: Artifact[];
  citations?: Citation[];
  owner?: string;
};

export type Job = {
  id: string;
  status: "queued" | "running" | "done" | "failed";
  progress: number;
};

export type JobStatus = Job & {
  result: Run | null;
  error: string | null;
  created_at: string;
};

export type Stats = {
  total: number;
  avg_duration_ms: number;
  by_action: Record<string, number>;
  artifacts_total: number;
  last_run_at: string | null;
};

export type Dashboard = { stats: Stats; items: Run[] };

export type Capabilities = {
  version: string;
  model: string;
  actions: string[];
  email_mode: "smtp" | "eml";
  artifacts_total: number;
  max_data_chars: number;
};

export type FileInfo = {
  kind: string;
  filename: string;
  size: number;
  modified_at: string;
  url: string;
};

export const ACTIONS = [
  { value: "auto" },
  { value: "email" },
  { value: "report" },
  { value: "both" },
];

export function formatMs(ms: number) {
  if (!ms) {
    return "0 ms";
  }
  if (ms < 1000) {
    return `${ms} ms`;
  }
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatBytes(bytes: number, locale: Locale = "fr") {
  const units = locale === "fr" ? ["o", "Ko", "Mo"] : ["B", "KB", "MB"];
  if (!bytes) {
    return `0 ${units[0]}`;
  }
  if (bytes < 1024) {
    return `${bytes} ${units[0]}`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} ${units[1]}`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} ${units[2]}`;
}

export function formatTime(iso: string | null, locale: Locale = "fr") {
  if (!iso) {
    return "—";
  }
  try {
    return new Date(iso).toLocaleString(locale === "fr" ? "fr-FR" : "en-GB", {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

export function artifactHref(filename: string) {
  return `/api/artifacts/${encodeURIComponent(filename)}`;
}
