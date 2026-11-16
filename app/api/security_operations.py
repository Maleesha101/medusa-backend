"""Authenticated Security Operations Center API.

SOC data is persisted server-side. All endpoints are restricted to platform admins;
PII is omitted from list responses unless the caller explicitly requests a privileged view.
"""

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.db.session import get_db
from app.models.audit_event import AuditEvent
from app.models.security_operations import (
    SecurityAlert, SecurityCase, SecurityEvent, SecurityReport, SecurityResponseAction,
    SecurityRule, SecurityRuleChange, SecuritySavedView, SecuritySettings, SecurityWatchlist,
)
from app.models.team import Team
from app.models.user import User
from app.services.audit import record_audit_event
from app.services.security_operations import seed_rules

router = APIRouter(prefix="/soc", tags=["security-operations"])
_ADMIN = Depends(require_roles("admin"))
_SETTINGS_DEFAULTS: dict[str, Any] = {
    "retentionDays": 90, "suppressionHours": 6, "allowIps": "", "campusNetworks": "",
    "businessHours": "08:00–20:00", "notifyCritical": True, "notifyHigh": True,
    "email": "", "webhook": "",
}
_TRANSITIONS = {
    "New": {"Acknowledged", "Investigating", "Resolved", "False positive"},
    "Acknowledged": {"Investigating", "Resolved", "False positive"},
    "Investigating": {"Resolved", "False positive"},
    "Resolved": {"Investigating"}, "False positive": {"New"},
}


def _ms(value: datetime | None) -> int:
    if value is None:
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp() * 1000)


def _event(db: Session, row: SecurityEvent, *, reveal_pii: bool = False, alert_id: str | None = None) -> dict[str, Any]:
    user = db.get(User, row.user_id) if row.user_id else None
    team = db.get(Team, row.team_id) if row.team_id else None
    return {
        "id": str(row.id), "ts": _ms(row.created_at), "type": row.event_type,
        "category": row.category, "userId": str(row.user_id or ""),
        "user": (user.email if reveal_pii else f"User #{row.user_id}") if user else "Unknown", "team": team.name if team else "—",
        "teamId": str(row.team_id or ""), "university": "", "ip": row.ip if reveal_pii else _mask_ip(row.ip),
        "country": row.country, "device": row.device, "ua": row.user_agent if reveal_pii else "",
        "session": row.session_id or "", "target": row.target, "result": row.result,
        "severity": row.severity, "requestId": row.request_id,
        "alertId": alert_id,
    }


def _mask_ip(value: str | None) -> str:
    if not value:
        return "—"
    if ":" in value:
        return ":".join(value.split(":")[:3]) + ":xxxx"
    parts = value.split(".")
    return ".".join(parts[:3]) + ".xxx" if len(parts) == 4 else "xxx"


def _alert(row: SecurityAlert) -> dict[str, Any]:
    return {
        "id": str(row.id), "title": row.title, "severity": row.severity, "status": row.status,
        "ruleId": row.rule_id, "rule": row.rule_name,
        "entity": {"type": row.entity_type, "id": row.entity_id, "label": row.entity_label},
        "firstSeen": _ms(row.first_seen), "lastSeen": _ms(row.last_seen),
        "eventCount": row.event_count, "assignee": row.assignee,
        "caseId": str(row.case_id) if row.case_id else None, "explanation": row.explanation,
        "riskScore": row.risk_score, "eventIds": [str(x) for x in row.event_ids or []],
        "related": row.related or [], "steps": row.steps or [], "notes": row.notes or [],
        "history": row.history or [],
    }


def _case(row: SecurityCase) -> dict[str, Any]:
    return {
        "id": str(row.id), "title": row.title, "status": row.status, "severity": row.severity,
        "assignee": row.assignee, "entities": row.entities or [], "created": _ms(row.created_at),
        "updated": _ms(row.updated_at), "outcome": row.outcome, "description": row.description,
        "evidence": row.evidence or [], "notes": row.notes or [], "decisions": row.decisions or [],
        "attachments": row.attachments or [],
    }


def _case_or_404(db: Session, case_id: int) -> SecurityCase:
    row = db.get(SecurityCase, case_id)
    if row is None:
        raise HTTPException(404, "Investigation not found")
    return row


def _alert_or_404(db: Session, alert_id: int) -> SecurityAlert:
    row = db.get(SecurityAlert, alert_id)
    if row is None:
        raise HTTPException(404, "Alert not found")
    return row


