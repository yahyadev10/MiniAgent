import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

DB_PATH = os.getenv("HISTORY_DB_PATH", os.path.join("data", "history.db"))


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                message TEXT NOT NULL,
                action TEXT NOT NULL,
                results TEXT NOT NULL,
                final TEXT NOT NULL,
                steps TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                artifacts TEXT NOT NULL DEFAULT '[]',
                owner TEXT NOT NULL DEFAULT 'public'
            )
            """
        )
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(runs)").fetchall()
        }
        if "artifacts" not in columns:
            conn.execute(
                "ALTER TABLE runs ADD COLUMN artifacts TEXT NOT NULL DEFAULT '[]'"
            )
        if "owner" not in columns:
            conn.execute(
                "ALTER TABLE runs ADD COLUMN owner TEXT NOT NULL DEFAULT 'public'"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_created_at "
            "ON runs(created_at DESC)"
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_run(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "message": row["message"],
        "action": row["action"],
        "results": json.loads(row["results"]),
        "final": row["final"],
        "steps": json.loads(row["steps"]),
        "duration_ms": row["duration_ms"],
        "created_at": row["created_at"],
        "artifacts": json.loads(row["artifacts"] or "[]"),
        "owner": row["owner"] if "owner" in row.keys() else "public",
    }


def save_run(run: dict[str, Any]) -> None:
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO runs
                (id, message, action, results, final, steps, duration_ms,
                 created_at, artifacts, owner)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run["id"],
                run["message"],
                run["action"],
                json.dumps(run["results"], ensure_ascii=False),
                run["final"],
                json.dumps(run["steps"], ensure_ascii=False),
                run["duration_ms"],
                run["created_at"],
                json.dumps(run.get("artifacts", []), ensure_ascii=False),
                run.get("owner", "public"),
            ),
        )


def _where(action: str | None, q: str | None, owner: str = "public") -> tuple[str, list[Any]]:
    clauses: list[str] = ["owner = ?"]
    params: list[Any] = [owner]
    if action and action != "all":
        clauses.append("action = ?")
        params.append(action)
    if q:
        clauses.append("(message LIKE ? OR final LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])
    return (f"WHERE {' AND '.join(clauses)}" if clauses else ""), params


def list_runs(
    limit: int = 20,
    action: str | None = None,
    q: str | None = None,
    owner: str = "public",
) -> list[dict[str, Any]]:
    where, params = _where(action, q, owner)
    with _db() as conn:
        rows = conn.execute(
            f"SELECT * FROM runs {where} ORDER BY created_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
    return [_row_to_run(row) for row in rows]


def get_run(run_id: str, owner: str | None = None) -> dict[str, Any] | None:
    with _db() as conn:
        if owner is None:
            row = conn.execute(
                "SELECT * FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM runs WHERE id = ? AND owner = ?",
                (run_id, owner),
            ).fetchone()
    return _row_to_run(row) if row else None


def get_stats(
    action: str | None = None,
    q: str | None = None,
    owner: str = "public",
) -> dict[str, Any]:
    where, params = _where(action, q, owner)
    with _db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM runs {where}", params
        ).fetchone()["n"]
        avg = conn.execute(
            f"SELECT COALESCE(AVG(duration_ms), 0) AS avg FROM runs {where}",
            params,
        ).fetchone()["avg"]
        last = conn.execute(
            f"SELECT MAX(created_at) AS last FROM runs {where}", params
        ).fetchone()["last"]
        rows = conn.execute(
            f"SELECT action, COUNT(*) AS n FROM runs {where} GROUP BY action",
            params,
        ).fetchall()
        artifacts_total = sum(
            len(json.loads(row["artifacts"] or "[]"))
            for row in conn.execute(
                f"SELECT artifacts FROM runs {where}", params
            ).fetchall()
        )

    return {
        "total": total,
        "avg_duration_ms": int(avg),
        "by_action": {row["action"]: row["n"] for row in rows},
        "artifacts_total": artifacts_total,
        "last_run_at": last,
    }


def get_dashboard(
    limit: int = 20,
    action: str | None = None,
    q: str | None = None,
    owner: str = "public",
) -> dict[str, Any]:
    return {
        "stats": get_stats(action, q, owner),
        "items": list_runs(limit, action, q, owner),
    }


def render_report_markdown(run: dict[str, Any]) -> str:
    lines = [
        "# Agent Run Report",
        "",
        f"- **Run ID**: `{run['id']}`",
        f"- **Date**: {run['created_at']}",
        f"- **Action**: `{run['action']}`",
        f"- **Duration**: {run['duration_ms']} ms",
        "",
        "## Request",
        "",
        run["message"],
        "",
        "## Trace",
        "",
        "| Step | Status | Duration |",
        "|---|---|---|",
    ]
    for step in run["steps"]:
        lines.append(
            f"| {step.get('node', '?')} | {step.get('status', '?')} "
            f"| {step.get('ms', 0)} ms |"
        )
    lines.extend(["", "## Results", ""])
    for result in run["results"]:
        lines.extend(["```", result, "```", ""])

    artifacts = run.get("artifacts", [])
    if artifacts:
        lines.extend(["## Artifacts", ""])
        for artifact in artifacts:
            lines.append(
                f"- `{artifact.get('kind', 'file')}`: "
                f"`{artifact.get('filename', '?')}`"
            )
        lines.append("")

    lines.extend(["## Final answer", "", run["final"], ""])
    return "\n".join(lines)
