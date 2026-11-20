import { NextResponse } from "next/server";

import { authHeaders, jsonHeaders } from "@/lib/server-api";

const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export async function POST(
  request: Request,
  context: { params: Promise<{ mode: string }> },
) {
  const { mode } = await context.params;
  if (mode !== "login" && mode !== "register") {
    return NextResponse.json({ detail: "Unknown auth mode." }, { status: 404 });
  }
  try {
    const response = await fetch(`${API_BASE}/auth/${mode}`, {
      method: "POST",
      headers: jsonHeaders(request),
      body: await request.text(),
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        detail: `Cannot reach the agent API at ${API_BASE}: ${
          error instanceof Error ? error.message : String(error)
        }`,
      },
      { status: 502 },
    );
  }
}

export async function GET(
  request: Request,
  context: { params: Promise<{ mode: string }> },
) {
  const { mode } = await context.params;
  if (mode !== "me") {
    return NextResponse.json({ detail: "Unknown auth mode." }, { status: 404 });
  }
  try {
    const response = await fetch(`${API_BASE}/auth/me`, {
      headers: authHeaders(request),
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        detail: `Cannot reach the agent API at ${API_BASE}: ${
          error instanceof Error ? error.message : String(error)
        }`,
      },
      { status: 502 },
    );
  }
}
