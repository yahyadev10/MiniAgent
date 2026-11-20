export function authHeaders(request: Request): HeadersInit {
  const headers = new Headers();
  const authorization = request.headers.get("authorization");
  if (authorization) {
    headers.set("Authorization", authorization);
  }
  return headers;
}

export function jsonHeaders(request: Request): HeadersInit {
  const headers = new Headers(authHeaders(request));
  headers.set("Content-Type", "application/json");
  return headers;
}
