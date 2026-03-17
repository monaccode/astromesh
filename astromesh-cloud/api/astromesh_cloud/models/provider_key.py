import uuid

from sqlalchemy import ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, GUID, TimestampMixin, UUIDMixin


class ProviderKey(UUIDMixin, TimestampMixin, Base):
    """Encrypted LLM provider credential stored per organization."""

    __tablename__ = "provider_keys"

    org_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    def __repr__(self) -> str:
        return f"<ProviderKey id={self.id} provider={self.provider!r}>"