@router.get("/events")
def list_events(
    limit: int = Query(100, ge=1, le=5000), cursor: int = Query(0, ge=0),
    since: int | None = None, severity: str | None = None, category: str | None = None,
    search: str | None = Query(None, max_length=200), reveal_pii: bool = False,
    db: Session = Depends(get_db), user: User = _ADMIN,
) -> dict[str, Any]:
    security_rows = list(db.scalars(
        select(SecurityEvent).order_by(SecurityEvent.created_at.desc(), SecurityEvent.id.desc()).limit(5000)
    ).all())
    alert_map: dict[int, str] = {}
    for alert in db.scalars(select(SecurityAlert)).all():
        for event_id in alert.event_ids or []:
            alert_map[event_id] = str(alert.id)
    items = [
        _event(db, row, reveal_pii=reveal_pii and user.role == "admin",
               alert_id=alert_map.get(row.id))
        for row in security_rows
    ]
    # Merge existing append-only platform audit records into the SOC activity stream.
    for audit in db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(5000)).all():
        if audit.action == "challenge.submission":
            continue  # flag submissions already have richer telemetry above
        actor = db.get(User, audit.actor_user_id) if audit.actor_user_id else None
        details = audit.details or {}
        team = db.get(Team, details.get("team_id")) if isinstance(details.get("team_id"), int) else None
        items.append({
            "id": f"audit-{audit.id}", "ts": _ms(audit.created_at), "type": audit.action,
            "category": "platform", "userId": str(audit.actor_user_id or ""),
            "user": (actor.email if reveal_pii else f"User #{audit.actor_user_id}") if actor else "System",
            "team": team.name if team else "—", "teamId": str(team.id) if team else "",
            "university": "", "ip": "—", "country": "XX", "device": "unknown",
            "ua": "", "session": "", "target": f"{audit.resource_type}:{audit.resource_id or ''}",
            "result": audit.outcome, "severity": "High" if audit.outcome in {"failure", "denied"} else "Info",
            "requestId": f"audit-{audit.id}", "alertId": None,
        })
    if since is not None:
        items = [item for item in items if item["ts"] >= since]
    if severity:
        items = [item for item in items if item["severity"].lower() == severity.lower()]
    if category:
        items = [item for item in items if item["category"] == category]
    if search:
        needle = search.lower()
        items = [item for item in items if needle in " ".join(str(value) for value in item.values()).lower()]
    items.sort(key=lambda item: (item["ts"], item["id"]), reverse=True)
    page = items[cursor:cursor + limit]
    more = cursor + len(page) < len(items)
    return {"items": page, "nextCursor": str(cursor + len(page)) if more else None}


@router.get("/alerts")
def list_alerts(
    limit: int = Query(100, ge=1, le=500), cursor: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status"), severity: str | None = None,
    assignee: str | None = None, db: Session = Depends(get_db), user: User = _ADMIN,
) -> dict[str, Any]:
    query = select(SecurityAlert).order_by(SecurityAlert.last_seen.desc(), SecurityAlert.id.desc())
    if status_filter:
        query = query.where(SecurityAlert.status == status_filter)
    if severity:
        query = query.where(SecurityAlert.severity == severity)
    if assignee:
        query = query.where(SecurityAlert.assignee == assignee)
    rows = list(db.scalars(query.offset(cursor).limit(limit + 1)).all())
    more = len(rows) > limit
    rows = rows[:limit]
    return {"items": [_alert(row) for row in rows], "nextCursor": str(cursor + len(rows)) if more else None}


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: int, db: Session = Depends(get_db), user: User = _ADMIN) -> dict[str, Any]:
    return _alert(_alert_or_404(db, alert_id))


@router.patch("/alerts/{alert_id}")
def update_alert(
    alert_id: int, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db),
    user: User = _ADMIN,
) -> dict[str, Any]:
    row = _alert_or_404(db, alert_id)
    allowed = {"status", "assignee", "caseId"}
    if set(payload) - allowed:
        raise HTTPException(422, "Unsupported alert fields")
    if "status" in payload:
        target = payload["status"]
        if target not in _TRANSITIONS.get(row.status, set()):
            raise HTTPException(409, "Invalid alert status transition")
        row.history = [*(row.history or []), {"at": int(datetime.now(UTC).timestamp()*1000),
                        "by": user.email, "from": row.status, "to": target}]
        row.status = target
    if "assignee" in payload:
        row.assignee = str(payload["assignee"]).strip()[:255] or "Unassigned"
    if "caseId" in payload:
        value = payload["caseId"]
        case = _case_or_404(db, int(value)) if value else None
        row.case_id = case.id if case else None
    record_audit_event(db, actor=user, action="soc.alert.updated", resource_type="soc_alert",
                       resource_id=row.id, details={"changed_fields": sorted(payload)})
    db.commit()
    db.refresh(row)
    return _alert(row)


