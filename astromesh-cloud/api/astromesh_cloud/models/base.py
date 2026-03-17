import json
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, TypeDecorator, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class GUID(TypeDecorator):
    """Platform-independent UUID type."""

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return str(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return uuid.UUID(value)
        return value


class JSONType(TypeDecorator):
    """Platform-independent JSON type."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and isinstance(value, str):
            return json.loads(value)
        return value


class StringArray(TypeDecorator):
    """Platform-independent array type. Stores as JSON string list."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return "[]"

    def process_result_value(self, value, dialect):
        if value is not None and isinstance(value, str):
            return json.loads(value)
        return value or []


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
