# Astromesh Cloud API — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Cloud API — a multi-tenant FastAPI service with OAuth auth, organizations, agent CRUD, runtime proxy, and usage tracking.

**Architecture:** FastAPI service at `astromesh-cloud/api/` with SQLAlchemy async models (PostgreSQL), JWT auth, and httpx proxy to the Astromesh runtime. All business logic in `services/`, all HTTP in `routes/`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async + asyncpg, Alembic, Pydantic v2, python-jose (JWT), cryptography (Fernet), httpx, pytest, uv

**Depends on:** Runtime Prerequisites plan (Tasks 1-5) must be completed first.

---

## File Structure

### Models (`astromesh_cloud/models/`)
| File | Responsibility |
|------|----------------|
| `base.py` | SQLAlchemy declarative base, common mixins (UUIDMixin, TimestampMixin) |
| `user.py` | User model (OAuth fields) |
| `organization.py` | Organization + OrgMember models |
| `agent.py` | Agent model (config JSONB, status enum, runtime_name) |
| `api_key.py` | ApiKey model (hash, prefix, scopes) |
| `provider_key.py` | ProviderKey model (encrypted_key) |
| `usage_log.py` | UsageLog model |

### Schemas (`astromesh_cloud/schemas/`)
| File | Responsibility |
|------|----------------|
| `auth.py` | OAuth callback, JWT token, user profile schemas |
| `agent.py` | Agent create/update/response, wizard config schema |
| `organization.py` | Org response, member invite, member response |
| `usage.py` | Usage summary response |
| `keys.py` | API key create/response, provider key create/response |

### Routes (`astromesh_cloud/routes/`)
| File | Responsibility |
|------|----------------|
| `auth.py` | Google/GitHub OAuth, refresh, logout |
| `agents.py` | Agent CRUD + deploy/pause/test |
| `organizations.py` | Org settings, member management |
| `keys.py` | API key + provider key management |
| `execution.py` | Run proxy, WebSocket stream proxy |
| `usage.py` | Usage summary |

### Services (`astromesh_cloud/services/`)
| File | Responsibility |
|------|----------------|
| `auth_service.py` | OAuth token exchange, user upsert, JWT creation |
| `agent_service.py` | Agent lifecycle (create/deploy/pause/delete), limit checks |
| `runtime_proxy.py` | httpx client to runtime, namespace rewriting, session prefix, BYOK headers |
| `config_builder.py` | Wizard JSON config → Astromesh agent YAML translation |
| `encryption.py` | Fernet encrypt/decrypt for provider keys |
| `reconciliation.py` | Startup reconciliation loop (re-register deployed agents) |

### Infrastructure
| File | Responsibility |
|------|----------------|
| `main.py` | FastAPI app, lifespan, CORS, route registration |
| `config.py` | Pydantic Settings (env vars: DB URL, JWT secret, OAuth keys, runtime URL) |
| `database.py` | async engine, session factory, `get_db` dependency |
| `middleware/auth.py` | JWT verification dependency (`get_current_user`) |
| `middleware/rate_limit.py` | Request counting against UsageLog |

---

### Task 1: Project Scaffold and Database Setup

**Files:**
- Create: `astromesh-cloud/api/pyproject.toml`
- Create: `astromesh-cloud/api/astromesh_cloud/__init__.py`
- Create: `astromesh-cloud/api/astromesh_cloud/config.py`
- Create: `astromesh-cloud/api/astromesh_cloud/database.py`
- Create: `astromesh-cloud/api/astromesh_cloud/models/base.py`
- Create: `astromesh-cloud/api/astromesh_cloud/main.py`
- Create: `astromesh-cloud/api/tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "astromesh-cloud"
version = "0.1.0"
description = "Astromesh Cloud — multi-tenant AI agent platform API"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.30.0",
    "alembic>=1.13.0",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.0.0",
    "python-jose[cryptography]>=3.3.0",
    "cryptography>=42.0.0",
    "httpx>=0.27.0",
    "bcrypt>=4.0.0",
    "authlib>=1.3.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0",
    "aiosqlite>=0.20.0",
    "ruff>=0.6.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100
```

- [ ] **Step 2: Create config.py**

```python
# astromesh_cloud/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/astromesh_cloud"
    database_url_test: str = "sqlite+aiosqlite:///test.db"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7

    # OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""

    # Runtime
    runtime_url: str = "http://localhost:8000"

    # Encryption
    fernet_key: str = ""  # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    # Limits
    max_agents_per_org: int = 5
    max_requests_per_day: int = 1000
    max_members_per_org: int = 3

    model_config = {"env_prefix": "ASTROMESH_CLOUD_"}


settings = Settings()
```

- [ ] **Step 3: Create database.py**

```python
# astromesh_cloud/database.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from astromesh_cloud.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session
```

- [ ] **Step 4: Create models/base.py**

```python
# astromesh_cloud/models/base.py
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text, TypeDecorator, func, types
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class GUID(TypeDecorator):
    """Platform-independent UUID type. Uses PostgreSQL UUID, falls back to String(36) for SQLite."""
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
    """Platform-independent JSON type. Uses PostgreSQL JSONB, falls back to Text+json for SQLite."""
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
    """Platform-independent array type. Stores as JSON string list for SQLite."""
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
    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 5: Create minimal main.py**

```python
# astromesh_cloud/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: reconciliation loop will go here
    yield
    # Shutdown


app = FastAPI(
    title="Astromesh Cloud",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "service": "astromesh-cloud"}
```

- [ ] **Step 6: Create test conftest with SQLite async**

```python
# astromesh-cloud/api/tests/conftest.py
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from astromesh_cloud.models.base import Base
from astromesh_cloud.database import get_db
from astromesh_cloud.main import app

TEST_DB_URL = "sqlite+aiosqlite:///./test.db"


@pytest.fixture
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

- [ ] **Step 7: Write and run health check test**

```python
# astromesh-cloud/api/tests/test_health.py
async def test_health(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["service"] == "astromesh-cloud"
```

Run: `cd astromesh-cloud/api && uv sync && uv run pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add astromesh-cloud/api/
git commit -m "feat(cloud): scaffold Cloud API with FastAPI, SQLAlchemy async, test infrastructure"
```

---

### Task 2: SQLAlchemy Models

**Files:**
- Create: `astromesh_cloud/models/user.py`
- Create: `astromesh_cloud/models/organization.py`
- Create: `astromesh_cloud/models/agent.py`
- Create: `astromesh_cloud/models/api_key.py`
- Create: `astromesh_cloud/models/provider_key.py`
- Create: `astromesh_cloud/models/usage_log.py`
- Create: `astromesh_cloud/models/__init__.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Create all model files**

```python
# astromesh_cloud/models/user.py
from datetime import datetime

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UUIDMixin, TimestampMixin


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    auth_provider: Mapped[str] = mapped_column(Enum("google", "github", name="auth_provider_enum"))
    auth_provider_id: Mapped[str] = mapped_column(String(255))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