@router.post("/alerts/{alert_id}/notes")
def add_alert_note(alert_id: int, payload: dict[str, str] = Body(...),
                   db: Session = Depends(get_db), user: User = _ADMIN) -> dict[str, Any]:
    row = _alert_or_404(db, alert_id)
    note = payload.get("text", "").strip()
    if len(note) < 3 or len(note) > 2000:
        raise HTTPException(422, "Note must contain 3–2000 characters")
    row.notes = [*(row.notes or []), {"by": user.email, "at": int(datetime.now(UTC).timestamp()*1000), "text": note}]
    record_audit_event(db, actor=user, action="soc.alert.note", resource_type="soc_alert", resource_id=row.id)
    db.commit()
    return _alert(row)


@router.post("/alerts/from-event/{event_id}", status_code=201)
def create_alert_from_event(event_id: int, db: Session = Depends(get_db),
                             user: User = _ADMIN) -> dict[str, Any]:
    event = db.get(SecurityEvent, event_id)
    if event is None:
        raise HTTPException(404, "Event not found")
    row = SecurityAlert(
        title=f"Manual alert: {event.event_type}", severity="Medium", status="New",
        rule_id="manual", rule_name="Manual (analyst)", entity_type="user",
        entity_id=str(event.user_id or event.ip or "unknown"), entity_label=str(event.user_id or event.ip or "unknown"),
        first_seen=event.created_at, last_seen=event.created_at, event_count=1,
        assignee=user.email, explanation=f"Raised manually from event {event.id}.",
        risk_score=40, event_ids=[event.id], steps=["Review related events"],
    )
    db.add(row)
    db.flush()
    record_audit_event(db, actor=user, action="soc.alert.created", resource_type="soc_alert", resource_id=row.id)
    db.commit()
    db.refresh(row)
    return _alert(row)


@router.get("/cases")
def list_cases(limit: int = Query(100, ge=1, le=500), cursor: int = Query(0, ge=0),
               db: Session = Depends(get_db), user: User = _ADMIN) -> dict[str, Any]:
    rows = list(db.scalars(select(SecurityCase).order_by(SecurityCase.updated_at.desc())
                           .offset(cursor).limit(limit + 1)).all())
    more = len(rows) > limit
    rows = rows[:limit]
    return {"items": [_case(row) for row in rows], "nextCursor": str(cursor + len(rows)) if more else None}


@router.post("/cases", status_code=201)
def create_case(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db),
                user: User = _ADMIN) -> dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    severity = payload.get("severity", "Medium")
    if not title or len(title) > 255 or severity not in {"Critical", "High", "Medium", "Low", "Info"}:
        raise HTTPException(422, "A valid title and severity are required")
    row = SecurityCase(title=title, severity=severity, assignee=user.email,
                       description=str(payload.get("description", ""))[:10000],
                       entities=payload.get("entities", []), evidence=payload.get("evidence", []))
    db.add(row)
    db.flush()
    record_audit_event(db, actor=user, action="soc.case.created", resource_type="soc_case", resource_id=row.id)
    db.commit()
    db.refresh(row)
    return _case(row)


@router.get("/cases/{case_id}")
def get_case(case_id: int, db: Session = Depends(get_db), user: User = _ADMIN) -> dict[str, Any]:
    return _case(_case_or_404(db, case_id))


@router.patch("/cases/{case_id}")
def update_case(case_id: int, payload: dict[str, Any] = Body(...),
                db: Session = Depends(get_db), user: User = _ADMIN) -> dict[str, Any]:
    row = _case_or_404(db, case_id)
    allowed = {"title", "status", "severity", "assignee", "outcome", "description",
               "entities", "evidence", "attachments"}
    if set(payload) - allowed:
        raise HTTPException(422, "Unsupported investigation fields")
    if "status" in payload and payload["status"] not in {"Open", "In progress", "Pending decision", "Closed"}:
        raise HTTPException(422, "Invalid investigation status")
    if "severity" in payload and payload["severity"] not in {"Critical", "High", "Medium", "Low", "Info"}:
        raise HTTPException(422, "Invalid severity")
    for key, value in payload.items():
        setattr(row, key, value)
    record_audit_event(db, actor=user, action="soc.case.updated", resource_type="soc_case",
                       resource_id=row.id, details={"changed_fields": sorted(payload)})
    db.commit()
    db.refresh(row)
    return _case(row)


