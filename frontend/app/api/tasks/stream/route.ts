import { authHeaders } from "@/lib/server-api";

const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export async function GET(request: Request) {
  const url = new URL(request.url);
  try {
    const response = await fetch(
      `${API_BASE}/tasks/stream?${url.searchParams.toString()}`,
      {
        headers: authHeaders(request),
        cache: "no-store",
      },
    );
    return new Response(response.body, {
      status: response.status,
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (error) {
    return Response.json(
      {
        detail: `Cannot reach the agent API at ${API_BASE}: ${
          error instanceof Error ? error.message : String(error)
        }`,
      },
      { status: 502 },
    );
  }
}