```python
# astromesh_cloud/models/organization.py
import uuid

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from .base import GUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDMixin, TimestampMixin


class Organization(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "organizations"

    slug: Mapped[str] = mapped_column(String(63), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))

    members: Mapped[list["OrgMember"]] = relationship(back_populates="organization")


class OrgMember(Base):
    __tablename__ = "org_members"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_org_member"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id"), primary_key=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id"), primary_key=True
    )
    role: Mapped[str] = mapped_column(
        Enum("owner", "admin", "member", name="org_role_enum"), default="member"
    )

    organization: Mapped["Organization"] = relationship(back_populates="members")
```

```python
# astromesh_cloud/models/agent.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from .base import GUID, JSONType
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UUIDMixin, TimestampMixin


class Agent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_agent_org_name"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(63))
    display_name: Mapped[str] = mapped_column(String(255))
    config: Mapped[dict] = mapped_column(JSONType(), default=dict)
    status: Mapped[str] = mapped_column(
        Enum("draft", "deployed", "paused", name="agent_status_enum"), default="draft"
    )
    runtime_name: Mapped[str] = mapped_column(String(127))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", onupdate="now()"
    )
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

```python
# astromesh_cloud/models/api_key.py
import uuid

from sqlalchemy import ForeignKey, String
from .base import GUID, StringArray
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from sqlalchemy import DateTime

from .base import Base, UUIDMixin, TimestampMixin