@router.post("/cases/{case_id}/notes")
def add_case_note(case_id: int, payload: dict[str, str] = Body(...),
                  db: Session = Depends(get_db), user: User = _ADMIN) -> dict[str, Any]:
    row = _case_or_404(db, case_id)
    note = payload.get("text", "").strip()
    if len(note) < 3 or len(note) > 5000:
        raise HTTPException(422, "Note must contain 3–5000 characters")
    row.notes = [*(row.notes or []), {"by": user.email, "at": int(datetime.now(UTC).timestamp()*1000), "text": note}]
    db.commit()
    return _case(row)


@router.post("/cases/{case_id}/decisions")
def add_case_decision(case_id: int, payload: dict[str, str] = Body(...),
                      db: Session = Depends(get_db), user: User = _ADMIN) -> dict[str, Any]:
    row = _case_or_404(db, case_id)
    decision = payload.get("text", "").strip()
    if len(decision) < 5 or len(decision) > 5000:
        raise HTTPException(422, "Decision must contain 5–5000 characters")
    row.decisions = [*(row.decisions or []), {"by": user.email, "at": int(datetime.now(UTC).timestamp()*1000), "text": decision}]
    row.status = "Pending decision"
    db.commit()
    return _case(row)


@router.get("/rules")
def list_rules(db: Session = Depends(get_db), user: User = _ADMIN) -> dict[str, Any]:
    seed_rules(db)
    db.commit()
    rows = list(db.scalars(select(SecurityRule).order_by(SecurityRule.id)).all())
    return {"items": [{"id": r.id, "name": r.name, "group": r.rule_group, "enabled": r.enabled,
        "severity": r.severity, "threshold": r.threshold, "windowMin": r.window_minutes,
        "scope": r.scope, "fired24h": r.fired_24h, "lastEval": _ms(r.last_eval)} for r in rows],
        "changes": [{"at": _ms(c.created_at), "by": db.get(User, c.actor_user_id).email if c.actor_user_id and db.get(User, c.actor_user_id) else "System",
                     "rule": c.rule_id, "change": c.change}
                    for c in db.scalars(select(SecurityRuleChange).order_by(SecurityRuleChange.created_at.desc()).limit(100)).all()]}


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: str, payload: dict[str, Any] = Body(...),
                db: Session = Depends(get_db), user: User = _ADMIN) -> dict[str, Any]:
    row = db.get(SecurityRule, rule_id)
    if row is None:
        raise HTTPException(404, "Detection rule not found")
    allowed = {"enabled", "severity", "threshold", "windowMin", "scope"}
    if set(payload) - allowed:
        raise HTTPException(422, "Unsupported rule fields")
    before = {key: getattr(row, {"windowMin": "window_minutes"}.get(key, key)) for key in payload}
    for key, value in payload.items():
        if key == "severity" and value not in {"Critical", "High", "Medium", "Low", "Info"}:
            raise HTTPException(422, "Invalid severity")
        if key == "threshold" and (not isinstance(value, (int, float)) or value <= 0):
            raise HTTPException(422, "Threshold must be positive")
        if key == "windowMin" and (not isinstance(value, int) or value < 1 or value > 10080):
            raise HTTPException(422, "Window must be between 1 and 10080 minutes")
        setattr(row, {"windowMin": "window_minutes"}.get(key, key), value)
    change = ", ".join(f"{key}: {before[key]} → {value}" for key, value in payload.items())
    db.add(SecurityRuleChange(rule_id=row.id, actor_user_id=user.id, change=change[:255]))
    record_audit_event(db, actor=user, action="soc.rule.updated", resource_type="soc_rule",
                       details={"rule_id": rule_id, "fields": sorted(payload)})
    db.commit()
    return {"id": row.id, "name": row.name, "group": row.rule_group, "enabled": row.enabled,
            "severity": row.severity, "threshold": row.threshold, "windowMin": row.window_minutes,
            "scope": row.scope, "fired24h": row.fired_24h, "lastEval": _ms(row.last_eval)}


