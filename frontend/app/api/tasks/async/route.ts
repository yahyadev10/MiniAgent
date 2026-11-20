import { NextResponse } from "next/server";

import { jsonHeaders } from "@/lib/server-api";

const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export async function POST(request: Request) {
  try {
    const response = await fetch(`${API_BASE}/tasks/async`, {
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