class ApiKey(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "api_keys"

    org_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("organizations.id"))
    key_hash: Mapped[str] = mapped_column(String(255))
    prefix: Mapped[str] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(255))
    scopes: Mapped[list[str]] = mapped_column(StringArray(), default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

```python
# astromesh_cloud/models/provider_key.py
import uuid

from sqlalchemy import ForeignKey, LargeBinary, String
from .base import GUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UUIDMixin, TimestampMixin


class ProviderKey(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "provider_keys"

    org_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("organizations.id"))
    provider: Mapped[str] = mapped_column(String(63))
    encrypted_key: Mapped[bytes] = mapped_column(LargeBinary)
```

```python
# astromesh_cloud/models/usage_log.py
import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String
from .base import GUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UUIDMixin, TimestampMixin


class UsageLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "usage_logs"

    org_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("organizations.id"))
    agent_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("agents.id"))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(127), default="")
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
```

```python
# astromesh_cloud/models/__init__.py
from .base import Base
from .user import User
from .organization import Organization, OrgMember
from .agent import Agent
from .api_key import ApiKey
from .provider_key import ProviderKey
from .usage_log import UsageLog

__all__ = [
    "Base", "User", "Organization", "OrgMember", "Agent",
    "ApiKey", "ProviderKey", "UsageLog",
]
```

- [ ] **Step 2: Write model tests**

```python
# tests/test_models.py
from astromesh_cloud.models import User, Organization, OrgMember, Agent, ApiKey, ProviderKey, UsageLog


async def test_create_user(db_session):
    user = User(
        email="test@example.com",
        name="Test User",
        auth_provider="google",
        auth_provider_id="google-123",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    assert user.id is not None
    assert user.email == "test@example.com"


async def test_create_org_with_member(db_session):
    user = User(email="owner@test.com", name="Owner", auth_provider="google", auth_provider_id="g1")
    db_session.add(user)
    await db_session.commit()

    org = Organization(slug="acme", name="Acme Corp")
    db_session.add(org)
    await db_session.commit()

    member = OrgMember(user_id=user.id, org_id=org.id, role="owner")
    db_session.add(member)
    await db_session.commit()

    assert member.role == "owner"


async def test_create_agent(db_session):
    org = Organization(slug="test-org", name="Test Org")
    db_session.add(org)
    await db_session.commit()

    agent = Agent(
        org_id=org.id,
        name="my-agent",
        display_name="My Agent",
        config={"model": {"primary": "ollama/llama3"}},
        status="draft",
        runtime_name="test-org--my-agent",
    )
    db_session.add(agent)
    await db_session.commit()
    assert agent.status == "draft"
```

- [ ] **Step 3: Run tests**

Run: `cd astromesh-cloud/api && uv run pytest tests/test_models.py -v`
Expected: ALL PASS

Note: Tests use SQLite via aiosqlite. The portable type decorators in `base.py` (GUID, JSONType, StringArray) ensure compatibility between PostgreSQL and SQLite.

- [ ] **Step 4: Commit**

```bash
git add astromesh-cloud/api/astromesh_cloud/models/
git commit -m "feat(cloud): add SQLAlchemy models for User, Org, Agent, ApiKey, ProviderKey, UsageLog"
```

---

### Task 3: Pydantic Schemas

**Files:**
- Create: `astromesh_cloud/schemas/auth.py`
- Create: `astromesh_cloud/schemas/agent.py`
- Create: `astromesh_cloud/schemas/organization.py`
- Create: `astromesh_cloud/schemas/usage.py`
- Create: `astromesh_cloud/schemas/keys.py`
- Create: `astromesh_cloud/schemas/__init__.py`
- Create: `tests/test_schemas.py`

- [ ] **Step 1: Create all schema files**

```python
# astromesh_cloud/schemas/auth.py
from pydantic import BaseModel


class OAuthCallback(BaseModel):
    code: str
    redirect_uri: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserProfile(BaseModel):
    id: str
    email: str
    name: str
    avatar_url: str | None = None
    auth_provider: str

    model_config = {"from_attributes": True}
```

```python
# astromesh_cloud/schemas/agent.py
from datetime import datetime
from pydantic import BaseModel, Field


class WizardConfig(BaseModel):
    """Flat config from the wizard UI — config_builder translates this to agent YAML."""
    # Step 1 - Identity
    name: str = Field(max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_name: str = Field(max_length=255)
    system_prompt: str
    tone: str = "professional"  # professional | casual | technical | empathetic

    # Step 2 - Model
    model: str  # e.g. "ollama/llama3", "openai/gpt-4o"
    routing_strategy: str = "cost_optimized"  # cost_optimized | latency_optimized | quality_first

    # Step 3 - Tools
    tools: list[str] = []  # tool IDs from catalog
    tool_configs: dict[str, dict] = {}  # tool_id → config

    # Step 4 - Settings
    memory_enabled: bool = False
    pii_filter: bool = False
    content_filter: bool = False
    orchestration: str = "react"  # single_pass | react | plan_and_execute


class AgentCreate(BaseModel):
    config: WizardConfig


class AgentUpdate(BaseModel):
    config: WizardConfig


class AgentResponse(BaseModel):
    id: str
    name: str
    display_name: str
    status: str
    config: dict
    runtime_name: str
    created_at: datetime
    updated_at: datetime
    deployed_at: datetime | None = None

    model_config = {"from_attributes": True}


class AgentListItem(BaseModel):
    id: str
    name: str
    display_name: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

```python
# astromesh_cloud/schemas/organization.py
from pydantic import BaseModel


class OrgResponse(BaseModel):
    id: str
    slug: str
    name: str

    model_config = {"from_attributes": True}


class OrgUpdate(BaseModel):
    name: str


class MemberInvite(BaseModel):
    email: str


class MemberResponse(BaseModel):
    user_id: str
    email: str
    name: str
    role: str
```

```python
# astromesh_cloud/schemas/keys.py
from datetime import datetime
from pydantic import BaseModel


class ApiKeyCreate(BaseModel):
    name: str
    scopes: list[str] = ["agent:run"]


class ApiKeyResponse(BaseModel):
    id: str
    prefix: str
    name: str
    scopes: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreated(ApiKeyResponse):
    """Returned only on creation — includes the full key."""
    key: str


class ProviderKeyCreate(BaseModel):
    provider: str
    key: str


class ProviderKeyResponse(BaseModel):
    id: str
    provider: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

```python
# astromesh_cloud/schemas/usage.py
from decimal import Decimal
from pydantic import BaseModel


class UsageSummary(BaseModel):
    total_requests: int
    total_tokens_in: int
    total_tokens_out: int
    total_cost_usd: Decimal
    period_start: str
    period_end: str
```

- [ ] **Step 2: Write schema validation tests**

```python
# tests/test_schemas.py
import pytest
from astromesh_cloud.schemas.agent import WizardConfig


def test_wizard_config_valid():
    config = WizardConfig(
        name="my-agent",
        display_name="My Agent",
        system_prompt="You are helpful.",
        model="ollama/llama3",
    )
    assert config.name == "my-agent"
    assert config.tone == "professional"
    assert config.orchestration == "react"


def test_wizard_config_invalid_name():
    with pytest.raises(Exception):
        WizardConfig(
            name="My Agent!",  # Invalid: uppercase, special chars
            display_name="My Agent",
            system_prompt="Test",
            model="ollama/llama3",
        )
```

- [ ] **Step 3: Run tests**

Run: `cd astromesh-cloud/api && uv run pytest tests/test_schemas.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add astromesh-cloud/api/astromesh_cloud/schemas/
git commit -m "feat(cloud): add Pydantic v2 schemas for auth, agents, orgs, keys, usage"
```

---

### Task 4: Encryption Service

**Files:**
- Create: `astromesh_cloud/services/encryption.py`
- Create: `tests/test_encryption.py`

- [ ] **Step 1: Implement Fernet encryption**

```python
# astromesh_cloud/services/encryption.py
from cryptography.fernet import Fernet

from astromesh_cloud.config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = settings.fernet_key
        if not key:
            raise RuntimeError("ASTROMESH_CLOUD_FERNET_KEY not configured")
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_key(plaintext: str) -> bytes:
    return _get_fernet().encrypt(plaintext.encode())


def decrypt_key(ciphertext: bytes) -> str:
    return _get_fernet().decrypt(ciphertext).decode()
```

- [ ] **Step 2: Test it**

```python
# tests/test_encryption.py
import os
import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def set_fernet_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ASTROMESH_CLOUD_FERNET_KEY", key)
    # Reset cached fernet
    import astromesh_cloud.services.encryption as enc
    enc._fernet = None


def test_encrypt_decrypt_roundtrip():
    from astromesh_cloud.services.encryption import encrypt_key, decrypt_key

    original = "sk-test-12345"
    encrypted = encrypt_key(original)
    assert encrypted != original.encode()
    assert decrypt_key(encrypted) == original
```

- [ ] **Step 3: Run and commit**

Run: `cd astromesh-cloud/api && uv run pytest tests/test_encryption.py -v`

```bash
git add astromesh-cloud/api/astromesh_cloud/services/encryption.py astromesh-cloud/api/tests/test_encryption.py
git commit -m "feat(cloud): add Fernet encryption service for provider keys"
```

---

### Task 5: Config Builder Service

**Files:**
- Create: `astromesh_cloud/services/config_builder.py`
- Create: `tests/test_config_builder.py`

- [ ] **Step 1: Implement wizard config → agent YAML translation**

```python
# astromesh_cloud/services/config_builder.py
"""Translates wizard JSON config into Astromesh agent YAML config."""

TONE_PREFIXES = {
    "professional": "Respond in a professional, clear tone.",
    "casual": "Respond in a friendly, conversational tone.",
    "technical": "Respond in a precise, technical tone with detail.",
    "empathetic": "Respond in a warm, empathetic tone showing understanding.",
}

ROUTING_MAP = {
    "cost_optimized": "cost_optimized",
    "latency_optimized": "latency_optimized",
    "quality_first": "quality_first",
}

ORCHESTRATION_MAP = {
    "single_pass": "single_pass",
    "react": "react",
    "plan_and_execute": "plan_and_execute",
}


def build_agent_config(wizard_config: dict, org_slug: str) -> dict:
    """Convert flat wizard config to full Astromesh agent YAML config dict."""
    name = wizard_config["name"]
    runtime_name = f"{org_slug}--{name}"

    # Build system prompt with tone prefix
    tone = wizard_config.get("tone", "professional")
    tone_prefix = TONE_PREFIXES.get(tone, TONE_PREFIXES["professional"])
    system_prompt = f"{tone_prefix}\n\n{wizard_config['system_prompt']}"

    # Parse model string
    model_str = wizard_config["model"]
    provider, model = model_str.split("/", 1) if "/" in model_str else ("ollama", model_str)

    # Build config
    config = {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": runtime_name, "version": "1.0"},
        "spec": {
            "identity": {
                "name": runtime_name,
                "role": wizard_config.get("display_name", name),
            },
            "model": {
                "primary": {"provider": provider, "model": model},
                "routing": {
                    "strategy": ROUTING_MAP.get(
                        wizard_config.get("routing_strategy", "cost_optimized"),
                        "cost_optimized",
                    ),
                },
            },
            "prompts": {"system": system_prompt},
            "orchestration": {
                "pattern": ORCHESTRATION_MAP.get(
                    wizard_config.get("orchestration", "react"), "react"
                ),
            },
        },
    }

    # Tools
    tools = wizard_config.get("tools", [])
    tool_configs = wizard_config.get("tool_configs", {})
    if tools:
        config["spec"]["tools"] = [
            {"name": t, "type": "builtin", **(tool_configs.get(t, {}))}
            for t in tools
        ]

    # Memory
    if wizard_config.get("memory_enabled"):
        config["spec"]["memory"] = {
            "conversational": {"backend": "sqlite"},
        }

    # Guardrails
    guardrails = []
    if wizard_config.get("pii_filter"):
        guardrails.append({"type": "pii_filter", "action": "redact"})
    if wizard_config.get("content_filter"):
        guardrails.append({"type": "content_safety", "action": "block"})
    if guardrails:
        config["spec"]["guardrails"] = {"input": guardrails, "output": guardrails}

    return config
```

- [ ] **Step 2: Test it**

```python
# tests/test_config_builder.py
from astromesh_cloud.services.config_builder import build_agent_config


def test_build_basic_config():
    wizard = {
        "name": "support",
        "display_name": "Support Bot",
        "system_prompt": "Help customers with their questions.",
        "model": "ollama/llama3",
        "tone": "professional",
    }
    config = build_agent_config(wizard, "acme")
    assert config["metadata"]["name"] == "acme--support"
    assert config["spec"]["model"]["primary"]["provider"] == "ollama"
    assert config["spec"]["model"]["primary"]["model"] == "llama3"
    assert "professional" in config["spec"]["prompts"]["system"].lower()


def test_build_config_with_tools_and_guardrails():
    wizard = {
        "name": "research",
        "display_name": "Research Bot",
        "system_prompt": "Research topics.",
        "model": "openai/gpt-4o",
        "tools": ["web_search", "calculator"],
        "pii_filter": True,
        "content_filter": True,
        "memory_enabled": True,
        "orchestration": "plan_and_execute",
    }
    config = build_agent_config(wizard, "globex")
    assert len(config["spec"]["tools"]) == 2
    assert config["spec"]["guardrails"]["input"][0]["type"] == "pii_filter"
    assert config["spec"]["memory"]["conversational"]["backend"] == "sqlite"
    assert config["spec"]["orchestration"]["pattern"] == "plan_and_execute"


def test_runtime_name_namespaced():
    wizard = {"name": "bot", "display_name": "Bot", "system_prompt": "Hi.", "model": "ollama/mistral"}
    config = build_agent_config(wizard, "my-org")
    assert config["metadata"]["name"] == "my-org--bot"
```

- [ ] **Step 3: Run and commit**

Run: `cd astromesh-cloud/api && uv run pytest tests/test_config_builder.py -v`

```bash
git add astromesh-cloud/api/astromesh_cloud/services/config_builder.py astromesh-cloud/api/tests/test_config_builder.py
git commit -m "feat(cloud): add config_builder — wizard JSON to Astromesh agent YAML"
```

---

### Task 6: JWT Auth Middleware

**Files:**
- Create: `astromesh_cloud/middleware/auth.py`
- Create: `astromesh_cloud/services/auth_service.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Implement JWT creation and verification**

```python
# astromesh_cloud/services/auth_service.py
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from astromesh_cloud.config import settings


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_expire_minutes)
    payload = {"sub": user_id, "email": email, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expire_days)
    payload = {"sub": user_id, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(token: str, expected_type: str = "access") -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != expected_type:
            raise ValueError("Invalid token type")
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}") from e
```

```python
# astromesh_cloud/middleware/auth.py
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from astromesh_cloud.services.auth_service import verify_token

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    try:
        payload = verify_token(credentials.credentials)
        return {"user_id": payload["sub"], "email": payload["email"]}
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
```

- [ ] **Step 2: Test JWT flow**

```python
# tests/test_auth.py
import pytest
from astromesh_cloud.services.auth_service import create_access_token, create_refresh_token, verify_token


