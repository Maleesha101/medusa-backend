"""Persistent security operations data: events, alerts, cases, rules, and analyst state."""
# fmt: off
# ruff: noqa: E501

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

class SecurityEvent(Base):
    __tablename__ = "soc_events"
    __table_args__ = (
        Index("ix_soc_events_created_at", "created_at"),
        Index("ix_soc_events_category_severity", "category", "severity"),
        Index("ix_soc_events_actor_created", "user_id", "created_at"),
        Index("ix_soc_events_ip_created", "ip", "created_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="XX", server_default="XX")
    device: Mapped[str] = mapped_column(String(128), nullable=False, default="unknown", server_default="unknown")
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    result: Mapped[str] = mapped_column(String(24), nullable=False, default="success", server_default="success")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="Info", server_default="Info")
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SecurityAlert(Base):
    __tablename__ = "soc_alerts"
    __table_args__ = (Index("ix_soc_alerts_status_severity", "status", "severity"), Index("ix_soc_alerts_last_seen", "last_seen"))
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="New", server_default="New")
    rule_id: Mapped[str] = mapped_column(String(80), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(160), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_label: Mapped[str] = mapped_column(String(255), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    assignee: Mapped[str] = mapped_column(String(255), nullable=False, default="Unassigned", server_default="Unassigned")
    case_id: Mapped[int | None] = mapped_column(ForeignKey("soc_cases.id", ondelete="SET NULL"), nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    event_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    related: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    steps: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)


class SecurityCase(Base):
    __tablename__ = "soc_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Open", server_default="Open")
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    assignee: Mapped[str] = mapped_column(String(255), nullable=False, default="Unassigned", server_default="Unassigned")
    entities: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False, default="", server_default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    decisions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    attachments: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SecurityRule(Base):
    __tablename__ = "soc_rules"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    rule_group: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    threshold: Mapped[float] = mapped_column(nullable=False)
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    scope: Mapped[str] = mapped_column(String(100), nullable=False, default="All teams", server_default="All teams")
    fired_24h: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_eval: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SecurityRuleChange(Base):
    __tablename__ = "soc_rule_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("soc_rules.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    change: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SecurityWatchlist(Base):
    __tablename__ = "soc_watchlist"
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", name="uq_soc_watchlist_entity"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SecuritySettings(Base):
    __tablename__ = "soc_settings"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SecurityResponseAction(Base):
    __tablename__ = "soc_response_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("soc_cases.id", ondelete="SET NULL"), nullable=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    preview: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    revertible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    reverted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SecuritySavedView(Base):
    __tablename__ = "soc_saved_views"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_soc_saved_view_user_name"),)


class SecurityReport(Base):
    __tablename__ = "soc_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    generated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
