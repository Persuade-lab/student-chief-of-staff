"""Application startup and shutdown for the background monitor."""

from __future__ import annotations

from src.runtime.monitor import run_monitor_cycle
from src.runtime.scheduler import BackgroundScheduler
from src.storage.database import initialize_database


class RuntimeOrchestrator:
    """Initialize storage, run once, then keep monitoring in background."""

    def __init__(
        self,
        sync_interval_seconds: int = 5 * 60,
    ):
        self.scheduler = BackgroundScheduler(
            interval_seconds=sync_interval_seconds
        )
        self.startup_result: dict | None = None

    def start(self) -> dict:
        """
        Run one full cycle synchronously, then schedule future cycles.

        Returning the result makes startup easy to test and easy to show in a
        demo without reading terminal output.
        """

        initialize_database()
        print("Running initial monitor cycle...")
        self.startup_result = run_monitor_cycle()
        self._print_startup_result(self.startup_result)
        self.scheduler.start()

        return self.startup_result

    def stop(self) -> None:
        """Stop future monitor cycles."""

        self.scheduler.stop()

    def status(self) -> dict:
        """Expose scheduler status to the CLI or agent interface."""

        return self.scheduler.status()

    def _print_startup_result(self, result: dict) -> None:
        sync = result["sync"]
        processing = result["processing"]

        for source in ("gmail", "calendar"):
            source_result = sync[source]

            if source_result["success"]:
                print(
                    f"{source.title()} synchronized: "
                    f"{source_result['count']} item(s)"
                )
            else:
                print(
                    f"{source.title()} synchronization failed: "
                    f"{source_result['error']}"
                )

        for source in ("emails", "calendar"):
            source_result = processing[source]

            if source_result["success"]:
                details = source_result["result"]
                print(
                    f"{source.title()} processed: "
                    f"{details.get('processed', 0)}"
                )
            else:
                print(
                    f"{source.title()} processing failed: "
                    f"{source_result['error']}"
                )