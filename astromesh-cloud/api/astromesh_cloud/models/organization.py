import uuid

from sqlalchemy import ForeignKey, Index, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, GUID, TimestampMixin, UUIDMixin


class Organization(UUIDMixin, TimestampMixin, Base):
    """Tenant organization."""

    __tablename__ = "organizations"
    __table_args__ = (Index("ix_organizations_slug", "slug", unique=True),)

    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    members: Mapped[list["OrgMember"]] = relationship(
        "OrgMember", back_populates="organization", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Organization id={self.id} slug={self.slug!r}>"


class OrgMember(Base):
    """Membership link between a User and an Organization.

    role values: 'owner' | 'admin' | 'member'
    """

    __tablename__ = "org_members"
    __table_args__ = (PrimaryKeyConstraint("user_id", "org_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # role values: 'owner' | 'admin' | 'member'
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="member", comment="owner|admin|member"
    )

    organization: Mapped[Organization] = relationship("Organization", back_populates="members")

    def __repr__(self) -> str:
        return f"<OrgMember user_id={self.user_id} org_id={self.org_id} role={self.role!r}>"