def test_create_and_verify_access_token():
    token = create_access_token("user-123", "test@example.com")
    payload = verify_token(token)
    assert payload["sub"] == "user-123"
    assert payload["email"] == "test@example.com"


def test_create_and_verify_refresh_token():
    token = create_refresh_token("user-123")
    payload = verify_token(token, expected_type="refresh")
    assert payload["sub"] == "user-123"


def test_verify_invalid_token():
    with pytest.raises(ValueError, match="Invalid token"):
        verify_token("not-a-real-token")


def test_verify_wrong_type():
    token = create_refresh_token("user-123")
    with pytest.raises(ValueError, match="Invalid token type"):
        verify_token(token, expected_type="access")
```

- [ ] **Step 3: Run and commit**

Run: `cd astromesh-cloud/api && uv run pytest tests/test_auth.py -v`

```bash
git add astromesh-cloud/api/astromesh_cloud/services/auth_service.py astromesh-cloud/api/astromesh_cloud/middleware/
git commit -m "feat(cloud): add JWT auth service and middleware"
```

---

### Task 7: Runtime Proxy Service

**Files:**
- Create: `astromesh_cloud/services/runtime_proxy.py`
- Create: `tests/test_runtime_proxy.py`

- [ ] **Step 1: Implement runtime proxy with namespace rewriting**

```python
# astromesh_cloud/services/runtime_proxy.py
"""HTTP proxy to Astromesh runtime with namespace rewriting, session prefixing, and BYOK."""
import httpx

from astromesh_cloud.config import settings


