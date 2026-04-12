"""SQLAlchemy mirror models for the admin dashboard tables.

Mirrors the Prisma models defined in `packages/db/prisma/schema.prisma`:
SystemRule, SystemConfig, SystemBroadcast, MaintenanceJob.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.owner import Base, _utcnow


class SystemRule(Base):
    __tablename__ = "system_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    personality_baseline: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rate_limits: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    file_size_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    base_model: Mapped[str | None] = mapped_column(String, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class SystemConfig(Base):
    __tablename__ = "system_config"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="singleton")
    default_rule_id: Mapped[str | None] = mapped_column(String, nullable=True)
    default_base_model: Mapped[str | None] = mapped_column(String, nullable=True)
    global_rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    global_file_size_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class SystemBroadcast(Base):
    __tablename__ = "system_broadcasts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    push_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    push_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (Index("ix_system_broadcasts_active_created", "active", "created_at"),)


class MaintenanceJob(Base):
    __tablename__ = "maintenance_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_type: Mapped[str] = mapped_column(String, nullable=False)
    target: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_by: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (Index("ix_maintenance_jobs_status_started", "status", "started_at"),)
