import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Literal

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator

from agent.graph import build_graph
from api import auth, history, jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "artifacts"))
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Mini AI Task Agent", version="2.0.0")
agent_graph = build_graph()
history.init_db()
auth.init_db()


class TaskRequest(BaseModel):
    message: str | None = Field(
        default=None,
        max_length=20_000,
        description="Natural-language request, used in auto mode or as fallback.",
        examples=["Send an email to John about the project"],
    )
    action: Literal["auto", "email", "report", "both"] = Field(
        default="auto",
        description="Explicit action. 'auto' lets the local LLM classify.",
    )
    to: str | None = Field(default=None, max_length=320)
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=20_000)
    title: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, max_length=20_000)
    data: str | None = Field(
        default=None,
        max_length=200_000,
        description="Optional CSV/JSON/text content used to build the report.",
    )
    filename: str | None = Field(
        default=None,
        max_length=200,
        description="Optional original filename for the uploaded data.",
    )

    @model_validator(mode="after")
    def validate_request(self) -> "TaskRequest":
        if self.action == "auto" and not (self.message or "").strip():
            raise ValueError("message is required when action is 'auto'.")
        if self.action in {"email", "both"} and not (self.to or "").strip():
            raise ValueError("to is required for email actions.")
        return self


class Step(BaseModel):
    node: str
    status: str
    ms: int


class Artifact(BaseModel):
    kind: str
    filename: str
    size: int = 0
    url: str


class ArtifactInfo(BaseModel):
    kind: str
    filename: str
    size: int
    modified_at: str
    url: str


class TaskResponse(BaseModel):
    id: str
    message: str
    action: str
    results: list[str]
    final: str
    steps: list[Step]
    duration_ms: int
    created_at: str
    artifacts: list[Artifact] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)


class StatsResponse(BaseModel):
    total: int
    avg_duration_ms: int
    by_action: dict[str, int]
    artifacts_total: int = 0
    last_run_at: str | None


class DashboardResponse(BaseModel):
    stats: StatsResponse
    items: list[TaskResponse]


class CapabilitiesResponse(BaseModel):
    version: str
    model: str
    actions: list[str]
    email_mode: Literal["smtp", "eml"]
    artifacts_total: int
    max_data_chars: int


class AuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    username: str


class UserResponse(BaseModel):
    username: str
    created_at: str | None = None


class JobResponse(BaseModel):
    id: str
    status: str
    progress: int


class JobStatusResponse(BaseModel):
    id: str
    status: str
    progress: int
    result: TaskResponse | None = None
    error: str | None = None
    created_at: str


def _current_user(authorization: str | None) -> str:
    if not authorization:
        return "public"
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization header.")
    return auth.decode_token(token)


def _initial_state(request: TaskRequest) -> dict[str, Any]:
    return {
        "message": request.message or "",
        "data": request.data or "",
        "filename": request.filename or "",
        "action_hint": request.action,
        "to": request.to or "",
        "subject": request.subject or "",
        "body": request.body or "",
        "title": request.title or "",
        "content": request.content or "",
        "search_query": "",
        "sources": [],
        "citations": [],
        "action": "",
        "results": [],
        "artifacts": [],
        "steps": [],
        "final": "",
    }


def _task_summary(request: TaskRequest) -> str:
    return (
        (request.message or "").strip()
        or (request.subject or "").strip()
        or (request.title or "").strip()
        or f"{request.action} task"
    )


def _artifacts_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {**item, "url": f"/artifacts/{item['filename']}"}
        for item in state.get("artifacts", [])
        if item.get("filename")
    ]


def _task_from_state(
    state: dict[str, Any], run_id: str, summary: str, duration_ms: int, owner: str
) -> dict[str, Any]:
    return {
        "id": run_id,
        "message": summary,
        "action": state.get("action", "unknown"),
        "results": state.get("results", []),
        "final": state.get("final", ""),
        "steps": state.get("steps", []),
        "duration_ms": duration_ms,
        "created_at": history.utc_now_iso(),
        "artifacts": _artifacts_from_state(state),
        "citations": state.get("citations", []),
        "owner": owner,
    }


