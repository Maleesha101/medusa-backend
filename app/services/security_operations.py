"""Server-side security telemetry ingestion and threshold evaluation."""
# fmt: off
# ruff: noqa: E501

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.security_operations import SecurityAlert, SecurityEvent, SecurityRule
from app.models.user import User

RULES = (
    ("r_bruteauth", "Login brute force", "Account takeover", "High", 10, 5),
    ("r_bruteforce", "Flag brute-force", "Flag brute-forcing", "High", 20, 5),
    ("r_ratestreak", "Rate-limit hit streak", "Flag brute-forcing", "Medium", 5, 10),
    ("r_multiaccount", "Multi-accounting (shared IP/device)", "Multi-accounting", "Critical", 3, 60),
    ("r_spray", "Password spraying / credential stuffing", "Account takeover", "High", 10, 5),
    ("r_rapidsignup", "Rapid account creation", "Multi-accounting", "Medium", 5, 10),
    ("r_collusion", "Flag sharing / collusion", "Flag sharing / collusion", "Critical", 2, 1),
    ("r_samewrong", "Identical wrong flags across teams", "Flag sharing / collusion", "High", 2, 30),
    ("r_travel", "Impossible travel", "Account takeover", "High", 900, 60),
    ("r_scrape", "Scraping / enumeration", "Scraping/enumeration", "Medium", 30, 1),
    ("r_instance", "Instance start/stop cycling", "Instance abuse", "Low", 10, 15),
    ("r_inject", "Injection payload in text input", "Injection and probing", "High", 1, 1),
    ("r_files", "Bulk downloads after release", "File abuse", "Low", 50, 5),
    ("r_admin", "Admin action outside business hours", "Privilege/admin anomalies", "Medium", 1, 60),
    ("r_bot", "Machine-regular submission intervals", "Timing anomalies", "Medium", 10, 10),
    ("r_ws", "WebSocket reconnect flood", "Platform integrity", "Low", 30, 1),
)


SUPPORTED_RULES = {"r_bruteauth", "r_bruteforce"}


def seed_rules(db: Session) -> None:
    for rule_id, name, group, severity, threshold, window in RULES:
        if db.get(SecurityRule, rule_id) is None:
            supported = rule_id in SUPPORTED_RULES
            db.add(SecurityRule(
                id=rule_id, name=name, rule_group=group, severity=severity,
                threshold=threshold, window_minutes=window, enabled=supported,
                scope=("Authentication" if rule_id == "r_bruteauth" else
                       "Flag submissions" if rule_id == "r_bruteforce" else "Telemetry unavailable"),
            ))
    db.flush()


def record_security_event(
    db: Session,
    *,
    request: Request,
    event_type: str,
    category: str,
    user: User | None = None,
    team_id: int | None = None,
    target: str = "",
    result: str = "success",
    severity: str = "Info",
    details: dict[str, Any] | None = None,
) -> SecurityEvent:
    """Persist a normalized event; never accept passwords, tokens, or submitted flags."""
    peer = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")[:512] or None
    device = hashlib.sha256((ua or "unknown").encode()).hexdigest()[:24]
    event = SecurityEvent(
        event_type=event_type,
        category=category,
        user_id=user.id if user else None,
        team_id=team_id,
        ip=peer,
        device=device,
        user_agent=ua,
        target=target[:255],
        result=result,
        severity=severity,
        request_id=uuid.uuid4().hex,
        details=details,
    )
    db.add(event)
    db.flush()
    evaluate_security_rules(db, event)
    return event


def evaluate_security_rules(db: Session, event: SecurityEvent) -> None:
    """Evaluate persisted thresholds for supported telemetry types and upsert alerts."""
    seed_rules(db)
    now = event.created_at or datetime.now(UTC)
    supported = {
        "auth.login.failure": ("r_bruteauth", "ip", str(event.ip or "unknown")),
        "flag.submit": ("r_bruteforce", "team", str(event.team_id or "unknown")),
    }
    match = supported.get(event.event_type)
    if not match or event.result not in {"failure", "incorrect"}:
        return
    rule_id, entity_type, entity_id = match
    rule = db.get(SecurityRule, rule_id)
    if rule is None or not rule.enabled:
        return
    since = now - timedelta(minutes=rule.window_minutes)
    query = select(func.count(SecurityEvent.id)).where(
        SecurityEvent.event_type == event.event_type,
        SecurityEvent.result.in_(("failure", "incorrect")),
        SecurityEvent.created_at >= since,
    )
    if entity_type == "user" and event.user_id is not None:
        query = query.where(SecurityEvent.user_id == event.user_id)
    elif entity_type == "team" and event.team_id is not None:
        query = query.where(SecurityEvent.team_id == event.team_id)
    else:
        query = query.where(SecurityEvent.ip == event.ip)
    count = int(db.scalar(query) or 0)
    rule.last_eval = now
    if count < rule.threshold:
        return
    entity_label = entity_id
    alert = db.scalar(
        select(SecurityAlert).where(
            SecurityAlert.rule_id == rule_id,
            SecurityAlert.entity_type == entity_type,
            SecurityAlert.entity_id == entity_id,
            SecurityAlert.status.notin_(("Resolved", "False positive")),
        )
    )
    if alert is None:
        alert = SecurityAlert(
            title=f"{rule.name}: threshold exceeded",
            severity=rule.severity,
            status="New",
            rule_id=rule_id,
            rule_name=rule.name,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_label=entity_label,
            first_seen=now,
            last_seen=now,
            event_count=count,
            explanation=f"{count} matching events within {rule.window_minutes} minutes (threshold: {rule.threshold}).",
            risk_score=min(100, 40 + count),
            event_ids=[event.id],
            steps=["Review related activity", "Confirm whether this activity is authorized"],
        )
        db.add(alert)
    else:
        alert.last_seen = now
        alert.event_count = count
        alert.risk_score = min(100, 40 + count)
        alert.event_ids = list(dict.fromkeys([*(alert.event_ids or []), event.id]))
    rule.fired_24h += 1
