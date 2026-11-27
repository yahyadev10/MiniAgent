"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { useI18n } from "@/components/LanguageProvider";
import { apiFetch, setSession } from "@/lib/api";

export default function LoginPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail ?? `HTTP ${res.status}`);
      }
      if (mode === "register") {
        setMode("login");
        setError(t("login.created"));
        return;
      }
      setSession(data.access_token, data.username);
      router.push("/");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("login.failed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <p className="eyebrow">{t("login.eyebrow")}</p>
          <h1>{t("login.title")}</h1>
          <p className="lede">{t("login.lede")}</p>
        </div>
      </div>

      <form className="card form" onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="username">{t("login.username")}</label>
          <input
            id="username"
            className="input"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            required
          />
        </div>
        <div className="field">
          <label htmlFor="password">{t("login.password")}</label>
          <input
            id="password"
            className="input"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            minLength={6}
            required
          />
        </div>
        <div className="actions">
          <button className="primary" type="submit" disabled={loading}>
            {loading
              ? t("login.wait")
              : mode === "login"
                ? t("login.signIn")
                : t("login.create")}
          </button>
          <button
            className="chip"
            type="button"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError(null);
            }}
          >
            {mode === "login" ? t("login.create") : t("login.back")}
          </button>
        </div>
        {error ? <p className="hint">{error}</p> : null}
      </form>
    </div>
  );
}