async def _run_agent(request: TaskRequest, owner: str = "public") -> TaskResponse:
    started = time.perf_counter()
    summary = _task_summary(request)
    try:
        state = await agent_graph.ainvoke(_initial_state(request))
    except Exception as exc:
        logging.exception("Agent execution failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    run = _task_from_state(
        state,
        uuid.uuid4().hex[:12],
        summary,
        int((time.perf_counter() - started) * 1000),
        owner,
    )
    try:
        history.save_run(run)
    except Exception:
        logging.exception("Unable to persist run history")
    return TaskResponse(**run)


def _kind_for(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return {"pdf": "pdf", "html": "html", "eml": "eml"}.get(suffix, suffix or "file")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/eval")
async def eval_suite() -> dict[str, Any]:
    from evals.run_eval import run

    return run()


@app.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities() -> CapabilitiesResponse:
    artifacts_total = sum(1 for path in ARTIFACTS_DIR.iterdir() if path.is_file())
    return CapabilitiesResponse(
        version=app.version,
        model=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b"),
        actions=["auto", "email", "report", "both"],
        email_mode="smtp" if os.getenv("SMTP_HOST") else "eml",
        artifacts_total=artifacts_total,
        max_data_chars=200_000,
    )


@app.post("/auth/register", response_model=UserResponse)
async def register(request: AuthRequest) -> UserResponse:
    return UserResponse(**auth.register(request.username, request.password))


@app.post("/auth/login", response_model=TokenResponse)
async def login(request: AuthRequest) -> TokenResponse:
    return TokenResponse(**auth.login(request.username, request.password))


@app.get("/auth/me", response_model=UserResponse)
async def me(authorization: str | None = Header(default=None)) -> UserResponse:
    return UserResponse(username=_current_user(authorization))


@app.post("/tasks", response_model=TaskResponse)
async def run_task(
    request: TaskRequest,
    authorization: str | None = Header(default=None),
) -> TaskResponse:
    """Run the LangGraph agent for one structured or natural-language task."""
    return await _run_agent(request, _current_user(authorization))


@app.post("/tasks/async", response_model=JobResponse, status_code=202)
async def run_task_async(
    request: TaskRequest,
    authorization: str | None = Header(default=None),
) -> JobResponse:
    owner = _current_user(authorization)
    job_id = jobs.submit(lambda: _run_agent(request, owner))
    job = jobs.status(job_id) or {}
    return JobResponse(id=job_id, status=str(job.get("status", "queued")), progress=0)


@app.get("/tasks/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    authorization: str | None = Header(default=None),
) -> JobStatusResponse:
    _current_user(authorization)
    job = jobs.status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        id=job["id"],
        status=job["status"],
        progress=int(job["progress"]),
        result=job.get("result"),
        error=job.get("error"),
        created_at=datetime.fromtimestamp(job["created_at"], timezone.utc).isoformat(
            timespec="seconds"
        ),
    )