@router.get("/entities")
def list_entities(db: Session = Depends(get_db), user: User = _ADMIN) -> dict[str, Any]:
    rows = list(db.scalars(select(SecurityEvent).order_by(SecurityEvent.created_at.desc()).limit(5000)).all())
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        for kind, key, label in (("user", str(row.user_id or ""), str(row.user_id or "Unknown")),
                                 ("team", str(row.team_id or ""), str(row.team_id or "Unknown")),
                                 ("ip", row.ip or "", _mask_ip(row.ip)), ("device", row.device, row.device)):
            if not key:
                continue
            item = groups.setdefault((kind, key), {"id": key, "type": kind, "label": label,
                "riskScore": 0, "watchlisted": False, "eventCount": 0, "lastSeen": _ms(row.created_at)})
            item["eventCount"] += 1
            item["lastSeen"] = max(item["lastSeen"], _ms(row.created_at))
    watched = {(w.entity_type, w.entity_id) for w in db.scalars(select(SecurityWatchlist)).all()}
    for (kind, key), item in groups.items():
        item["watchlisted"] = (kind, key) in watched
        item["riskScore"] = min(100, item["eventCount"] * 5)
    return {"items": list(groups.values())}


@router.get("/watchlist")
def list_watchlist(db: Session = Depends(get_db), user: User = _ADMIN) -> dict[str, Any]:
    rows = list(db.scalars(select(SecurityWatchlist).order_by(SecurityWatchlist.created_at.desc())).all())
    return {"items": [{"type": row.entity_type, "id": row.entity_id, "label": row.label,
                       "note": row.note} for row in rows]}


@router.post("/watchlist", status_code=201)
def add_watchlist(payload: dict[str, str] = Body(...), db: Session = Depends(get_db),
                  user: User = _ADMIN) -> dict[str, Any]:
    kind, entity_id = payload.get("type", ""), payload.get("id", "").strip()
    if kind not in {"user", "team", "ip", "device"} or not entity_id or len(entity_id) > 128:
        raise HTTPException(422, "Invalid watchlist entity")
    row = db.scalar(select(SecurityWatchlist).where(SecurityWatchlist.entity_type == kind,
                                                    SecurityWatchlist.entity_id == entity_id))
    if row is None:
        row = SecurityWatchlist(entity_type=kind, entity_id=entity_id,
                                label=payload.get("label", entity_id)[:255],
                                note=payload.get("note", "")[:2000], created_by_user_id=user.id)
        db.add(row)
    db.commit()
    return {"type": row.entity_type, "id": row.entity_id, "label": row.label, "note": row.note}


@router.delete("/watchlist/{entity_type}/{entity_id}", status_code=204)
def remove_watchlist(entity_type: str, entity_id: str, db: Session = Depends(get_db),
                     user: User = _ADMIN) -> Response:
    row = db.scalar(select(SecurityWatchlist).where(SecurityWatchlist.entity_type == entity_type,
                                                    SecurityWatchlist.entity_id == entity_id))
    if row:
        db.delete(row)
        db.commit()
    return Response(status_code=204)


@router.get("/saved-views")
def list_saved_views(db: Session = Depends(get_db), user: User = _ADMIN) -> dict[str, Any]:
    rows = list(db.scalars(select(SecuritySavedView).where(SecuritySavedView.user_id == user.id)
                           .order_by(SecuritySavedView.created_at.desc())).all())
    return {"items": [{"id": str(row.id), "name": row.name, "query": row.query} for row in rows]}


@router.post("/saved-views", status_code=201)
def create_saved_view(payload: dict[str, str] = Body(...), db: Session = Depends(get_db),
                      user: User = _ADMIN) -> dict[str, Any]:
    name, query = payload.get("name", "").strip(), payload.get("query", "").strip()
    if not name or len(name) > 100 or len(query) > 500:
        raise HTTPException(422, "Saved view name and query are invalid")
    row = db.scalar(select(SecuritySavedView).where(SecuritySavedView.user_id == user.id,
                                                    SecuritySavedView.name == name))
    if row is None:
        row = SecuritySavedView(user_id=user.id, name=name, query=query)
        db.add(row)
    else:
        row.query = query
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "name": row.name, "query": row.query}


