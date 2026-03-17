import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, GUID, TimestampMixin, UUIDMixin


class User(UUIDMixin, TimestampMixin, Base):
    """Platform user. auth_provider is 'google' or 'github'."""

    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email", "email", unique=True),)

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # auth_provider values: 'google' | 'github'
    auth_provider: Mapped[str] = mapped_column(String(32), nullable=False, comment="google|github")
    auth_provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
