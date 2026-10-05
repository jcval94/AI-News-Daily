from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable

from pipeline.schema_validation import validate_payload


DEFAULT_INTERVAL_SECONDS = 5.0
DEFAULT_STALE_SECONDS = 30.0


def build_heartbeat(
    *,
    job_id: str,
    operation: str,
    status: str,
    started_at: str,
    now: str,
    finished_at: str | None = None,
    runner_pid: int | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "job_id": str(job_id),
        "operation": str(operation),
        "status": str(status),
        "started_at": str(started_at),
        "last_heartbeat_at": str(now),
        "finished_at": finished_at,
        "runner_pid": int(runner_pid or os.getpid()),
        "privacy": {
            "absolute_paths_persisted": False,
            "raw_media_uploaded": False,
        },
    }
    validate_payload(payload, "local/local_heartbeat.schema.json")
    return payload


def write_heartbeat(path: Path, payload: dict[str, Any]) -> Path:
    validate_payload(payload, "local/local_heartbeat.schema.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


class Heartbeat:
    def __init__(
        self,
        path: Path,
        *,
        job_id: str,
        operation: str,
        started_at: str,
        now_fn: Callable[[], str],
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self.path = path
        self.job_id = str(job_id)
        self.operation = str(operation)
        self.started_at = str(started_at)
        self.now_fn = now_fn
        self.interval_seconds = max(0.05, float(interval_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None

    def _write(self, status: str, *, finished_at: str | None = None) -> None:
        write_heartbeat(
            self.path,
            build_heartbeat(
                job_id=self.job_id,
                operation=self.operation,
                status=status,
                started_at=self.started_at,
                now=self.now_fn(),
                finished_at=finished_at,
            ),
        )

    def _worker(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self._write("running")
            except Exception as exc:
                # A missing heartbeat should become stale and visible in status,
                # but must not hide the underlying media/Resolve process result.
                self.last_error = str(exc)
                return

    def start(self) -> None:
        # Initial write is fail-closed: do not start a side-effecting job when
        # the harness cannot establish its observable run state.
        self._write("running")
        self._thread = threading.Thread(
            target=self._worker,
            name=f"local-heartbeat-{self.job_id}",
            daemon=True,
        )
        self._thread.start()

    def finish(self, status: str) -> bool:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 2))
        try:
            finished_at = self.now_fn()
            self._write(status, finished_at=finished_at)
            return True
        except Exception as exc:
            self.last_error = str(exc)
            return False
