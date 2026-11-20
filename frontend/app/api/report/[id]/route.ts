import { NextResponse } from "next/server";

import { authHeaders } from "@/lib/server-api";

const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;

  try {
    const response = await fetch(
      `${API_BASE}/history/${encodeURIComponent(id)}/report`,
      { headers: authHeaders(request), cache: "no-store" },
    );

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      return NextResponse.json(data, { status: response.status });
    }

    const body = await response.text();
    return new NextResponse(body, {
      status: 200,
      headers: {
        "Content-Type": "text/markdown; charset=utf-8",
        "Content-Disposition": `attachment; filename="agent-run-${id}.md"`,
      },
    });
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
