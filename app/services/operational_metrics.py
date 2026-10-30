"""Safe operational metrics for the API process and persisted sandbox lifecycle."""

import os
import shutil
import time
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.sandbox_instance import SandboxInstance
from app.services.sandbox_cleanup_metrics import sandbox_cleanup_metrics

_PROCESS_STARTED = time.monotonic()


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as stream:
            return stream.read()
    except OSError:
        return None


def _memory_metrics() -> dict[str, int | None]:
    """Read cgroup v2 limits first, then report host memory as a fallback."""
    current = _read_text("/sys/fs/cgroup/memory.current")
    maximum = _read_text("/sys/fs/cgroup/memory.max")
    if current and maximum and maximum.strip() != "max":
        try:
            used = int(current.strip())
            limit = int(maximum.strip())
            return {"used_bytes": used, "limit_bytes": limit, "percent": round(used / limit * 100, 2) if limit else None}
        except ValueError:
            pass

    meminfo = _read_text("/proc/meminfo")
    if not meminfo:
        return {"used_bytes": None, "limit_bytes": None, "percent": None}
    values = {}
    for line in meminfo.splitlines():
        key, _, value = line.partition(":")
        if key in {"MemTotal", "MemAvailable"}:
            try:
                values[key] = int(value.strip().split()[0]) * 1024
            except (ValueError, IndexError):
                continue
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    used = total - available if total is not None and available is not None else None
    return {
        "used_bytes": used,
        "limit_bytes": total,
        "percent": round(used / total * 100, 2) if used is not None and total else None,
    }


def _cpu_percent() -> float | None:
    """Return the host CPU busy percentage from Linux procfs, if available."""
    contents = _read_text("/proc/stat")
    if not contents:
        return None
    fields = contents.splitlines()[0].split()[1:]
    try:
        values = [int(value) for value in fields]
    except (ValueError, IndexError):
        return None
    if len(values) < 4:
        return None
    total = sum(values)
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return round((total - idle) / total * 100, 2) if total else None


def _metric(value: int | float | None, unit: str, observed_at: str) -> dict:
    return {
        "value": value,
        "unit": unit,
        "observed_at": observed_at,
        "available": value is not None,
        "source": "linux_procfs_or_cgroup",
    }


def _alerts(metrics: dict, settings) -> list[dict]:
    definitions = (
        ("host_cpu_percent", "cpu", settings.ops_cpu_warning_percent, settings.ops_cpu_critical_percent),
        ("memory_percent", "memory", settings.ops_memory_warning_percent, settings.ops_memory_critical_percent),
        ("disk_percent", "disk", settings.ops_disk_warning_percent, settings.ops_disk_critical_percent),
        ("sandbox_cleanup_failed", "cleanup_failures", settings.ops_cleanup_warning_count, settings.ops_cleanup_critical_count),
    )
    alerts = []
    for metric_name, alert_name, warning, critical in definitions:
        metric = metrics[metric_name]
        value = metric["value"]
        if value is None:
            continue
        severity = "critical" if value >= critical else "warning" if value >= warning else None
        if severity:
            alerts.append({
                "id": f"medusa.{alert_name}",
                "severity": severity,
                "metric": metric_name,
                "value": value,
                "threshold": critical if severity == "critical" else warning,
                "unit": metric["unit"],
                "observed_at": metric["observed_at"],
            })
    return alerts


def collect_operational_metrics(db: Session, settings) -> dict:
    """Collect process, host/container, cleanup and sandbox state metrics."""
    observed_at = datetime.now(UTC).isoformat()
    memory = _memory_metrics()
    disk = shutil.disk_usage("/")
    cpu = _cpu_percent()
    cleanup = sandbox_cleanup_metrics.snapshot()
    state_rows = db.execute(
        select(SandboxInstance.state, func.count(SandboxInstance.id)).group_by(SandboxInstance.state)
    ).all()
    cleanup_rows = db.execute(
        select(SandboxInstance.cleanup_status, func.count(SandboxInstance.id))
        .group_by(SandboxInstance.cleanup_status)
    ).all()
    now = datetime.now(UTC)
    due_retry_count = db.scalar(
        select(func.count(SandboxInstance.id)).where(
            SandboxInstance.cleanup_status.in_(("pending", "failed")),
            SandboxInstance.cleanup_next_attempt_at.is_not(None),
            SandboxInstance.cleanup_next_attempt_at <= now,
        )
    ) or 0
    oldest_retry = db.scalar(
        select(func.min(SandboxInstance.cleanup_next_attempt_at)).where(
            SandboxInstance.cleanup_status.in_(("pending", "failed")),
            SandboxInstance.cleanup_next_attempt_at.is_not(None),
        )
    )
    disk_percent = round(disk.used / disk.total * 100, 2) if disk.total else None
    metrics = {
        "host_cpu_percent": _metric(cpu, "percent", observed_at),
        "memory_percent": _metric(memory["percent"], "percent", observed_at),
        "memory_used_bytes": _metric(memory["used_bytes"], "bytes", observed_at),
        "memory_limit_bytes": _metric(memory["limit_bytes"], "bytes", observed_at),
        "disk_percent": _metric(disk_percent, "percent", observed_at),
        "disk_used_bytes": _metric(disk.used, "bytes", observed_at),
        "disk_total_bytes": _metric(disk.total, "bytes", observed_at),
        "process_uptime_seconds": _metric(round(time.monotonic() - _PROCESS_STARTED, 2), "seconds", observed_at),
        "sandbox_cleanup_failed": _metric(dict(cleanup_rows).get("failed", 0), "instances", observed_at),
        "sandbox_cleanup_due_retries": _metric(due_retry_count, "instances", observed_at),
        "sandbox_oldest_retry_age_seconds": _metric(
            max(0, int((now - oldest_retry).total_seconds())) if oldest_retry else 0,
            "seconds",
            observed_at,
        ),
    }
    return {
        "observed_at": observed_at,
        "metrics": metrics,
        "sandbox_instances_by_state": dict(state_rows),
        "sandbox_cleanup_by_status": dict(cleanup_rows),
        "cleanup_worker": {
            "scope": "current_api_process_only",
            "resets_on_process_restart": True,
            "batches": cleanup.batches,
            "processed": cleanup.processed,
            "cleaned": cleanup.cleaned,
            "failed": cleanup.failed,
        },
        "provider_instance_resource_metrics": {
            "available": False,
            "reason": "No concrete sandbox provider is configured; per-instance CPU/RAM is not measured.",
        },
        "alerts": _alerts(metrics, settings),
    }
