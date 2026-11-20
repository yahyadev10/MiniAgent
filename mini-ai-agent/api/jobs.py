import asyncio
import time
import uuid
from typing import Any, Awaitable, Callable

JOBS: dict[str, dict[str, Any]] = {}


def submit(factory: Callable[[], Awaitable[Any]]) -> str:
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {
        "id": job_id,
        "status": "queued",
        "progress": 0,
        "result": None,
        "error": None,
        "created_at": time.time(),
    }
    asyncio.create_task(_run(job_id, factory))
    return job_id


async def _run(job_id: str, factory: Callable[[], Awaitable[Any]]) -> None:
    job = JOBS[job_id]
    job["status"] = "running"
    job["progress"] = 10
    try:
        result = await factory()
        job["result"] = result
        job["progress"] = 100
        job["status"] = "done"
    except Exception as exc:
        job["error"] = str(exc)
        job["status"] = "failed"


def status(job_id: str) -> dict[str, Any] | None:
    return JOBS.get(job_id)
