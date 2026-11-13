from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class JobStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    invoice_path TEXT NOT NULL,
                    purchase_order_path TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            connection.execute(
                "CREATE TABLE IF NOT EXISTS batches (batch_id TEXT PRIMARY KEY, job_ids_json TEXT NOT NULL)"
            )

    def create(self, job_id: str, invoice_path: str, purchase_order_path: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)",
                (job_id, "queued", invoice_path, purchase_order_path, now, now),
            )

    def update(
        self,
        job_id: str,
        *,
        status: str,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        payload = json.dumps(result) if result is not None else None
        with self._lock, self._connect() as connection:
            connection.execute(
                """UPDATE jobs
                SET status=?, result_json=COALESCE(?, result_json), error=?, updated_at=?
                WHERE job_id=?""",
                (status, payload, error, now, job_id),
            )

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        raw_result = item.pop("result_json")
        item["result"] = json.loads(raw_result) if raw_result else None
        return item

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT job_id, status, error, created_at, updated_at
                FROM jobs ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def estimated_spend_usd(self) -> float:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT result_json FROM jobs WHERE result_json IS NOT NULL"
            ).fetchall()
        total = 0.0
        for row in rows:
            result = json.loads(row["result_json"])
            for document_key in ("invoice", "purchase_order", "extraction"):
                metadata = result.get(document_key, {}).get("provider_metadata", {})
                total += float(metadata.get("estimated_cost_usd", 0.0))
        return round(total, 6)

    def create_batch(self, batch_id: str, documents: list[tuple[str, str]]) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            connection.executemany("INSERT INTO jobs VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)",
                [(job_id, "queued", path, "", now, now) for job_id, path in documents])
            connection.execute("INSERT INTO batches VALUES (?, ?)",
                               (batch_id, json.dumps([job_id for job_id, _ in documents])))

    def batch(self, batch_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT job_ids_json FROM batches WHERE batch_id=?", (batch_id,)
            ).fetchone()
        if row is None:
            return None
        jobs = [self.get(job_id) for job_id in json.loads(row[0])]
        for job in jobs:
            job.pop("invoice_path")
            job.pop("purchase_order_path")
        counts = {status: sum(job["status"] == status for job in jobs)
                  for status in ("queued", "processing", "completed", "failed")}
        return {"batch_id": batch_id, "total": len(jobs), **counts, "jobs": jobs,
                "done": counts["completed"] + counts["failed"] == len(jobs)}

    def incomplete_jobs(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs WHERE status IN ('queued', 'processing') ORDER BY created_at"
            ).fetchall()
        return [dict(row) for row in rows]
