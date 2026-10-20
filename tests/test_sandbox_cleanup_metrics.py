from app.services.sandbox_cleanup_metrics import SandboxCleanupMetrics


def test_cleanup_metrics_accumulate_batch_outcomes() -> None:
    metrics = SandboxCleanupMetrics()

    metrics.observe_batch({"processed": 4, "cleaned": 3, "failed": 1})
    metrics.observe_batch({"processed": 2, "cleaned": 2, "failed": 0})

    snapshot = metrics.snapshot()
    assert snapshot.batches == 2
    assert snapshot.processed == 6
    assert snapshot.cleaned == 5
    assert snapshot.failed == 1


def test_cleanup_metrics_snapshot_is_immutable() -> None:
    metrics = SandboxCleanupMetrics()
    snapshot = metrics.snapshot()

    assert snapshot.batches == 0
    assert snapshot.processed == 0
    assert snapshot.cleaned == 0
    assert snapshot.failed == 0
