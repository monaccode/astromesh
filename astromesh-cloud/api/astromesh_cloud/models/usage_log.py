import uuid

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, GUID, TimestampMixin, UUIDMixin


class UsageLog(UUIDMixin, TimestampMixin, Base):
    """Per-request token and cost tracking record."""

    __tablename__ = "usage_logs"

    org_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("agents.id", ondelete="SET NULL"), nullable=False, index=True
    )
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, default=0)

    def __repr__(self) -> str:
        return (
            f"<UsageLog id={self.id} model={self.model!r} "
            f"tokens_in={self.tokens_in} tokens_out={self.tokens_out}>"
        )
