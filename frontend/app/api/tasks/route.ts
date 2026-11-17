import { NextResponse } from "next/server";

const API_URL = process.env.API_URL ?? "http://localhost:8000/tasks";
const MAX_DATA = 200_000;
const MAX_FILENAME = 200;
const MAX_MESSAGE = 20_000;
const MAX_SHORT = 200;
const MAX_TO = 320;

const ACTIONS = new Set(["auto", "email", "report", "both"]);

type Payload = Record<string, unknown>;

function readString(
  body: Payload,
  key: string,
  max: number,
  required = false,
): { value?: string; error?: NextResponse } {
  const raw = body[key];
  if (raw === undefined || raw === null) {
    if (required) {
      return {
        error: NextResponse.json(
          { detail: `Field '${key}' is required.` },
          { status: 400 },
        ),
      };
    }
    return {};
  }
  if (typeof raw !== "string") {
    return {
      error: NextResponse.json(
        { detail: `Field '${key}' must be a string.` },
        { status: 400 },
      ),
    };
  }
  const value = raw.trim();
  if (required && value.length === 0) {
    return {
      error: NextResponse.json(
        { detail: `Field '${key}' cannot be empty.` },
        { status: 400 },
      ),
    };
  }
  if (raw.length > max) {
    return {
      error: NextResponse.json(
        { detail: `Field '${key}' exceeds ${max} characters.` },
        { status: 413 },
      ),
    };
  }
  return { value };
}

export async function POST(request: Request) {
  let payload: unknown;

  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body." }, { status: 400 });
  }

  const body =
    typeof payload === "object" && payload !== null
      ? (payload as Payload)
      : {};

  const action =
    typeof body.action === "string" && ACTIONS.has(body.action)
      ? body.action
      : "auto";

  const message = readString(body, "message", MAX_MESSAGE);
  if (message.error) {
    return message.error;
  }
  if (action === "auto" && !message.value) {
    return NextResponse.json(
      { detail: "Field 'message' is required when action is 'auto'." },
      { status: 400 },
    );
  }

  const to = readString(body, "to", MAX_TO, action === "email" || action === "both");
  if (to.error) {
    return to.error;
  }
  const subject = readString(body, "subject", MAX_SHORT);
  if (subject.error) {
    return subject.error;
  }
  const emailBody = readString(body, "body", MAX_MESSAGE);
  if (emailBody.error) {
    return emailBody.error;
  }
  const title = readString(body, "title", MAX_SHORT);
  if (title.error) {
    return title.error;
  }
  const content = readString(body, "content", MAX_MESSAGE);
  if (content.error) {
    return content.error;
  }
  const data = readString(body, "data", MAX_DATA);
  if (data.error) {
    return data.error;
  }
  const filename = readString(body, "filename", MAX_FILENAME);
  if (filename.error) {
    return filename.error;
  }

  const outbound: Payload = { action };
  if (message.value) outbound.message = message.value;
  if (to.value) outbound.to = to.value;
  if (subject.value) outbound.subject = subject.value;
  if (emailBody.value) outbound.body = emailBody.value;
  if (title.value) outbound.title = title.value;
  if (content.value) outbound.content = content.value;
  if (data.value) outbound.data = data.value;
  if (filename.value) outbound.filename = filename.value;

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(outbound),
      cache: "no-store",
    });

    const responseData = await response.json().catch(() => ({}));
    return NextResponse.json(responseData, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        detail: `Cannot reach the agent API at ${API_URL}: ${
          error instanceof Error ? error.message : String(error)
        }`,
      },
      { status: 502 },
    );
  }
}
