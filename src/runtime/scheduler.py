"""Threaded scheduler for repeated full monitor cycles."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from src.runtime.monitor import run_monitor_cycle
from src.storage.state import set_state


DEFAULT_SYNC_INTERVAL_SECONDS = 5 * 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BackgroundScheduler:
    """
    Run one full monitor cycle at a fixed interval.

    The orchestrator performs the first cycle before start(), so this thread
    waits one interval before the next cycle. That avoids a duplicate startup
    sync and notification burst.
    """

    def __init__(
        self,
        interval_seconds: int = DEFAULT_SYNC_INTERVAL_SECONDS,
    ):
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")

        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._last_cycle_started_at: str | None = None
        self._last_cycle_finished_at: str | None = None
        self._last_result: dict[str, Any] | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        """Start the background thread if it is not already running."""

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="student-chief-of-staff-monitor",
                daemon=True,
            )
            self._thread.start()

        self._persist_status()

    def stop(self) -> None:
        """Request a clean shutdown and wait briefly for the thread."""

        self._stop_event.set()

        with self._lock:
            thread = self._thread

        if thread is not None:
            thread.join(
                timeout=self.interval_seconds + 5
            )

        self._persist_status()

    def status(self) -> dict[str, Any]:
        """Return a serializable runtime status snapshot."""

        with self._lock:
            running = bool(
                self._thread is not None
                and self._thread.is_alive()
            )

            return {
                "running": running,
                "interval_seconds": self.interval_seconds,
                "last_cycle_started_at": (
                    self._last_cycle_started_at
                ),
                "last_cycle_finished_at": (
                    self._last_cycle_finished_at
                ),
                "last_error": self._last_error,
            }

    def _persist_status(self) -> None:
        try:
            set_state("scheduler_status", self.status())
        except Exception:
            # A status write must not kill the monitoring thread.
            pass

    def _run(self) -> None:
        while not self._stop_event.wait(
            self.interval_seconds
        ):
            with self._lock:
                self._last_cycle_started_at = _now()
                self._last_error = None

            self._persist_status()

            try:
                result = run_monitor_cycle()

                with self._lock:
                    self._last_result = result

            except Exception as error:
                with self._lock:
                    self._last_error = str(error)

            finally:
                with self._lock:
                    self._last_cycle_finished_at = _now()

                self._persist_status()