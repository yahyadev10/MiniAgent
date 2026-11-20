import { NextResponse } from "next/server";

const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export async function GET() {
  try {
    const response = await fetch(`${API_BASE}/eval`, { cache: "no-store" });
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
