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

export const ACTION_LABEL: Record<string, string> = {
  email: "Email",
  report: "Report",
  both: "Email + Report",
  unknown: "Unsupported",
};

export const ACTIONS = [
  { value: "auto", label: "Auto (LLM decides)" },
  { value: "email", label: "Send an email" },
  { value: "report", label: "Generate a report" },
  { value: "both", label: "Email + report" },
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

export function formatBytes(bytes: number) {
  if (!bytes) {
    return "0 o";
  }
  if (bytes < 1024) {
    return `${bytes} o`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} Ko`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

export function formatTime(iso: string | null) {
  if (!iso) {
    return "—";
  }
  try {
    return new Date(iso).toLocaleString("fr-FR", {
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
