"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { apiFetch, setSession } from "@/lib/api";

export default function LoginPage() {
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
        setError("Account created. You can sign in now.");
        return;
      }
      setSession(data.access_token, data.username);
      router.push("/");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <p className="eyebrow">Account</p>
          <h1>Private workspace access</h1>
          <p className="lede">
            Login to isolate your runs and history. Without an account, the
            shared public workspace is used.
          </p>
        </div>
      </div>

      <form className="card form" onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="username">Username</label>
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
          <label htmlFor="password">Password</label>
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
              ? "Please wait…"
              : mode === "login"
                ? "Sign in"
                : "Create account"}
          </button>
          <button
            className="chip"
            type="button"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError(null);
            }}
          >
            {mode === "login" ? "Create account" : "Back to sign in"}
          </button>
        </div>
        {error ? <p className="hint">{error}</p> : null}
      </form>
    </div>
  );
}
