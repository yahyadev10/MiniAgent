const TOKEN_KEY = "mini-agent-token";
const USER_KEY = "mini-agent-user";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setSession(token: string | null, username: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
  if (username) window.localStorage.setItem(USER_KEY, username);
  else window.localStorage.removeItem(USER_KEY);
}

export function getUsername(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(USER_KEY);
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(path.startsWith("/") ? `/api${path}` : path, {
    ...init,
    headers,
    cache: "no-store",
  });
}

export async function streamTask(
  payload: Record<string, unknown>,
  onEvent: (event: string, data: unknown) => void,
) {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const query = new URLSearchParams(
    Object.entries(payload)
      .filter(([, value]) => value !== undefined && value !== null && value !== "")
      .map(([key, value]) => [key, String(value)]),
  );
  const res = await fetch(`/api/tasks/stream?${query.toString()}`, { headers });
  if (!res.ok || !res.body) {
    let detail = `HTTP ${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let event = "message";
      let dataText = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        if (line.startsWith("data: ")) dataText += line.slice(6);
      }
      if (dataText) {
        try {
          onEvent(event, JSON.parse(dataText));
        } catch {
          onEvent(event, dataText);
        }
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
}
