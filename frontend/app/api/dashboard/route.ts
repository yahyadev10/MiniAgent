import { NextResponse } from "next/server";

const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const params = new URLSearchParams();
  params.set("limit", url.searchParams.get("limit") ?? "20");

  const action = url.searchParams.get("action");
  if (action && action !== "all") {
    params.set("action", action);
  }

  const q = url.searchParams.get("q");
  if (q) {
    params.set("q", q);
  }

  try {
    const response = await fetch(`${API_BASE}/dashboard?${params.toString()}`, {
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
