import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, GUID, JSONType, TimestampMixin, UUIDMixin


class Agent(UUIDMixin, TimestampMixin, Base):
    """Agent definition owned by an organization.

    status values: 'draft' | 'deployed' | 'paused'
    """

    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_agents_org_name"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict | None] = mapped_column(JSONType(), nullable=True)
    # status values: 'draft' | 'deployed' | 'paused'
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="draft", comment="draft|deployed|paused"
    )
    runtime_name: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Agent id={self.id} name={self.name!r} status={self.status!r}>"
