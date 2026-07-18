"""SQLAlchemy models for durable API controls."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, LargeBinary, BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ApiRateControlCounter(Base):
    """Privacy-keyed fixed-window counter shared by every API replica."""

    __tablename__ = "api_rate_control_counters"
    __table_args__ = (
        CheckConstraint(
            "control_scope in ('first_access', 'admin_mutation')",
            name="scope_token",
        ),
        CheckConstraint("octet_length(key_digest) = 32", name="digest_length"),
        CheckConstraint(
            "request_count between 1 and 9223372036854775807",
            name="request_count",
        ),
        CheckConstraint(
            "window_started_at < window_expires_at",
            name="window_order",
        ),
        Index(
            "ix_api_rate_control_counters_window_expires_at",
            "window_expires_at",
        ),
    )

    control_scope: Mapped[str] = mapped_column(String(32), primary_key=True)
    key_digest: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_count: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
