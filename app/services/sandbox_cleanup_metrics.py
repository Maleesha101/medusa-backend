"""Metrics hooks for sandbox cleanup operational visibility."""

from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True, slots=True)
class SandboxCleanupMetricsSnapshot:
    """Immutable in-process snapshot of cleanup outcomes."""

    batches: int
    processed: int
    cleaned: int
    failed: int


class SandboxCleanupMetrics:
    """Thread-safe in-process counters.

    These counters are process-local and reset on restart. Production
    deployments should export equivalent counters to their monitoring backend.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._batches = 0
        self._processed = 0
        self._cleaned = 0
        self._failed = 0

    def observe_batch(self, result: dict[str, int]) -> None:
        """Record one reconciliation batch."""
        with self._lock:
            self._batches += 1
            self._processed += result["processed"]
            self._cleaned += result["cleaned"]
            self._failed += result["failed"]

    def snapshot(self) -> SandboxCleanupMetricsSnapshot:
        """Return a consistent read-only snapshot."""
        with self._lock:
            return SandboxCleanupMetricsSnapshot(
                batches=self._batches,
                processed=self._processed,
                cleaned=self._cleaned,
                failed=self._failed,
            )


sandbox_cleanup_metrics = SandboxCleanupMetrics()