@router.delete("/saved-views/{view_id}", status_code=204)
def delete_saved_view(view_id: int, db: Session = Depends(get_db),
                      user: User = _ADMIN) -> Response:
    row = db.scalar(select(SecuritySavedView).where(SecuritySavedView.id == view_id,
                                                    SecuritySavedView.user_id == user.id))
    if row:
        db.delete(row)
        db.commit()
    return Response(status_code=204)


@router.get("/settings")
def get_soc_settings(db: Session = Depends(get_db), user: User = _ADMIN) -> dict[str, Any]:
    row = db.get(SecuritySettings, 1)
    return row.config if row else _SETTINGS_DEFAULTS


@router.put("/settings")
def update_soc_settings(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db),
                        user: User = _ADMIN) -> dict[str, Any]:
    allowed = set(_SETTINGS_DEFAULTS)
    if set(payload) - allowed:
        raise HTTPException(422, "Unsupported SOC settings")
    config = {**_SETTINGS_DEFAULTS, **payload}
    if not isinstance(config["retentionDays"], int) or not 1 <= config["retentionDays"] <= 3650:
        raise HTTPException(422, "Retention must be between 1 and 3650 days")
    if not isinstance(config["suppressionHours"], int) or not 0 <= config["suppressionHours"] <= 168:
        raise HTTPException(422, "Suppression must be between 0 and 168 hours")
    if config["webhook"] and not str(config["webhook"]).startswith("https://"):
        raise HTTPException(422, "Webhook URL must use HTTPS")
    row = db.get(SecuritySettings, 1)
    if row is None:
        row = SecuritySettings(id=1, config=config, updated_by_user_id=user.id)
        db.add(row)
    else:
        row.config = config
        row.updated_by_user_id = user.id
    record_audit_event(db, actor=user, action="soc.settings.updated", resource_type="soc_settings")
    db.commit()
    return config


@router.get("/reports")
def list_reports(db: Session = Depends(get_db), user: User = _ADMIN) -> dict[str, Any]:
    rows = list(db.scalars(select(SecurityReport).order_by(SecurityReport.created_at.desc()).limit(100)).all())
    return {"items": [{"id": str(r.id), "title": r.title, "generatedAt": _ms(r.created_at),
                       "format": r.parameters.get("format", "json")} for r in rows]}


@router.post("/reports", status_code=201)
def create_report(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db),
                  user: User = _ADMIN) -> dict[str, Any]:
    report_type = payload.get("type", "summary")
    if report_type not in {"summary", "events", "alerts", "rules"}:
        raise HTTPException(422, "Unsupported report type")
    row = SecurityReport(title=str(payload.get("title", "SOC report"))[:160],
                         report_type=report_type, parameters=payload)
    db.add(row)
    db.flush()
    record_audit_event(db, actor=user, action="soc.report.generated", resource_type="soc_report", resource_id=row.id)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "title": row.title, "generatedAt": _ms(row.created_at),
            "format": payload.get("format", "json")}