@app.get("/tasks/stream")
async def stream_task(
    message: str | None = Query(None, max_length=20_000),
    action: Literal["auto", "email", "report", "both"] = "auto",
    to: str | None = Query(None, max_length=320),
    subject: str | None = Query(None, max_length=200),
    body: str | None = Query(None, max_length=20_000),
    title: str | None = Query(None, max_length=200),
    content: str | None = Query(None, max_length=20_000),
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    """SSE endpoint: emit each graph node update as soon as it completes."""
    owner = _current_user(authorization)
    request = TaskRequest(
        message=message or "",
        action=action,
        to=to,
        subject=subject,
        body=body,
        title=title,
        content=content,
    )
    started = time.perf_counter()

    async def events() -> AsyncIterator[str]:
        def emit(event: str, data: dict[str, Any]) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        try:
            yield emit("start", {"message": _task_summary(request)})
            final_state: dict[str, Any] = {
                "steps": [],
                "results": [],
                "artifacts": [],
                "citations": [],
            }
            accumulators = {"steps", "results", "artifacts", "citations"}
            async for update in agent_graph.astream(
                _initial_state(request), stream_mode="updates"
            ):
                for node, payload in update.items():
                    if not isinstance(payload, dict):
                        continue
                    for key, value in payload.items():
                        if key in accumulators and isinstance(value, list):
                            final_state[key].extend(value)
                        else:
                            final_state[key] = value
                    steps = payload.get("steps", [])
                    results = payload.get("results", [])
                    yield emit(
                        "step",
                        {
                            "node": node,
                            "steps": steps,
                            "results": results,
                        },
                    )
            run = _task_from_state(
                final_state,
                uuid.uuid4().hex[:12],
                _task_summary(request),
                int((time.perf_counter() - started) * 1000),
                owner,
            )
            try:
                history.save_run(run)
            except Exception:
                logging.exception("Unable to persist streamed run history")
            yield emit("done", TaskResponse(**run).model_dump())
        except Exception as exc:
            logging.exception("Streamed agent execution failed")
            yield emit("error", {"error": str(exc)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    limit: int = Query(20, ge=1, le=100),
    action: str | None = Query(None),
    q: str | None = Query(None, max_length=200),
    authorization: str | None = Header(default=None),
) -> DashboardResponse:
    owner = _current_user(authorization)
    return DashboardResponse(**history.get_dashboard(limit, action, q, owner))


@app.get("/stats", response_model=StatsResponse)
async def stats(
    action: str | None = Query(None),
    q: str | None = Query(None, max_length=200),
    authorization: str | None = Header(default=None),
) -> StatsResponse:
    owner = _current_user(authorization)
    return StatsResponse(**history.get_stats(action, q, owner))


@app.get("/history", response_model=list[TaskResponse])
async def list_history(
    limit: int = Query(20, ge=1, le=100),
    action: str | None = Query(None),
    q: str | None = Query(None, max_length=200),
    authorization: str | None = Header(default=None),
) -> list[TaskResponse]:
    owner = _current_user(authorization)
    return [
        TaskResponse(**item) for item in history.list_runs(limit, action, q, owner)
    ]


@app.get("/history/{run_id}", response_model=TaskResponse)
async def get_history_run(
    run_id: str,
    authorization: str | None = Header(default=None),
) -> TaskResponse:
    owner = _current_user(authorization)
    run = history.get_run(run_id, owner)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return TaskResponse(**run)


@app.get("/history/{run_id}/report", response_class=PlainTextResponse)
async def download_report(
    run_id: str,
    authorization: str | None = Header(default=None),
) -> PlainTextResponse:
    owner = _current_user(authorization)
    run = history.get_run(run_id, owner)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    markdown = history.render_report_markdown(run)
    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="agent-run-{run_id}.md"'
        },
    )


@app.get("/artifacts", response_model=list[ArtifactInfo])
async def list_artifacts(
    limit: int = Query(100, ge=1, le=500),
) -> list[ArtifactInfo]:
    paths = sorted(
        (path for path in ARTIFACTS_DIR.iterdir() if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:limit]
    return [
        ArtifactInfo(
            kind=_kind_for(path),
            filename=path.name,
            size=path.stat().st_size,
            modified_at=datetime.fromtimestamp(
                path.stat().st_mtime, timezone.utc
            ).isoformat(timespec="seconds"),
            url=f"/artifacts/{path.name}",
        )
        for path in paths
    ]


@app.get("/artifacts/{filename}")
async def get_artifact(filename: str) -> FileResponse:
    safe_name = os.path.basename(filename)
    path = ARTIFACTS_DIR / safe_name
    if not safe_name or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path, filename=safe_name)
