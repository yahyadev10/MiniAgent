import { NextResponse } from "next/server";

import { authHeaders } from "@/lib/server-api";

const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;

  if (!id || !/^[a-zA-Z0-9_-]+$/.test(id)) {
    return NextResponse.json({ detail: "Invalid run id." }, { status: 400 });
  }

  try {
    const response = await fetch(`${API_BASE}/history/${encodeURIComponent(id)}`, {
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