@router.get("/reports/{report_id}/data")
def report_data(report_id: int, db: Session = Depends(get_db), user: User = _ADMIN) -> Response:
    report = db.get(SecurityReport, report_id)
    if report is None:
        raise HTTPException(404, "Report not found")
    since_ms = report.parameters.get("since")
    since = (datetime.fromtimestamp(int(since_ms) / 1000, UTC) if since_ms is not None
             else datetime.now(UTC) - timedelta(days=int(report.parameters.get("days", 1))))
    output = io.StringIO()
    writer = csv.writer(output)
    if report.report_type == "events":
        writer.writerow(["id", "timestamp", "type", "category", "actor_id", "result", "severity", "ip", "target"])
        for event in db.scalars(select(SecurityEvent).where(SecurityEvent.created_at >= since)
                                .order_by(SecurityEvent.created_at.desc()).limit(5000)).all():
            writer.writerow([event.id, _ms(event.created_at), event.event_type, event.category,
                             event.user_id or "", event.result, event.severity, _mask_ip(event.ip), event.target])
    elif report.report_type == "alerts":
        writer.writerow(["id", "title", "severity", "status", "rule", "entity_type", "entity_id",
                         "first_seen", "last_seen", "event_count", "assignee", "case_id"])
        for alert in db.scalars(select(SecurityAlert).where(SecurityAlert.last_seen >= since)
                                .order_by(SecurityAlert.last_seen.desc()).limit(5000)).all():
            writer.writerow([alert.id, alert.title, alert.severity, alert.status, alert.rule_name,
                             alert.entity_type, alert.entity_id, _ms(alert.first_seen), _ms(alert.last_seen),
                             alert.event_count, alert.assignee, alert.case_id or ""])
    elif report.report_type == "rules":
        writer.writerow(["id", "name", "group", "enabled", "severity", "threshold", "window_minutes",
                         "scope", "fired_24h", "last_eval"])
        for rule in db.scalars(select(SecurityRule).order_by(SecurityRule.id)).all():
            writer.writerow([rule.id, rule.name, rule.rule_group, rule.enabled, rule.severity,
                             rule.threshold, rule.window_minutes, rule.scope, rule.fired_24h, _ms(rule.last_eval)])
    else:
        writer.writerow(["generated_at", "window_start", "events", "open_alerts", "critical_alerts",
                         "unresolved_cases", "enabled_rules"])
        writer.writerow([_ms(datetime.now(UTC)), _ms(since),
                         db.query(SecurityEvent).filter(SecurityEvent.created_at >= since).count(),
                         db.query(SecurityAlert).filter(SecurityAlert.status.notin_(("Resolved", "False positive"))).count(),
                         db.query(SecurityAlert).filter(SecurityAlert.severity == "Critical",
                             SecurityAlert.status.notin_(("Resolved", "False positive"))).count(),
                         db.query(SecurityCase).filter(SecurityCase.status != "Closed").count(),
                         db.query(SecurityRule).filter(SecurityRule.enabled.is_(True)).count()])
    return Response(output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="medusa-soc-{report.report_type}-{report_id}.csv"'})



@router.post("/response-actions", status_code=201)
def create_response_action(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db),
                           user: User = _ADMIN) -> dict[str, Any]:
    action_type = payload.get("type")
    supported = {"revoke_sessions", "lock_user", "require_reset", "warn"}
    if action_type not in supported:
        raise HTTPException(501, "This response action is not yet connected to an enforceable MEDUSA control")
    target = payload.get("target") or {}
    if target.get("type") not in {"user", "team", "device"} or not target.get("id"):
        raise HTTPException(422, "Invalid response target")
    reason = str(payload.get("reason", "")).strip()
    if len(reason) < 5 or len(reason) > 2000:
        raise HTTPException(422, "A reason of 5–2000 characters is required")
    # Revoke sessions and lock_user are enforced by auth_version / is_active.
    if action_type in {"revoke_sessions", "lock_user", "require_reset"}:
        if target["type"] != "user" or not str(target["id"]).isdigit():
            raise HTTPException(422, "This response action requires a numeric user ID")
        subject = db.get(User, int(target["id"]))
        if subject is None:
            raise HTTPException(404, "Target user not found")
        if action_type == "revoke_sessions":
            subject.auth_version += 1
        elif action_type == "lock_user":
            subject.is_active = False
            subject.auth_version += 1
        else:
            raise HTTPException(501, "Require password reset is not yet supported by the account model")
    row = SecurityResponseAction(action_type=action_type, target=target, reason=reason,
        case_id=int(payload["caseId"]) if payload.get("caseId") else None,
        actor_user_id=user.id, preview=[f"Action {action_type} applied to {target.get('label', target['id'])}."],
        revertible=action_type == "lock_user")
    db.add(row)
    db.flush()
    record_audit_event(db, actor=user, action=f"soc.response.{action_type}", resource_type="soc_response_action", resource_id=row.id)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "type": row.action_type, "target": row.target, "reason": row.reason,
            "caseId": str(row.case_id) if row.case_id else None, "at": _ms(row.created_at),
            "by": user.email, "preview": row.preview, "revertible": row.revertible, "reverted": row.reverted}


@router.get("/response-actions")
def list_response_actions(db: Session = Depends(get_db), user: User = _ADMIN) -> dict[str, Any]:
    rows = list(db.scalars(select(SecurityResponseAction).order_by(SecurityResponseAction.created_at.desc()).limit(500)).all())
    return {"items": [{"id": str(r.id), "type": r.action_type, "target": r.target, "reason": r.reason,
        "caseId": str(r.case_id) if r.case_id else None, "at": _ms(r.created_at),
        "by": db.get(User, r.actor_user_id).email if r.actor_user_id and db.get(User, r.actor_user_id) else "Unknown",
        "preview": r.preview, "revertible": r.revertible, "reverted": r.reverted} for r in rows]}
