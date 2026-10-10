"""Gerenciador de tarefas longas (transcrição) em segundo plano."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from rita_academic.db import Database
from rita_academic.textutil import now_iso


class JobManager:
    def __init__(self, db: Database, max_workers: int = 1):
        self.db = db
        self.pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="rita-job")
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def submit(self, kind: str, fn: Callable[[JobHandle], dict[str, Any]]) -> dict[str, Any]:
        job_id = "job-" + uuid.uuid4().hex[:10]
        now = now_iso()
        job = {"id": job_id, "kind": kind, "status": "queued", "progress": 0.0, "total": None,
               "message": "na fila", "result": None, "created_at": now, "updated_at": now}
        self.db.upsert_job(job)
        ev = threading.Event()
        with self._lock:
            self._cancel[job_id] = ev
        handle = JobHandle(self, job_id, ev)
        self.pool.submit(self._run, handle, fn)
        return job

    def _run(self, handle: JobHandle, fn: Callable[[JobHandle], dict[str, Any]]) -> None:
        handle.update(status="running", message="iniciando")
        try:
            result = fn(handle)
            if handle.cancelled():
                handle.update(status="cancelled", message="cancelado", result=result)
            else:
                handle.update(status="done", progress=handle.total or handle.progress,
                              message="concluído", result=result)
        except Exception as exc:  # noqa: BLE001
            handle.update(status="error", message=f"{type(exc).__name__}: {exc}")
        finally:
            with self._lock:
                self._cancel.pop(handle.job_id, None)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            ev = self._cancel.get(job_id)
        if ev:
            ev.set()
            job = self.db.get_job(job_id)
            if job and job["status"] == "queued":
                self._update(job_id, status="cancelled", message="cancelado antes de iniciar")
            return True
        return False

    def _update(self, job_id: str, **fields: Any) -> None:
        job = self.db.get_job(job_id)
        if not job:
            return
        job.update(fields)
        job["updated_at"] = now_iso()
        self.db.upsert_job(job)

    def shutdown(self, wait: bool = True) -> None:
        with self._lock:
            for ev in self._cancel.values():
                ev.set()
        self.pool.shutdown(wait=wait, cancel_futures=True)


class JobHandle:
    def __init__(self, manager: JobManager, job_id: str, cancel_event: threading.Event):
        self.manager, self.job_id, self._ev = manager, job_id, cancel_event
        self.progress: float = 0.0
        self.total: float | None = None

    def cancelled(self) -> bool:
        return self._ev.is_set()

    def report(self, progress: float, total: float | None = None, message: str = "") -> None:
        self.progress, self.total = progress, total
        self.manager._update(self.job_id, progress=progress, total=total, message=message)

    def update(self, **fields: Any) -> None:
        self.manager._update(self.job_id, **fields)
