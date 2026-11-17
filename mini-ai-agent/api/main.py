import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field, model_validator

from agent.graph import build_graph
from api import history

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "artifacts"))
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Mini AI Task Agent", version="1.3.0")
agent_graph = build_graph()
history.init_db()


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


def _kind_for(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return {"pdf": "pdf", "html": "html", "eml": "eml"}.get(suffix, suffix or "file")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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


@app.post("/tasks", response_model=TaskResponse)
async def run_task(request: TaskRequest) -> TaskResponse:
    """Run the LangGraph agent for one structured or natural-language task."""
    started = time.perf_counter()
    summary = (
        (request.message or "").strip()
        or (request.subject or "").strip()
        or (request.title or "").strip()
        or f"{request.action} task"
    )
    try:
        state = await agent_graph.ainvoke(
            {
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
                "action": "",
                "results": [],
                "artifacts": [],
                "steps": [],
                "final": "",
            }
        )
    except Exception as exc:
        logging.exception("Agent execution failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    artifacts = [
        {
            **item,
            "url": f"/artifacts/{item['filename']}",
        }
        for item in state.get("artifacts", [])
        if item.get("filename")
    ]

    run = {
        "id": uuid.uuid4().hex[:12],
        "message": summary,
        "action": state.get("action", "unknown"),
        "results": state.get("results", []),
        "final": state.get("final", ""),
        "steps": state.get("steps", []),
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "created_at": history.utc_now_iso(),
        "artifacts": artifacts,
    }

    try:
        history.save_run(run)
    except Exception:
        logging.exception("Unable to persist run history")

    return TaskResponse(**run)


@app.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    limit: int = Query(20, ge=1, le=100),
    action: str | None = Query(None),
    q: str | None = Query(None, max_length=200),
) -> DashboardResponse:
    return DashboardResponse(**history.get_dashboard(limit, action, q))


@app.get("/stats", response_model=StatsResponse)
async def stats(
    action: str | None = Query(None),
    q: str | None = Query(None, max_length=200),
) -> StatsResponse:
    return StatsResponse(**history.get_stats(action, q))


@app.get("/history", response_model=list[TaskResponse])
async def list_history(
    limit: int = Query(20, ge=1, le=100),
    action: str | None = Query(None),
    q: str | None = Query(None, max_length=200),
) -> list[TaskResponse]:
    return [
        TaskResponse(**item) for item in history.list_runs(limit, action, q)
    ]


@app.get("/history/{run_id}", response_model=TaskResponse)
async def get_history_run(run_id: str) -> TaskResponse:
    run = history.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return TaskResponse(**run)


@app.get("/history/{run_id}/report", response_class=PlainTextResponse)
async def download_report(run_id: str) -> PlainTextResponse:
    run = history.get_run(run_id)
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