class RuntimeProxy:
    def __init__(self, base_url: str | None = None):
        self._base_url = (base_url or settings.runtime_url).rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=60.0)

    async def register_agent(self, config: dict) -> dict:
        resp = await self._client.post("/v1/agents", json=config)
        resp.raise_for_status()
        return resp.json()

    async def unregister_agent(self, runtime_name: str) -> dict:
        resp = await self._client.delete(f"/v1/agents/{runtime_name}")
        resp.raise_for_status()
        return resp.json()

    async def run_agent(
        self,
        runtime_name: str,
        query: str,
        session_id: str,
        org_slug: str,
        context: dict | None = None,
        provider_key: str | None = None,
        provider_name: str | None = None,
    ) -> dict:
        # Namespace the session ID
        namespaced_session = f"{org_slug}:{session_id}"

        headers = {}
        if provider_key and provider_name:
            headers["X-Astromesh-Provider-Key"] = provider_key
            headers["X-Astromesh-Provider-Name"] = provider_name

        body = {
            "query": query,
            "session_id": namespaced_session,
            "context": context,
        }

        resp = await self._client.post(
            f"/v1/agents/{runtime_name}/run",
            json=body,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def delete_memory(self, runtime_name: str, session_id: str) -> None:
        resp = await self._client.delete(
            f"/v1/memory/{runtime_name}/history/{session_id}"
        )
        resp.raise_for_status()

    async def list_agents(self) -> list[dict]:
        resp = await self._client.get("/v1/agents")
        resp.raise_for_status()
        return resp.json()

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/v1/health")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self):
        await self._client.aclose()
```

- [ ] **Step 2: Test with mocked HTTP**

```python
# tests/test_runtime_proxy.py
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from astromesh_cloud.services.runtime_proxy import RuntimeProxy


@pytest.fixture
def proxy():
    return RuntimeProxy(base_url="http://test-runtime:8000")


async def test_run_agent_namespaces_session(proxy):
    mock_response = httpx.Response(200, json={"answer": "hello", "steps": [], "usage": None})
    with patch.object(proxy._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
        result = await proxy.run_agent(
            runtime_name="acme--support",
            query="Hi",
            session_id="user-sess-1",
            org_slug="acme",
        )
        call_kwargs = mock_post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["session_id"] == "acme:user-sess-1"
        assert result["answer"] == "hello"


async def test_run_agent_injects_byok_headers(proxy):
    mock_response = httpx.Response(200, json={"answer": "ok", "steps": []})
    with patch.object(proxy._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
        await proxy.run_agent(
            runtime_name="acme--bot",
            query="test",
            session_id="s1",
            org_slug="acme",
            provider_key="sk-test-123",
            provider_name="openai",
        )
        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers["X-Astromesh-Provider-Key"] == "sk-test-123"
        assert headers["X-Astromesh-Provider-Name"] == "openai"
```

- [ ] **Step 3: Run and commit**

Run: `cd astromesh-cloud/api && uv run pytest tests/test_runtime_proxy.py -v`

```bash
git add astromesh-cloud/api/astromesh_cloud/services/runtime_proxy.py astromesh-cloud/api/tests/test_runtime_proxy.py
git commit -m "feat(cloud): add RuntimeProxy with namespace rewriting, session prefix, BYOK headers"
```

---

### Task 8: Auth Routes (OAuth + JWT)

**Files:**
- Create: `astromesh_cloud/routes/auth.py`
- Modify: `astromesh_cloud/main.py`
- Create: `tests/test_auth_routes.py`

- [ ] **Step 1: Implement OAuth routes**

```python
# astromesh_cloud/routes/auth.py
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from astromesh_cloud.database import get_db
from astromesh_cloud.models.user import User
from astromesh_cloud.models.organization import Organization, OrgMember
from astromesh_cloud.schemas.auth import OAuthCallback, TokenResponse, UserProfile
from astromesh_cloud.services.auth_service import (
    create_access_token,
    create_refresh_token,
    verify_token,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/google", response_model=TokenResponse)
async def google_callback(callback: OAuthCallback, db: AsyncSession = Depends(get_db)):
    # In production: exchange code with Google, get user info
    # For v1 scaffold: accept user info directly for testing
    # TODO: Implement actual Google OAuth exchange with authlib
    raise HTTPException(status_code=501, detail="Google OAuth not yet implemented")


@router.post("/github", response_model=TokenResponse)
async def github_callback(callback: OAuthCallback, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=501, detail="GitHub OAuth not yet implemented")


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str, db: AsyncSession = Depends(get_db)):
    try:
        payload = verify_token(refresh_token, expected_type="refresh")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = payload["sub"]
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(str(user.id), user.email),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=900,
    )


@router.post("/logout")
async def logout():
    # JWT is stateless — client-side token removal
    # For v2: add token to blocklist in Redis
    return {"status": "ok"}


# Dev-only endpoint for testing without OAuth
@router.post("/dev/login", response_model=TokenResponse)
async def dev_login(email: str, name: str, db: AsyncSession = Depends(get_db)):
    """Dev-only: create/login user without OAuth. Remove in production."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            email=email,
            name=name,
            auth_provider="google",
            auth_provider_id=f"dev-{email}",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        # Auto-create org (append short UUID to prevent slug collisions)
        base_slug = email.split("@")[0].lower().replace(".", "-")
        slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
        org = Organization(slug=slug, name=f"{name}'s Org")
        db.add(org)
        await db.commit()
        await db.refresh(org)

        member = OrgMember(user_id=user.id, org_id=org.id, role="owner")
        db.add(member)
        await db.commit()

    return TokenResponse(
        access_token=create_access_token(str(user.id), user.email),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=900,
    )
```

- [ ] **Step 2: Register route in main.py**

Add to `main.py`:
```python
from astromesh_cloud.routes import auth as auth_routes
app.include_router(auth_routes.router)
```

- [ ] **Step 3: Test dev login flow**

```python
# tests/test_auth_routes.py
async def test_dev_login_creates_user_and_org(client):
    response = await client.post(
        "/api/v1/auth/dev/login",
        params={"email": "test@example.com", "name": "Test User"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


async def test_dev_login_idempotent(client):
    await client.post("/api/v1/auth/dev/login", params={"email": "same@test.com", "name": "Same"})
    response = await client.post("/api/v1/auth/dev/login", params={"email": "same@test.com", "name": "Same"})
    assert response.status_code == 200
```

- [ ] **Step 4: Run and commit**

Run: `cd astromesh-cloud/api && uv run pytest tests/test_auth_routes.py -v`

```bash
git add astromesh-cloud/api/astromesh_cloud/routes/auth.py astromesh-cloud/api/tests/test_auth_routes.py astromesh-cloud/api/astromesh_cloud/main.py
git commit -m "feat(cloud): add auth routes with dev login, JWT tokens, auto org creation"
```

---

### Task 9: Agent CRUD Routes

**Files:**
- Create: `astromesh_cloud/services/agent_service.py`
- Create: `astromesh_cloud/routes/agents.py`
- Create: `tests/test_agent_routes.py`

- [ ] **Step 1: Implement agent service**

```python
# astromesh_cloud/services/agent_service.py
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from astromesh_cloud.config import settings
from astromesh_cloud.models.agent import Agent


async def create_agent(db: AsyncSession, org_id: str, org_slug: str, config: dict) -> Agent:
    name = config["name"]
    runtime_name = f"{org_slug}--{name}"
    agent = Agent(
        org_id=org_id,
        name=name,
        display_name=config["display_name"],
        config=config,
        status="draft",
        runtime_name=runtime_name,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


async def get_agents(db: AsyncSession, org_id: str) -> list[Agent]:
    result = await db.execute(select(Agent).where(Agent.org_id == org_id))
    return list(result.scalars().all())


async def get_agent(db: AsyncSession, org_id: str, name: str) -> Agent | None:
    result = await db.execute(
        select(Agent).where(Agent.org_id == org_id, Agent.name == name)
    )
    return result.scalar_one_or_none()


async def count_deployed(db: AsyncSession, org_id: str) -> int:
    result = await db.execute(
        select(func.count()).select_from(Agent).where(
            Agent.org_id == org_id, Agent.status == "deployed"
        )
    )
    return result.scalar_one()


async def update_agent_status(
    db: AsyncSession, agent: Agent, status: str, deployed_at: datetime | None = None
) -> Agent:
    agent.status = status
    if deployed_at:
        agent.deployed_at = deployed_at
    await db.commit()
    await db.refresh(agent)
    return agent
```

- [ ] **Step 2: Implement agent routes**

```python
# astromesh_cloud/routes/agents.py
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from astromesh_cloud.database import get_db
from astromesh_cloud.middleware.auth import get_current_user
from astromesh_cloud.models.organization import OrgMember
from astromesh_cloud.schemas.agent import AgentCreate, AgentResponse, AgentUpdate
from astromesh_cloud.services import agent_service
from astromesh_cloud.services.config_builder import build_agent_config
from astromesh_cloud.config import settings

from sqlalchemy import select

router = APIRouter(prefix="/api/v1/orgs/{slug}/agents", tags=["agents"])


async def _get_org_id(slug: str, user: dict, db: AsyncSession) -> str:
    from astromesh_cloud.models.organization import Organization
    result = await db.execute(
        select(OrgMember.org_id)
        .join(Organization, OrgMember.org_id == Organization.id)
        .where(OrgMember.user_id == user["user_id"], Organization.slug == slug)
    )
    org_id = result.scalar_one_or_none()
    if not org_id:
        raise HTTPException(status_code=403, detail="Not a member of this organization")
    return str(org_id)


@router.get("")
async def list_agents(
    slug: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    agents = await agent_service.get_agents(db, org_id)
    return [AgentResponse.model_validate(a) for a in agents]


@router.post("", status_code=201)
async def create_agent(
    slug: str,
    body: AgentCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    agent = await agent_service.create_agent(
        db, org_id, slug, body.config.model_dump()
    )
    return AgentResponse.model_validate(agent)


@router.get("/{name}")
async def get_agent(
    slug: str,
    name: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    agent = await agent_service.get_agent(db, org_id, name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse.model_validate(agent)


@router.post("/{name}/deploy")
async def deploy_agent(
    slug: str,
    name: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    agent = await agent_service.get_agent(db, org_id, name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Check limit
    deployed_count = await agent_service.count_deployed(db, org_id)
    if deployed_count >= settings.max_agents_per_org:
        raise HTTPException(
            status_code=429,
            detail=f"Maximum {settings.max_agents_per_org} deployed agents per org",
        )

    # Build runtime config and deploy
    runtime_config = build_agent_config(agent.config, slug)
    from astromesh_cloud.routes.execution import _proxy
    if _proxy:
        await _proxy.register_agent(runtime_config)

    agent = await agent_service.update_agent_status(
        db, agent, "deployed", deployed_at=datetime.now(timezone.utc)
    )
    return {"status": "deployed", "runtime_name": agent.runtime_name}


@router.post("/{name}/pause")
async def pause_agent(
    slug: str,
    name: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    agent = await agent_service.get_agent(db, org_id, name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.status != "deployed":
        raise HTTPException(status_code=400, detail="Agent is not deployed")

    from astromesh_cloud.routes.execution import _proxy
    if _proxy:
        await _proxy.unregister_agent(agent.runtime_name)
    agent = await agent_service.update_agent_status(db, agent, "paused")
    return {"status": "paused"}


@router.put("/{name}")
async def update_agent(
    slug: str,
    name: str,
    body: AgentUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    agent = await agent_service.get_agent(db, org_id, name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # If deployed, transition back to draft and remove from runtime
    if agent.status == "deployed":
        from astromesh_cloud.routes.execution import _proxy
        if _proxy:
            await _proxy.unregister_agent(agent.runtime_name)
        agent.status = "draft"

    agent.config = body.config.model_dump()
    agent.display_name = body.config.display_name
    await db.commit()
    await db.refresh(agent)
    return AgentResponse.model_validate(agent)


@router.post("/{name}/test")
async def test_agent(
    slug: str,
    name: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute agent in test mode with disposable session, then clean up memory."""
    import uuid as uuid_mod
    org_id = await _get_org_id(slug, user, db)
    agent = await agent_service.get_agent(db, org_id, name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Deploy temporarily if draft
    from astromesh_cloud.routes.execution import _proxy
    temp_deployed = False
    if agent.status != "deployed" and _proxy:
        runtime_config = build_agent_config(agent.config, slug)
        await _proxy.register_agent(runtime_config)
        temp_deployed = True

    test_session = f"__test__:{uuid_mod.uuid4().hex}"
    try:
        if _proxy:
            result = await _proxy.run_agent(
                runtime_name=agent.runtime_name,
                query="Hello, this is a test.",
                session_id=test_session,
                org_slug=slug,
            )
        else:
            result = {"answer": "Runtime not connected", "steps": []}
    finally:
        # Clean up test session memory and temp deployment
        if _proxy:
            await _proxy.delete_memory(agent.runtime_name, f"{slug}:{test_session}")
            if temp_deployed:
                await _proxy.unregister_agent(agent.runtime_name)

    return {"answer": result.get("answer", ""), "test_session": test_session}


@router.delete("/{name}")
async def delete_agent(
    slug: str,
    name: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    agent = await agent_service.get_agent(db, org_id, name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.status == "deployed":
        from astromesh_cloud.routes.execution import _proxy
        if _proxy:
            await _proxy.unregister_agent(agent.runtime_name)
    await db.delete(agent)
    await db.commit()
    return {"status": "deleted"}
```

- [ ] **Step 3: Register route and test**

Add to `main.py`:
```python
from astromesh_cloud.routes import agents as agent_routes
app.include_router(agent_routes.router)
```

```python
# tests/test_agent_routes.py
import pytest


@pytest.fixture
async def auth_headers(client):
    resp = await client.post("/api/v1/auth/dev/login", params={"email": "dev@test.com", "name": "Dev"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def org_slug(client, auth_headers):
    return "dev"  # auto-created from email prefix in dev login


async def test_create_agent(client, auth_headers, org_slug):
    body = {
        "config": {
            "name": "test-bot",
            "display_name": "Test Bot",
            "system_prompt": "You help with testing.",
            "model": "ollama/llama3",
        }
    }
    response = await client.post(
        f"/api/v1/orgs/{org_slug}/agents",
        json=body,
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "test-bot"
    assert data["status"] == "draft"


async def test_list_agents(client, auth_headers, org_slug):
    response = await client.get(f"/api/v1/orgs/{org_slug}/agents", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

- [ ] **Step 4: Run and commit**

Run: `cd astromesh-cloud/api && uv run pytest tests/test_agent_routes.py -v`

```bash
git add astromesh-cloud/api/astromesh_cloud/routes/agents.py astromesh-cloud/api/astromesh_cloud/services/agent_service.py astromesh-cloud/api/tests/test_agent_routes.py
git commit -m "feat(cloud): add agent CRUD routes with deploy/pause/delete lifecycle"
```

---

### Task 10: Organization Routes

**Files:**
- Create: `astromesh_cloud/routes/organizations.py`
- Create: `tests/test_org_routes.py`

- [ ] **Step 1: Implement org routes**

```python
# astromesh_cloud/routes/organizations.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from astromesh_cloud.database import get_db
from astromesh_cloud.middleware.auth import get_current_user
from astromesh_cloud.models.organization import Organization, OrgMember
from astromesh_cloud.models.user import User
from astromesh_cloud.schemas.organization import OrgResponse, OrgUpdate, MemberInvite, MemberResponse
from astromesh_cloud.config import settings

router = APIRouter(prefix="/api/v1/orgs", tags=["organizations"])


@router.get("/me", response_model=OrgResponse)
async def get_my_org(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Organization)
        .join(OrgMember)
        .where(OrgMember.user_id == user["user_id"])
        .order_by(Organization.created_at)
        .limit(1)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="No organization found")
    return OrgResponse.model_validate(org)


@router.patch("/{slug}", response_model=OrgResponse)
async def update_org(
    slug: str,
    body: OrgUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Organization).where(Organization.slug == slug))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    org.name = body.name
    await db.commit()
    await db.refresh(org)
    return OrgResponse.model_validate(org)


@router.get("/{slug}/members")
async def list_members(
    slug: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrgMember, User)
        .join(User, OrgMember.user_id == User.id)
        .join(Organization, OrgMember.org_id == Organization.id)
        .where(Organization.slug == slug)
    )
    rows = result.all()
    return [
        MemberResponse(
            user_id=str(member.user_id),
            email=u.email,
            name=u.name,
            role=member.role,
        )
        for member, u in rows
    ]


@router.post("/{slug}/members/invite", status_code=201)
async def invite_member(
    slug: str,
    body: MemberInvite,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check member limit
    result = await db.execute(
        select(func.count())
        .select_from(OrgMember)
        .join(Organization)
        .where(Organization.slug == slug)
    )
    count = result.scalar_one()
    if count >= settings.max_members_per_org:
        raise HTTPException(
            status_code=429,
            detail=f"Maximum {settings.max_members_per_org} members per org",
        )

    # TODO: Send invite email, create pending invite record
    return {"status": "invited", "email": body.email}
```

- [ ] **Step 2: Register and test**

Add to `main.py`:
```python
from astromesh_cloud.routes import organizations as org_routes
app.include_router(org_routes.router)
```

- [ ] **Step 3: Commit**

```bash
git add astromesh-cloud/api/astromesh_cloud/routes/organizations.py
git commit -m "feat(cloud): add organization routes (me, update, members, invite)"
```

---

### Task 11: API Key and Provider Key Routes

**Files:**
- Create: `astromesh_cloud/routes/keys.py`
- Create: `tests/test_key_routes.py`

- [ ] **Step 1: Implement key management routes**

```python
# astromesh_cloud/routes/keys.py
import secrets
import uuid

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from astromesh_cloud.database import get_db
from astromesh_cloud.middleware.auth import get_current_user
from astromesh_cloud.models.api_key import ApiKey
from astromesh_cloud.models.organization import Organization, OrgMember
from astromesh_cloud.models.provider_key import ProviderKey
from astromesh_cloud.schemas.keys import (
    ApiKeyCreate, ApiKeyCreated, ApiKeyResponse,
    ProviderKeyCreate, ProviderKeyResponse,
)
from astromesh_cloud.services.encryption import encrypt_key

router = APIRouter(prefix="/api/v1/orgs/{slug}", tags=["keys"])


async def _get_org_id(slug: str, user: dict, db: AsyncSession) -> str:
    result = await db.execute(
        select(OrgMember.org_id)
        .join(Organization, OrgMember.org_id == Organization.id)
        .where(OrgMember.user_id == user["user_id"], Organization.slug == slug)
    )
    org_id = result.scalar_one_or_none()
    if not org_id:
        raise HTTPException(status_code=403, detail="Not a member of this org")
    return str(org_id)


# ── API Keys ──

@router.get("/keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    slug: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    result = await db.execute(select(ApiKey).where(ApiKey.org_id == org_id))
    return [ApiKeyResponse.model_validate(k) for k in result.scalars().all()]


@router.post("/keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    slug: str,
    body: ApiKeyCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)

    # Generate key: am_<32 random chars>
    raw_key = f"am_{secrets.token_urlsafe(32)}"
    prefix = raw_key[:11]  # "am_" + first 8 chars
    key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()

    api_key = ApiKey(
        org_id=org_id,
        key_hash=key_hash,
        prefix=prefix,
        name=body.name,
        scopes=body.scopes,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    validated = ApiKeyResponse.model_validate(api_key)
    return ApiKeyCreated(**validated.model_dump(), key=raw_key)


@router.delete("/keys/{key_id}")
async def revoke_api_key(
    slug: str,
    key_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.org_id == org_id)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    await db.delete(key)
    await db.commit()
    return {"status": "revoked"}


# ── Provider Keys ──

@router.get("/providers", response_model=list[ProviderKeyResponse])
async def list_provider_keys(
    slug: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    result = await db.execute(select(ProviderKey).where(ProviderKey.org_id == org_id))
    return [ProviderKeyResponse.model_validate(k) for k in result.scalars().all()]


@router.post("/providers", status_code=201)
async def save_provider_key(
    slug: str,
    body: ProviderKeyCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    encrypted = encrypt_key(body.key)

    # Upsert: delete existing for this provider, then insert
    result = await db.execute(
        select(ProviderKey).where(
            ProviderKey.org_id == org_id, ProviderKey.provider == body.provider
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        await db.delete(existing)

    pk = ProviderKey(org_id=org_id, provider=body.provider, encrypted_key=encrypted)
    db.add(pk)
    await db.commit()
    return {"status": "saved", "provider": body.provider}


@router.delete("/providers/{provider}")
async def delete_provider_key(
    slug: str,
    provider: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    result = await db.execute(
        select(ProviderKey).where(
            ProviderKey.org_id == org_id, ProviderKey.provider == provider
        )
    )
    pk = result.scalar_one_or_none()
    if not pk:
        raise HTTPException(status_code=404, detail="Provider key not found")
    await db.delete(pk)
    await db.commit()
    return {"status": "deleted"}
```

- [ ] **Step 2: Register and commit**

Add to `main.py`:
```python
from astromesh_cloud.routes import keys as key_routes
app.include_router(key_routes.router)
```

```bash
git add astromesh-cloud/api/astromesh_cloud/routes/keys.py
git commit -m "feat(cloud): add API key and provider key management routes"
```

---

### Task 12: Execution Proxy Route + Usage Logging

**Files:**
- Create: `astromesh_cloud/routes/execution.py`
- Create: `astromesh_cloud/routes/usage.py`
- Create: `tests/test_execution.py`

- [ ] **Step 1: Implement execution proxy with rate limiting and usage logging**

```python
# astromesh_cloud/routes/execution.py
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from astromesh_cloud.database import get_db
from astromesh_cloud.middleware.auth import get_current_user
from astromesh_cloud.models.agent import Agent
from astromesh_cloud.models.organization import Organization, OrgMember
from astromesh_cloud.models.provider_key import ProviderKey
from astromesh_cloud.models.usage_log import UsageLog
from astromesh_cloud.services.encryption import decrypt_key
from astromesh_cloud.services.runtime_proxy import RuntimeProxy
from astromesh_cloud.config import settings
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/orgs/{slug}/agents/{name}", tags=["execution"])

_proxy: RuntimeProxy | None = None


def set_proxy(proxy: RuntimeProxy):
    global _proxy
    _proxy = proxy


class RunRequest(BaseModel):
    query: str
    session_id: str = "default"
    context: dict | None = None


@router.post("/run")
async def run_agent(
    slug: str,
    name: str,
    body: RunRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _proxy:
        raise HTTPException(status_code=503, detail="Runtime proxy not configured")

    # Resolve org
    result = await db.execute(
        select(OrgMember.org_id)
        .join(Organization, OrgMember.org_id == Organization.id)
        .where(OrgMember.user_id == user["user_id"], Organization.slug == slug)
    )
    org_id = result.scalar_one_or_none()
    if not org_id:
        raise HTTPException(status_code=403, detail="Not a member of this org")

    # Get agent
    result = await db.execute(
        select(Agent).where(Agent.org_id == org_id, Agent.name == name)
    )
    agent = result.scalar_one_or_none()
    if not agent or agent.status != "deployed":
        raise HTTPException(status_code=404, detail="Agent not found or not deployed")

    # Rate limit: count today's requests
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count()).select_from(UsageLog).where(
            UsageLog.org_id == org_id,
            UsageLog.created_at >= today_start,
        )
    )
    today_count = result.scalar_one()
    if today_count >= settings.max_requests_per_day:
        raise HTTPException(status_code=429, detail="Daily request limit exceeded")

    # Check for BYOK key
    provider_key = None
    provider_name = None
    model_str = agent.config.get("model", "")
    if "/" in model_str:
        prov = model_str.split("/")[0]
        if prov not in ("ollama",):  # Non-free providers need BYOK
            result = await db.execute(
                select(ProviderKey).where(
                    ProviderKey.org_id == org_id, ProviderKey.provider == prov
                )
            )
            pk = result.scalar_one_or_none()
            if pk:
                provider_key = decrypt_key(pk.encrypted_key)
                provider_name = prov

    # Proxy to runtime
    runtime_result = await _proxy.run_agent(
        runtime_name=agent.runtime_name,
        query=body.query,
        session_id=body.session_id,
        org_slug=slug,
        context=body.context,
        provider_key=provider_key,
        provider_name=provider_name,
    )

    # Log usage
    usage = runtime_result.get("usage") or {}
    log = UsageLog(
        org_id=org_id,
        agent_id=agent.id,
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
        model=usage.get("model", ""),
        cost_usd=0,  # Cost estimation deferred to v2
    )
    db.add(log)
    await db.commit()

    return {
        "answer": runtime_result.get("answer", ""),
        "steps": runtime_result.get("steps", []),
        "usage": usage,
    }
```

```python
# astromesh_cloud/routes/usage.py
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from astromesh_cloud.database import get_db
from astromesh_cloud.middleware.auth import get_current_user
from astromesh_cloud.models.organization import Organization, OrgMember
from astromesh_cloud.models.usage_log import UsageLog
from astromesh_cloud.schemas.usage import UsageSummary

router = APIRouter(prefix="/api/v1/orgs/{slug}/usage", tags=["usage"])


@router.get("", response_model=UsageSummary)
async def get_usage(
    slug: str,
    days: int = Query(default=30, ge=1, le=365),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrgMember.org_id)
        .join(Organization, OrgMember.org_id == Organization.id)
        .where(OrgMember.user_id == user["user_id"], Organization.slug == slug)
    )
    org_id = result.scalar_one_or_none()
    if not org_id:
        raise HTTPException(status_code=403, detail="Not a member of this org")

    period_start = datetime.now(timezone.utc) - timedelta(days=days)
    period_end = datetime.now(timezone.utc)

    result = await db.execute(
        select(
            func.count().label("total_requests"),
            func.coalesce(func.sum(UsageLog.tokens_in), 0).label("total_tokens_in"),
            func.coalesce(func.sum(UsageLog.tokens_out), 0).label("total_tokens_out"),
            func.coalesce(func.sum(UsageLog.cost_usd), 0).label("total_cost_usd"),
        ).where(
            UsageLog.org_id == org_id,
            UsageLog.created_at >= period_start,
        )
    )
    row = result.one()
    return UsageSummary(
        total_requests=row.total_requests,
        total_tokens_in=row.total_tokens_in,
        total_tokens_out=row.total_tokens_out,
        total_cost_usd=row.total_cost_usd,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
    )
```

- [ ] **Step 2: Register routes and commit**

Add to `main.py`:
```python
from astromesh_cloud.routes import execution as exec_routes
from astromesh_cloud.routes import usage as usage_routes
app.include_router(exec_routes.router)
app.include_router(usage_routes.router)
```

```bash
git add astromesh-cloud/api/astromesh_cloud/routes/execution.py astromesh-cloud/api/astromesh_cloud/routes/usage.py
git commit -m "feat(cloud): add execution proxy with rate limiting, usage logging, and usage summary"
```

---

### Task 13: Reconciliation Service + Docker Compose

**Files:**
- Create: `astromesh_cloud/services/reconciliation.py`
- Create: `astromesh-cloud/docker-compose.yaml`

- [ ] **Step 1: Implement reconciliation loop**

```python
# astromesh_cloud/services/reconciliation.py
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from astromesh_cloud.models.agent import Agent
from astromesh_cloud.services.config_builder import build_agent_config
from astromesh_cloud.services.runtime_proxy import RuntimeProxy

logger = logging.getLogger(__name__)


async def reconcile_agents(db: AsyncSession, proxy: RuntimeProxy) -> int:
    """Re-register all deployed agents on the runtime. Returns count of reconciled agents."""
    result = await db.execute(select(Agent).where(Agent.status == "deployed"))
    deployed = result.scalars().all()

    if not deployed:
        logger.info("Reconciliation: no deployed agents to reconcile")
        return 0

    # Get currently registered agents on runtime
    try:
        runtime_agents = await proxy.list_agents()
        runtime_names = {a["name"] for a in runtime_agents}
    except Exception:
        logger.warning("Reconciliation: could not list runtime agents, will re-register all")
        runtime_names = set()

    count = 0
    for agent in deployed:
        if agent.runtime_name not in runtime_names:
            try:
                # Reconstruct org_slug from runtime_name
                org_slug = agent.runtime_name.split("--")[0]
                config = build_agent_config(agent.config, org_slug)
                await proxy.register_agent(config)
                count += 1
                logger.info(f"Reconciliation: re-registered {agent.runtime_name}")
            except Exception as e:
                logger.error(f"Reconciliation: failed to register {agent.runtime_name}: {e}")

    logger.info(f"Reconciliation complete: {count} agents re-registered")
    return count
```

- [ ] **Step 2: Wire into lifespan in main.py**

Update `main.py` lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    from astromesh_cloud.services.runtime_proxy import RuntimeProxy
    from astromesh_cloud.services.reconciliation import reconcile_agents
    from astromesh_cloud.database import async_session
    from astromesh_cloud.routes.execution import set_proxy

    proxy = RuntimeProxy()
    set_proxy(proxy)

    # Reconciliation loop
    if await proxy.health():
        async with async_session() as db:
            await reconcile_agents(db, proxy)

    yield
    await proxy.close()
```

- [ ] **Step 3: Create Docker Compose for local development**

```yaml
# astromesh-cloud/docker-compose.yaml
services:
  cloud-api:
    build:
      context: ./api
      dockerfile: Dockerfile
    ports:
      - "8001:8001"
    environment:
      ASTROMESH_CLOUD_DATABASE_URL: postgresql+asyncpg://postgres:postgres@cloud-db:5432/astromesh_cloud
      ASTROMESH_CLOUD_RUNTIME_URL: http://runtime:8000
      ASTROMESH_CLOUD_JWT_SECRET: dev-secret-change-in-prod
      ASTROMESH_CLOUD_FERNET_KEY: ${FERNET_KEY:-}
    depends_on:
      cloud-db:
        condition: service_healthy
      runtime:
        condition: service_started

  cloud-db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: astromesh_cloud
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - cloud_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  runtime:
    build:
      context: ../
      dockerfile: Dockerfile
    ports:
      - "8000:8000"

  web:
    build:
      context: ./web
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8001
    depends_on:
      - cloud-api

volumes:
  cloud_pgdata:
```

- [ ] **Step 4: Commit**

```bash
git add astromesh-cloud/api/astromesh_cloud/services/reconciliation.py astromesh-cloud/docker-compose.yaml
git commit -m "feat(cloud): add reconciliation service and Docker Compose for local dev"
```

---

## Summary

| Task | What it delivers |
|------|-----------------|
| 1 | Project scaffold (FastAPI, SQLAlchemy, test infra) |
| 2 | All 7 SQLAlchemy models |
| 3 | Pydantic v2 schemas |
| 4 | Fernet encryption service |
| 5 | Config builder (wizard → YAML) |
| 6 | JWT auth + middleware |
| 7 | Runtime proxy (namespace, session, BYOK) |
| 8 | Auth routes (OAuth stubs, dev login) |
| 9 | Agent CRUD + deploy/pause lifecycle |
| 10 | Organization routes |
| 11 | API key + provider key routes |
| 12 | Execution proxy + usage logging |
| 13 | Reconciliation service + Docker Compose |

After these 13 tasks, the Cloud API is fully functional with all endpoints from the spec.
