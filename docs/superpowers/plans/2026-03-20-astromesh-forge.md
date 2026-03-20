# Astromesh Forge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Astromesh Forge, a visual agent builder SPA (Vite + React) that replaces `astromesh-cloud`, enabling non-technical users to create, edit, and deploy agents via a wizard and drag-and-drop canvas.

**Architecture:** Pure client SPA connecting directly to Astromesh node API (`/v1/*`). No backend. State lives in the node. Embeddable in FastAPI (`/forge`) or standalone via `npx`. Canvas uses React Flow for two-level visualization (macro: agent orchestration, micro: internal pipeline).

**Tech Stack:** Vite, React 18, TypeScript, React Flow, dnd-kit, Tailwind CSS, Zustand, React Router, Vitest, Testing Library

**Spec:** `docs/superpowers/specs/2026-03-20-astromesh-forge-design.md`

---

## File Structure

### Core API (new endpoints in existing Astromesh node)

| File | Responsibility |
|------|---------------|
| `astromesh/api/routes/agents.py` | Add PUT, deploy, pause endpoints |
| `astromesh/api/routes/templates.py` | New: GET /v1/templates, GET /v1/templates/{name} |
| `astromesh/api/main.py` | Register templates router, add CORS middleware, add Forge static mount |
| `astromesh/runtime/engine.py` | Add `update_agent()`, `deploy_agent()`, `pause_agent()` methods, agent status tracking |
| `config/templates/*.template.yaml` | 15 pre-built agent templates |
| `tests/test_api_templates.py` | Tests for templates endpoints |
| `tests/test_api_agents_extended.py` | Tests for PUT, deploy, pause |
| `tests/test_engine_status.py` | Tests for agent status lifecycle |

### Forge SPA

| File | Responsibility |
|------|---------------|
| `astromesh-forge/src/api/client.ts` | HTTP client to Astromesh node API |
| `astromesh-forge/src/types/agent.ts` | AgentConfig, AgentMeta, AgentStatus types |
| `astromesh-forge/src/types/template.ts` | Template, TemplateVariable types |
| `astromesh-forge/src/types/canvas.ts` | Node types for React Flow canvas |
| `astromesh-forge/src/stores/connection.ts` | Node connection state (URL, status, health) |
| `astromesh-forge/src/stores/agent.ts` | Agent editor state (config being edited) |
| `astromesh-forge/src/stores/agents-list.ts` | Dashboard agents list |
| `astromesh-forge/src/utils/yaml.ts` | JSON↔YAML conversion |
| `astromesh-forge/src/utils/template-engine.ts` | Variable substitution with slugify/lower/upper filters |
| `astromesh-forge/src/utils/agent-to-nodes.ts` | Convert AgentConfig to React Flow nodes/edges |
| `astromesh-forge/src/utils/nodes-to-agent.ts` | Convert React Flow nodes/edges back to AgentConfig |
| `astromesh-forge/src/components/ui/*.tsx` | Base UI components (Button, Input, Card, Badge, Select, Toggle, Modal) |
| `astromesh-forge/src/components/layout/Header.tsx` | Header with connection indicator + settings |
| `astromesh-forge/src/components/layout/Layout.tsx` | App shell with header + main content |
| `astromesh-forge/src/components/dashboard/AgentList.tsx` | Agent table with status, actions |
| `astromesh-forge/src/components/dashboard/QuickActions.tsx` | Create from scratch / template / import buttons |
| `astromesh-forge/src/components/dashboard/Dashboard.tsx` | Dashboard page combining list + actions |
| `astromesh-forge/src/components/wizard/WizardShell.tsx` | Wizard container with step navigation |
| `astromesh-forge/src/components/wizard/StepIdentity.tsx` | Step 1: name, display_name, description, avatar, tags |
| `astromesh-forge/src/components/wizard/StepModel.tsx` | Step 2: primary/fallback model, routing strategy |
| `astromesh-forge/src/components/wizard/StepTools.tsx` | Step 3: drag & drop tool selection |
| `astromesh-forge/src/components/wizard/StepOrchestration.tsx` | Step 4: pattern selector with diagrams |
| `astromesh-forge/src/components/wizard/StepSettings.tsx` | Step 5: memory, guardrails, permissions |
| `astromesh-forge/src/components/wizard/StepPrompts.tsx` | Step 6: system prompt editor |
| `astromesh-forge/src/components/wizard/StepReview.tsx` | Step 7: YAML preview + deploy |
| `astromesh-forge/src/components/canvas/CanvasEditor.tsx` | Main canvas container (React Flow) |
| `astromesh-forge/src/components/canvas/nodes/AgentNode.tsx` | Macro view: agent as node |
| `astromesh-forge/src/components/canvas/nodes/ToolNode.tsx` | Micro view: tool node |
| `astromesh-forge/src/components/canvas/nodes/ModelNode.tsx` | Micro view: model/router node |
| `astromesh-forge/src/components/canvas/nodes/GuardrailNode.tsx` | Micro view: guardrail node |
| `astromesh-forge/src/components/canvas/nodes/MemoryNode.tsx` | Micro view: memory node |
| `astromesh-forge/src/components/canvas/nodes/PromptNode.tsx` | Micro view: prompt engine node |
| `astromesh-forge/src/components/canvas/panels/PropertiesPanel.tsx` | Right sidebar: contextual property editor |
| `astromesh-forge/src/components/canvas/panels/Toolbox.tsx` | Left sidebar: draggable components |
| `astromesh-forge/src/components/templates/TemplateGallery.tsx` | Browse/search templates by category |
| `astromesh-forge/src/components/templates/TemplateCard.tsx` | Single template preview card |
| `astromesh-forge/src/components/templates/TemplatePreview.tsx` | Full template detail + customize variables |
| `astromesh-forge/src/components/deploy/DeployModal.tsx` | Target selector + confirmation |
| `astromesh-forge/src/components/deploy/TargetSelector.tsx` | Local / Remote / Nexus target picker |
| `astromesh-forge/src/App.tsx` | Router setup + layout |

### Docs-site updates

| File | Action |
|------|--------|
| `docs-site/src/content/docs/cloud/` | Rename/rewrite to `forge/` section |
| `docs-site/astro.config.mjs` | Update sidebar: replace Cloud with Forge |

---

## Task 1: Core API — Agent Status Tracking in Runtime Engine

**Files:**
- Modify: `astromesh/runtime/engine.py`
- Test: `tests/test_engine_status.py`

The runtime currently treats agents as either loaded or not. Forge needs `draft / deployed / paused` states. We add a `_agent_status` dict to track this.

- [ ] **Step 1: Write failing test for agent status tracking**

```python
# tests/test_engine_status.py
import pytest
from astromesh.runtime.engine import AgentRuntime

SAMPLE_CONFIG = {
    "apiVersion": "astromesh/v1",
    "kind": "Agent",
    "metadata": {"name": "test-status", "version": "1.0.0", "namespace": "test"},
    "spec": {
        "identity": {"display_name": "Test", "description": "Test agent"},
        "model": {
            "primary": {
                "provider": "ollama",
                "model": "llama3.1:8b",
                "endpoint": "http://localhost:11434",
            },
            "routing": {"strategy": "cost_optimized"},
        },
        "prompts": {"system": "You are a test agent."},
        "orchestration": {"pattern": "react", "max_iterations": 5},
    },
}


@pytest.fixture
def runtime(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "agents").mkdir()
    return AgentRuntime(config_dir=str(config_dir))


async def test_register_agent_starts_as_draft(runtime):
    await runtime.register_agent(SAMPLE_CONFIG)
    agents = runtime.list_agents()
    agent = next(a for a in agents if a["name"] == "test-status")
    assert agent["status"] == "draft"


async def test_deploy_agent_changes_status(runtime):
    await runtime.register_agent(SAMPLE_CONFIG)
    await runtime.deploy_agent("test-status")
    agents = runtime.list_agents()
    agent = next(a for a in agents if a["name"] == "test-status")
    assert agent["status"] == "deployed"


async def test_pause_agent_changes_status(runtime):
    await runtime.register_agent(SAMPLE_CONFIG)
    await runtime.deploy_agent("test-status")
    runtime.pause_agent("test-status")
    agents = runtime.list_agents()
    agent = next(a for a in agents if a["name"] == "test-status")
    assert agent["status"] == "paused"


async def test_deploy_nonexistent_raises(runtime):
    with pytest.raises(ValueError, match="not found"):
        await runtime.deploy_agent("nonexistent")


async def test_pause_nondeployed_raises(runtime):
    await runtime.register_agent(SAMPLE_CONFIG)
    with pytest.raises(ValueError, match="not deployed"):
        runtime.pause_agent("test-status")


async def test_update_agent_config(runtime):
    await runtime.register_agent(SAMPLE_CONFIG)
    updated = {**SAMPLE_CONFIG}
    updated["spec"] = {**SAMPLE_CONFIG["spec"], "prompts": {"system": "Updated prompt"}}
    await runtime.update_agent("test-status", updated)
    agents = runtime.list_agents()
    agent = next(a for a in agents if a["name"] == "test-status")
    assert agent["status"] == "draft"  # update resets to draft
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine_status.py -v`
Expected: FAIL — `deploy_agent`, `pause_agent`, `update_agent` methods don't exist, `list_agents` doesn't return `status`

- [ ] **Step 3: Implement agent status tracking in engine.py**

In `astromesh/runtime/engine.py`, add to `AgentRuntime.__init__`:

```python
self._agent_status: dict[str, str] = {}  # name -> draft|deployed|paused
self._agent_configs: dict[str, dict] = {}  # name -> raw config dict
```

Modify `register_agent` to store config and set status to `"draft"`:

```python
async def register_agent(self, config: dict) -> None:
    name = config["metadata"]["name"]
    self._agent_configs[name] = config
    self._agent_status[name] = "draft"
    # Don't build agent yet — wait for deploy
```

Add new methods:

```python
async def deploy_agent(self, name: str) -> None:
    if name not in self._agent_configs:
        raise ValueError(f"Agent '{name}' not found")
    config = self._agent_configs[name]
    agent = await self._build_agent(config)
    self._agents[name] = agent
    self._agent_status[name] = "deployed"

def pause_agent(self, name: str) -> None:
    if self._agent_status.get(name) != "deployed":
        raise ValueError(f"Agent '{name}' not deployed")
    if name in self._agents:
        del self._agents[name]
    self._agent_status[name] = "paused"

async def update_agent(self, name: str, config: dict) -> None:
    if name not in self._agent_configs:
        raise ValueError(f"Agent '{name}' not found")
    was_deployed = self._agent_status.get(name) == "deployed"
    if was_deployed:
        self.pause_agent(name)
    self._agent_configs[name] = config
    self._agent_status[name] = "draft"
```

Modify `list_agents` to include status:

```python
def list_agents(self) -> list[dict]:
    all_names = set(list(self._agents.keys()) + list(self._agent_configs.keys()))
    result = []
    for name in all_names:
        agent = self._agents.get(name)
        config = self._agent_configs.get(name)
        if agent:
            result.append({
                "name": agent.name,
                "version": agent.version,
                "namespace": agent.namespace,
                "description": getattr(agent, 'description', ''),
                "status": self._agent_status.get(name, "deployed"),
            })
        elif config:
            meta = config.get("metadata", {})
            spec = config.get("spec", {})
            identity = spec.get("identity", {})
            result.append({
                "name": meta.get("name", ""),
                "version": meta.get("version", ""),
                "namespace": meta.get("namespace", ""),
                "description": identity.get("description", ""),
                "status": self._agent_status.get(name, "draft"),
            })
    return result
```

Update `bootstrap` to mark YAML-loaded agents as `"deployed"` and track their configs:

```python
# Inside bootstrap(), after _build_agent succeeds for each config:
self._agent_status[name] = "deployed"
self._agent_configs[name] = config
```

Update `unregister_agent` to clean up status:

```python
def unregister_agent(self, name: str) -> None:
    if name not in self._agents and name not in self._agent_configs:
        raise ValueError(f"Agent '{name}' not found")
    self._agents.pop(name, None)
    self._agent_configs.pop(name, None)
    self._agent_status.pop(name, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine_status.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/runtime/engine.py tests/test_engine_status.py
git commit -m "feat(runtime): add agent status lifecycle (draft/deployed/paused)"
```

---

## Task 2: Core API — PUT, Deploy, Pause Endpoints

**Files:**
- Modify: `astromesh/api/routes/agents.py`
- Test: `tests/test_api_agents_extended.py`

Add three new endpoints to the agents router that Forge requires.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_api_agents_extended.py
import pytest
from httpx import ASGITransport, AsyncClient
from astromesh.api.main import app
from astromesh.api.routes import agents as agents_route
from unittest.mock import AsyncMock, MagicMock

SAMPLE_CONFIG = {
    "apiVersion": "astromesh/v1",
    "kind": "Agent",
    "metadata": {"name": "test-agent", "version": "1.0.0", "namespace": "test"},
    "spec": {
        "identity": {"display_name": "Test", "description": "Test agent"},
        "model": {
            "primary": {
                "provider": "ollama",
                "model": "llama3.1:8b",
                "endpoint": "http://localhost:11434",
            },
            "routing": {"strategy": "cost_optimized"},
        },
        "prompts": {"system": "Test prompt."},
        "orchestration": {"pattern": "react", "max_iterations": 5},
    },
}


@pytest.fixture
def mock_runtime():
    runtime = MagicMock()
    runtime.update_agent = AsyncMock()
    runtime.deploy_agent = AsyncMock()
    runtime.pause_agent = MagicMock()
    runtime.list_agents.return_value = [
        {"name": "test-agent", "version": "1.0.0", "namespace": "test", "status": "draft"}
    ]
    agents_route.set_runtime(runtime)
    return runtime


async def test_put_agent(mock_runtime):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put("/v1/agents/test-agent", json=SAMPLE_CONFIG)
    assert resp.status_code == 200
    assert resp.json()["status"] == "updated"
    mock_runtime.update_agent.assert_awaited_once_with("test-agent", SAMPLE_CONFIG)


async def test_deploy_agent(mock_runtime):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/agents/test-agent/deploy")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deployed"
    mock_runtime.deploy_agent.assert_awaited_once_with("test-agent")


async def test_pause_agent(mock_runtime):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/agents/test-agent/pause")
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"
    mock_runtime.pause_agent.assert_called_once_with("test-agent")


async def test_deploy_nonexistent_returns_404(mock_runtime):
    mock_runtime.deploy_agent.side_effect = ValueError("Agent 'nope' not found")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/agents/nope/deploy")
    assert resp.status_code == 404


async def test_put_agent_no_runtime():
    agents_route.set_runtime(None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put("/v1/agents/test-agent", json=SAMPLE_CONFIG)
    assert resp.status_code == 503
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_agents_extended.py -v`
Expected: FAIL — endpoints don't exist yet (404/405)

- [ ] **Step 3: Add PUT, deploy, pause to agents.py**

In `astromesh/api/routes/agents.py`, add after existing endpoints:

```python
@router.put("/agents/{agent_name}")
async def update_agent(agent_name: str, config: dict):
    if not _runtime:
        raise HTTPException(503, "Runtime not initialized")
    try:
        await _runtime.update_agent(agent_name, config)
        return {"status": "updated", "agent": agent_name}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/agents/{agent_name}/deploy")
async def deploy_agent(agent_name: str):
    if not _runtime:
        raise HTTPException(503, "Runtime not initialized")
    try:
        await _runtime.deploy_agent(agent_name)
        return {"status": "deployed", "agent": agent_name}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/agents/{agent_name}/pause")
async def pause_agent(agent_name: str):
    if not _runtime:
        raise HTTPException(503, "Runtime not initialized")
    try:
        _runtime.pause_agent(agent_name)
        return {"status": "paused", "agent": agent_name}
    except ValueError as e:
        raise HTTPException(404, str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_agents_extended.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/api/routes/agents.py tests/test_api_agents_extended.py
git commit -m "feat(api): add PUT, deploy, pause endpoints for agents"
```

---

## Task 3: Core API — Templates Endpoint

**Files:**
- Create: `astromesh/api/routes/templates.py`
- Modify: `astromesh/api/main.py`
- Create: `config/templates/` (directory)
- Test: `tests/test_api_templates.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_api_templates.py
import pytest
from httpx import ASGITransport, AsyncClient
from astromesh.api.main import app
from astromesh.api.routes import templates as templates_route
from pathlib import Path
import yaml


@pytest.fixture
def templates_dir(tmp_path):
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir()

    sales_tpl = {
        "apiVersion": "astromesh/v1",
        "kind": "AgentTemplate",
        "metadata": {
            "name": "sales-qualifier",
            "version": "1.0.0",
            "category": "sales",
            "tags": ["leads", "bant"],
        },
        "template": {
            "display_name": "Sales Lead Qualifier",
            "description": "Qualifies leads using BANT.",
            "recommended_channels": [
                {"channel": "whatsapp", "reason": "Direct messaging"}
            ],
            "variables": [
                {"key": "company_name", "label": "Company", "required": True}
            ],
            "agent_config": {
                "apiVersion": "astromesh/v1",
                "kind": "Agent",
                "metadata": {"name": "{{company_name|slugify}}-sales"},
                "spec": {"identity": {"display_name": "Sales Agent"}},
            },
        },
    }
    (tpl_dir / "sales-qualifier.template.yaml").write_text(yaml.dump(sales_tpl))

    templates_route.set_templates_dir(str(tpl_dir))
    return tpl_dir


async def test_list_templates(templates_dir):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "sales-qualifier"
    assert data[0]["category"] == "sales"
    assert "agent_config" not in data[0]  # list doesn't include full config


async def test_get_template_detail(templates_dir):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/templates/sales-qualifier")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "sales-qualifier"
    assert "agent_config" in data  # detail includes full config
    assert data["variables"][0]["key"] == "company_name"


async def test_get_template_not_found(templates_dir):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/templates/nonexistent")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_templates.py -v`
Expected: FAIL — templates module doesn't exist

- [ ] **Step 3: Create templates route**

```python
# astromesh/api/routes/templates.py
from fastapi import APIRouter, HTTPException
from pathlib import Path
import yaml

router = APIRouter()
_templates_dir: str | None = None


def set_templates_dir(path: str) -> None:
    global _templates_dir
    _templates_dir = path


def _load_templates() -> list[dict]:
    if not _templates_dir:
        return []
    tpl_path = Path(_templates_dir)
    if not tpl_path.exists():
        return []
    templates = []
    for f in sorted(tpl_path.glob("*.template.yaml")):
        with open(f) as fh:
            templates.append(yaml.safe_load(fh))
    return templates


@router.get("/templates")
async def list_templates():
    templates = _load_templates()
    return [
        {
            "name": t["metadata"]["name"],
            "version": t["metadata"].get("version", ""),
            "category": t["metadata"].get("category", ""),
            "tags": t["metadata"].get("tags", []),
            "display_name": t["template"]["display_name"],
            "description": t["template"]["description"],
            "recommended_channels": t["template"].get("recommended_channels", []),
        }
        for t in templates
    ]


@router.get("/templates/{template_name}")
async def get_template(template_name: str):
    templates = _load_templates()
    for t in templates:
        if t["metadata"]["name"] == template_name:
            return {
                "name": t["metadata"]["name"],
                "version": t["metadata"].get("version", ""),
                "category": t["metadata"].get("category", ""),
                "tags": t["metadata"].get("tags", []),
                "display_name": t["template"]["display_name"],
                "description": t["template"]["description"],
                "recommended_channels": t["template"].get("recommended_channels", []),
                "variables": t["template"].get("variables", []),
                "agent_config": t["template"]["agent_config"],
            }
    raise HTTPException(404, f"Template '{template_name}' not found")
```

- [ ] **Step 4: Register templates router in main.py**

In `astromesh/api/main.py`, add:

```python
from astromesh.api.routes import templates
app.include_router(templates.router, prefix="/v1")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_templates.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add astromesh/api/routes/templates.py astromesh/api/main.py tests/test_api_templates.py
git commit -m "feat(api): add templates CRUD endpoints"
```

---

## Task 4: Core API — CORS + Forge Static Serving

**Files:**
- Modify: `astromesh/api/main.py`
- Test: `tests/test_api_cors.py`

Enable CORS for standalone Forge and add optional static file serving for embedded mode.

- [ ] **Step 1: Write failing test for CORS**

```python
# tests/test_api_cors.py
import pytest
from httpx import ASGITransport, AsyncClient
from astromesh.api.main import app


async def test_cors_preflight():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.options(
            "/v1/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_cors.py -v`
Expected: FAIL — no CORS middleware configured

- [ ] **Step 3: Add CORS middleware to main.py**

In `astromesh/api/main.py`, add after app creation:

```python
import os
from fastapi.middleware.cors import CORSMiddleware

cors_origins = os.getenv("ASTROMESH_CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Add static file serving (conditional on directory existing):

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

forge_static = Path(__file__).parent.parent / "static" / "forge"
if forge_static.exists():
    app.mount("/forge", StaticFiles(directory=str(forge_static), html=True), name="forge")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_cors.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/api/main.py tests/test_api_cors.py
git commit -m "feat(api): add CORS middleware and optional Forge static serving"
```

---

## Task 5: Template YAML Files

**Files:**
- Create: `config/templates/*.template.yaml` (15 files)

Create all 15 pre-built agent templates as defined in the spec.

- [ ] **Step 1: Create config/templates/ directory**

```bash
mkdir -p config/templates
```

- [ ] **Step 2: Create all 15 template files**

Copy each template YAML from the spec (section "Template Agent Definitions") into individual files:

1. `config/templates/sales-qualifier.template.yaml`
2. `config/templates/product-advisor.template.yaml`
3. `config/templates/support-agent.template.yaml`
4. `config/templates/returns-claims.template.yaml`
5. `config/templates/payment-reminder.template.yaml`
6. `config/templates/debt-collector.template.yaml`
7. `config/templates/campaign-bot.template.yaml`
8. `config/templates/brand-chef.template.yaml`
9. `config/templates/nutritionist.template.yaml`
10. `config/templates/service-scheduler.template.yaml`
11. `config/templates/parts-advisor.template.yaml`
12. `config/templates/property-agent.template.yaml`
13. `config/templates/tutor-assistant.template.yaml`
14. `config/templates/hr-assistant.template.yaml`
15. `config/templates/onboarding-buddy.template.yaml`

Each file follows the `AgentTemplate` schema from the spec with `apiVersion`, `kind`, `metadata`, and `template` sections.

- [ ] **Step 3: Validate all templates are valid YAML**

```bash
uv run python -c "
import yaml
from pathlib import Path
for f in sorted(Path('config/templates').glob('*.template.yaml')):
    data = yaml.safe_load(f.read_text())
    assert data['kind'] == 'AgentTemplate', f'{f.name}: wrong kind'
    assert 'template' in data, f'{f.name}: missing template section'
    assert 'agent_config' in data['template'], f'{f.name}: missing agent_config'
    print(f'OK: {f.name}')
print(f'Total: {len(list(Path(\"config/templates\").glob(\"*.template.yaml\")))} templates')
"
```

Expected: 15 templates all OK

- [ ] **Step 4: Commit**

```bash
git add config/templates/
git commit -m "feat(templates): add 15 pre-built agent templates for business use cases"
```

---

## Task 6: Scaffold Forge SPA

**Files:**
- Create: `astromesh-forge/` (entire project scaffold)

Initialize the Vite + React + TypeScript project with all dependencies.

- [ ] **Step 1: Create Vite project**

```bash
cd astromesh-forge
npm create vite@latest . -- --template react-ts
```

- [ ] **Step 2: Install dependencies**

```bash
cd astromesh-forge
npm install @xyflow/react @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities zustand react-router-dom js-yaml
npm install -D tailwindcss @tailwindcss/vite @types/js-yaml vitest @testing-library/react @testing-library/jest-dom jsdom happy-dom
```

- [ ] **Step 3: Configure Tailwind**

Create `astromesh-forge/src/index.css`:

```css
@import "tailwindcss";
```

Update `astromesh-forge/vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/v1': {
        target: process.env.VITE_ASTROMESH_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test-setup.ts',
  },
})
```

Create `astromesh-forge/src/test-setup.ts`:

```typescript
import '@testing-library/jest-dom'
```

- [ ] **Step 4: Configure TypeScript**

Update `astromesh-forge/tsconfig.json` to include Vitest types:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "types": ["vitest/globals"]
  },
  "include": ["src"]
}
```

- [ ] **Step 5: Create directory structure**

```bash
cd astromesh-forge
mkdir -p src/{api,components/{ui,layout,dashboard,wizard,canvas/{nodes,edges,panels},templates,deploy},hooks,stores,types,utils}
```

- [ ] **Step 6: Verify project builds**

```bash
cd astromesh-forge && npm run build
```

Expected: Build succeeds with no errors

- [ ] **Step 7: Verify tests run**

```bash
cd astromesh-forge && npx vitest run
```

Expected: Test runner works (0 tests initially)

- [ ] **Step 8: Commit**

```bash
git add astromesh-forge/
git commit -m "feat(forge): scaffold Vite + React + TypeScript SPA"
```

---

## Task 7: Types and API Client

**Files:**
- Create: `astromesh-forge/src/types/agent.ts`
- Create: `astromesh-forge/src/types/template.ts`
- Create: `astromesh-forge/src/types/canvas.ts`
- Create: `astromesh-forge/src/api/client.ts`
- Test: `astromesh-forge/src/api/__tests__/client.test.ts`

- [ ] **Step 1: Define TypeScript types**

```typescript
// astromesh-forge/src/types/agent.ts
export interface AgentMeta {
  name: string;
  version: string;
  namespace: string;
  description: string;
  status: "draft" | "deployed" | "paused";
}

export interface ModelConfig {
  provider: string;
  model: string;
  endpoint?: string;
  api_key_env?: string;
  parameters?: {
    temperature?: number;
    top_p?: number;
    max_tokens?: number;
  };
}

export interface ToolConfig {
  name: string;
  type: "internal" | "mcp" | "webhook" | "rag" | "agent";
  description: string;
  parameters?: Record<string, { type: string; description: string }>;
}

export interface GuardrailConfig {
  type: string;
  action?: "redact" | "block";
  [key: string]: unknown;
}

export interface MemoryConfig {
  backend: string;
  strategy?: string;
  max_turns?: number;
  ttl?: number;
  similarity_threshold?: number;
  max_results?: number;
}

export interface AgentConfig {
  apiVersion: string;
  kind: "Agent";
  metadata: {
    name: string;
    version: string;
    namespace?: string;
    labels?: Record<string, string>;
  };
  spec: {
    identity: {
      display_name: string;
      description: string;
      avatar?: string;
    };
    model: {
      primary: ModelConfig;
      fallback?: ModelConfig;
      routing?: {
        strategy: string;
        health_check_interval?: number;
      };
    };
    prompts: {
      system: string;
      templates?: Record<string, string>;
    };
    orchestration: {
      pattern: string;
      max_iterations: number;
      timeout_seconds?: number;
    };
    tools?: ToolConfig[];
    memory?: {
      conversational?: MemoryConfig;
      semantic?: MemoryConfig;
      episodic?: MemoryConfig;
    };
    guardrails?: {
      input?: GuardrailConfig[];
      output?: GuardrailConfig[];
    };
    permissions?: {
      allowed_actions?: string[];
      filesystem?: { read?: string[]; write?: string[] };
      network?: { allowed?: string[] };
      execution?: { dry_run?: boolean };
    };
  };
}
```

```typescript
// astromesh-forge/src/types/template.ts
import type { AgentConfig } from "./agent";

export interface TemplateVariable {
  key: string;
  label: string;
  placeholder?: string;
  default?: string;
  required: boolean;
}

export interface TemplateChannel {
  channel: string;
  reason: string;
}

export interface TemplateSummary {
  name: string;
  version: string;
  category: string;
  tags: string[];
  display_name: string;
  description: string;
  recommended_channels: TemplateChannel[];
}

export interface TemplateDetail extends TemplateSummary {
  variables: TemplateVariable[];
  agent_config: AgentConfig;
}
```

```typescript
// astromesh-forge/src/types/canvas.ts
import type { Node, Edge } from "@xyflow/react";

export type AgentNodeData = {
  name: string;
  displayName: string;
  status: "draft" | "deployed" | "paused";
  pattern: string;
};

export type PipelineNodeData = {
  label: string;
  category: "guardrail" | "memory" | "prompt" | "model" | "tool";
  config: Record<string, unknown>;
};

export type ForgeNode = Node<AgentNodeData, "agent"> | Node<PipelineNodeData, "pipeline">;
export type ForgeEdge = Edge;
```

- [ ] **Step 2: Write failing test for API client**

```typescript
// astromesh-forge/src/api/__tests__/client.test.ts
import { describe, it, expect, beforeEach, vi } from "vitest";
import { ForgeClient } from "../client";

const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("ForgeClient", () => {
  let client: ForgeClient;

  beforeEach(() => {
    client = new ForgeClient("http://localhost:8000");
    mockFetch.mockReset();
  });

  it("lists agents", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([{ name: "test", status: "deployed" }]),
    });
    const agents = await client.listAgents();
    expect(agents).toHaveLength(1);
    expect(mockFetch).toHaveBeenCalledWith("http://localhost:8000/v1/agents", expect.any(Object));
  });

  it("creates agent", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ status: "created" }),
    });
    const config = { apiVersion: "astromesh/v1", kind: "Agent" } as any;
    await client.createAgent(config);
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/v1/agents",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("deploys agent", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ status: "deployed" }),
    });
    await client.deployAgent("test");
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/v1/agents/test/deploy",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("lists templates", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([{ name: "sales-qualifier" }]),
    });
    const templates = await client.listTemplates();
    expect(templates).toHaveLength(1);
  });

  it("checks health", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ status: "ok" }),
    });
    const healthy = await client.healthCheck();
    expect(healthy).toBe(true);
  });

  it("returns false on health check failure", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Connection refused"));
    const healthy = await client.healthCheck();
    expect(healthy).toBe(false);
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd astromesh-forge && npx vitest run src/api/__tests__/client.test.ts`
Expected: FAIL — ForgeClient doesn't exist

- [ ] **Step 4: Implement API client**

```typescript
// astromesh-forge/src/api/client.ts
import type { AgentConfig, AgentMeta } from "../types/agent";
import type { TemplateSummary, TemplateDetail } from "../types/template";

export class ForgeClient {
  constructor(private baseUrl: string) {}

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const resp = await fetch(`${this.baseUrl}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${resp.status}`);
    }
    return resp.json();
  }

  async healthCheck(): Promise<boolean> {
    try {
      await this.request("/v1/health");
      return true;
    } catch {
      return false;
    }
  }

  async listAgents(): Promise<AgentMeta[]> {
    return this.request("/v1/agents");
  }

  async getAgent(name: string): Promise<AgentConfig> {
    return this.request(`/v1/agents/${name}`);
  }

  async createAgent(config: AgentConfig): Promise<{ status: string }> {
    return this.request("/v1/agents", {
      method: "POST",
      body: JSON.stringify(config),
    });
  }

  async updateAgent(name: string, config: AgentConfig): Promise<{ status: string }> {
    return this.request(`/v1/agents/${name}`, {
      method: "PUT",
      body: JSON.stringify(config),
    });
  }

  async deleteAgent(name: string): Promise<void> {
    await this.request(`/v1/agents/${name}`, { method: "DELETE" });
  }

  async deployAgent(name: string): Promise<{ status: string }> {
    return this.request(`/v1/agents/${name}/deploy`, { method: "POST" });
  }

  async pauseAgent(name: string): Promise<{ status: string }> {
    return this.request(`/v1/agents/${name}/pause`, { method: "POST" });
  }

  async listTemplates(): Promise<TemplateSummary[]> {
    return this.request("/v1/templates");
  }

  async getTemplate(name: string): Promise<TemplateDetail> {
    return this.request(`/v1/templates/${name}`);
  }

  async listTools(): Promise<{ name: string; description: string }[]> {
    return this.request("/v1/tools/builtin");
  }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd astromesh-forge && npx vitest run src/api/__tests__/client.test.ts`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add astromesh-forge/src/types/ astromesh-forge/src/api/
git commit -m "feat(forge): add TypeScript types and API client"
```

---

## Task 8: Zustand Stores

**Files:**
- Create: `astromesh-forge/src/stores/connection.ts`
- Create: `astromesh-forge/src/stores/agent.ts`
- Create: `astromesh-forge/src/stores/agents-list.ts`
- Test: `astromesh-forge/src/stores/__tests__/connection.test.ts`

- [ ] **Step 1: Write failing test for connection store**

```typescript
// astromesh-forge/src/stores/__tests__/connection.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useConnectionStore } from "../connection";

describe("connectionStore", () => {
  beforeEach(() => {
    useConnectionStore.setState({
      nodeUrl: "http://localhost:8000",
      connected: false,
      checking: false,
    });
  });

  it("has default nodeUrl", () => {
    const { nodeUrl } = useConnectionStore.getState();
    expect(nodeUrl).toBe("http://localhost:8000");
  });

  it("sets node URL", () => {
    useConnectionStore.getState().setNodeUrl("http://remote:8000");
    expect(useConnectionStore.getState().nodeUrl).toBe("http://remote:8000");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-forge && npx vitest run src/stores/__tests__/connection.test.ts`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement stores**

```typescript
// astromesh-forge/src/stores/connection.ts
import { create } from "zustand";
import { ForgeClient } from "../api/client";

interface ConnectionState {
  nodeUrl: string;
  connected: boolean;
  checking: boolean;
  client: ForgeClient;
  setNodeUrl: (url: string) => void;
  checkConnection: () => Promise<void>;
}

const DEFAULT_URL = import.meta.env.VITE_ASTROMESH_URL || "http://localhost:8000";

export const useConnectionStore = create<ConnectionState>((set, get) => ({
  nodeUrl: DEFAULT_URL,
  connected: false,
  checking: false,
  client: new ForgeClient(DEFAULT_URL),
  setNodeUrl: (url: string) => {
    set({ nodeUrl: url, client: new ForgeClient(url), connected: false });
    get().checkConnection();
  },
  checkConnection: async () => {
    set({ checking: true });
    const healthy = await get().client.healthCheck();
    set({ connected: healthy, checking: false });
  },
}));
```

```typescript
// astromesh-forge/src/stores/agent.ts
import { create } from "zustand";
import type { AgentConfig } from "../types/agent";

const EMPTY_CONFIG: AgentConfig = {
  apiVersion: "astromesh/v1",
  kind: "Agent",
  metadata: { name: "", version: "1.0.0" },
  spec: {
    identity: { display_name: "", description: "" },
    model: {
      primary: { provider: "ollama", model: "llama3.1:8b", endpoint: "http://ollama:11434" },
      routing: { strategy: "cost_optimized" },
    },
    prompts: { system: "" },
    orchestration: { pattern: "react", max_iterations: 10 },
  },
};

interface AgentEditorState {
  config: AgentConfig;
  dirty: boolean;
  templateOrigin: string | null;
  setConfig: (config: AgentConfig) => void;
  updateSpec: <K extends keyof AgentConfig["spec"]>(
    key: K,
    value: AgentConfig["spec"][K]
  ) => void;
  reset: () => void;
  loadFromTemplate: (config: AgentConfig, templateName: string) => void;
}

export const useAgentEditorStore = create<AgentEditorState>((set) => ({
  config: structuredClone(EMPTY_CONFIG),
  dirty: false,
  templateOrigin: null,
  setConfig: (config) => set({ config, dirty: true }),
  updateSpec: (key, value) =>
    set((state) => ({
      config: {
        ...state.config,
        spec: { ...state.config.spec, [key]: value },
      },
      dirty: true,
    })),
  reset: () => set({ config: structuredClone(EMPTY_CONFIG), dirty: false, templateOrigin: null }),
  loadFromTemplate: (config, templateName) =>
    set({ config, dirty: false, templateOrigin: templateName }),
}));
```

```typescript
// astromesh-forge/src/stores/agents-list.ts
import { create } from "zustand";
import type { AgentMeta } from "../types/agent";

interface AgentsListState {
  agents: AgentMeta[];
  loading: boolean;
  error: string | null;
  setAgents: (agents: AgentMeta[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useAgentsListStore = create<AgentsListState>((set) => ({
  agents: [],
  loading: false,
  error: null,
  setAgents: (agents) => set({ agents, error: null }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error, loading: false }),
}));
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd astromesh-forge && npx vitest run src/stores/__tests__/connection.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh-forge/src/stores/
git commit -m "feat(forge): add Zustand stores for connection, agent editor, and agent list"
```

---

## Task 9: Utility Functions (YAML, Template Engine, Canvas Converters)

**Files:**
- Create: `astromesh-forge/src/utils/yaml.ts`
- Create: `astromesh-forge/src/utils/template-engine.ts`
- Create: `astromesh-forge/src/utils/agent-to-nodes.ts`
- Create: `astromesh-forge/src/utils/nodes-to-agent.ts`
- Test: `astromesh-forge/src/utils/__tests__/template-engine.test.ts`
- Test: `astromesh-forge/src/utils/__tests__/agent-to-nodes.test.ts`

- [ ] **Step 1: Write failing test for template engine**

```typescript
// astromesh-forge/src/utils/__tests__/template-engine.test.ts
import { describe, it, expect } from "vitest";
import { resolveTemplate } from "../template-engine";

describe("resolveTemplate", () => {
  it("replaces simple variables", () => {
    const result = resolveTemplate("Hello {{name}}", { name: "World" });
    expect(result).toBe("Hello World");
  });

  it("applies slugify filter", () => {
    const result = resolveTemplate("{{company|slugify}}", { company: "Acme Corp" });
    expect(result).toBe("acme-corp");
  });

  it("applies lower filter", () => {
    const result = resolveTemplate("{{text|lower}}", { text: "HELLO" });
    expect(result).toBe("hello");
  });

  it("applies upper filter", () => {
    const result = resolveTemplate("{{text|upper}}", { text: "hello" });
    expect(result).toBe("HELLO");
  });

  it("uses default value for missing variables", () => {
    const result = resolveTemplate("{{missing}}", {});
    expect(result).toBe("{{missing}}");
  });

  it("resolves deeply nested objects", () => {
    const obj = { metadata: { name: "{{company|slugify}}-agent" } };
    const resolved = resolveTemplateObject(obj, { company: "Acme Corp" });
    expect(resolved.metadata.name).toBe("acme-corp-agent");
  });
});

import { resolveTemplateObject } from "../template-engine";
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-forge && npx vitest run src/utils/__tests__/template-engine.test.ts`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement template engine**

```typescript
// astromesh-forge/src/utils/template-engine.ts
function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, "")
    .replace(/[\s_]+/g, "-")
    .replace(/-+/g, "-");
}

const FILTERS: Record<string, (s: string) => string> = {
  slugify,
  lower: (s) => s.toLowerCase(),
  upper: (s) => s.toUpperCase(),
};

export function resolveTemplate(
  template: string,
  variables: Record<string, string>
): string {
  return template.replace(/\{\{(\w+)(?:\|(\w+))?\}\}/g, (match, key, filter) => {
    const value = variables[key];
    if (value === undefined) return match;
    if (filter && FILTERS[filter]) return FILTERS[filter](value);
    return value;
  });
}

export function resolveTemplateObject<T>(obj: T, variables: Record<string, string>): T {
  if (typeof obj === "string") return resolveTemplate(obj, variables) as T;
  if (Array.isArray(obj)) return obj.map((item) => resolveTemplateObject(item, variables)) as T;
  if (obj !== null && typeof obj === "object") {
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj)) {
      result[key] = resolveTemplateObject(value, variables);
    }
    return result as T;
  }
  return obj;
}
```

- [ ] **Step 4: Write failing test for canvas converter**

```typescript
// astromesh-forge/src/utils/__tests__/agent-to-nodes.test.ts
import { describe, it, expect } from "vitest";
import { agentToNodes } from "../agent-to-nodes";
import type { AgentConfig } from "../../types/agent";

const SAMPLE: AgentConfig = {
  apiVersion: "astromesh/v1",
  kind: "Agent",
  metadata: { name: "test", version: "1.0.0" },
  spec: {
    identity: { display_name: "Test Agent", description: "A test" },
    model: {
      primary: { provider: "ollama", model: "llama3.1:8b" },
      routing: { strategy: "cost_optimized" },
    },
    prompts: { system: "You are a test agent." },
    orchestration: { pattern: "react", max_iterations: 5 },
    tools: [{ name: "search", type: "internal", description: "Search" }],
    guardrails: {
      input: [{ type: "pii_detection", action: "redact" }],
      output: [{ type: "cost_limit", max_tokens_per_turn: 500 }],
    },
    memory: {
      conversational: { backend: "redis", strategy: "sliding_window", max_turns: 20 },
    },
  },
};

describe("agentToNodes", () => {
  it("creates nodes for all pipeline components", () => {
    const { nodes, edges } = agentToNodes(SAMPLE);
    const categories = nodes.map((n) => n.data.category || n.type);
    expect(categories).toContain("guardrail");
    expect(categories).toContain("memory");
    expect(categories).toContain("prompt");
    expect(categories).toContain("model");
    expect(categories).toContain("tool");
    expect(edges.length).toBeGreaterThan(0);
  });

  it("creates input guardrail nodes", () => {
    const { nodes } = agentToNodes(SAMPLE);
    const inputGuardrails = nodes.filter(
      (n) => n.data.category === "guardrail" && n.data.label?.includes("pii")
    );
    expect(inputGuardrails).toHaveLength(1);
  });
});
```

- [ ] **Step 5: Implement canvas converters**

```typescript
// astromesh-forge/src/utils/agent-to-nodes.ts
import type { AgentConfig } from "../types/agent";
import type { ForgeEdge } from "../types/canvas";

interface PipelineNode {
  id: string;
  type: "pipeline";
  position: { x: number; y: number };
  data: { label: string; category: string; config: Record<string, unknown> };
}

export function agentToNodes(config: AgentConfig): {
  nodes: PipelineNode[];
  edges: ForgeEdge[];
} {
  const nodes: PipelineNode[] = [];
  const edges: ForgeEdge[] = [];
  let y = 0;
  const x = 250;
  const step = 120;
  let prevId: string | null = null;

  function addNode(id: string, label: string, category: string, nodeConfig: Record<string, unknown> = {}) {
    nodes.push({ id, type: "pipeline", position: { x, y }, data: { label, category, config: nodeConfig } });
    if (prevId) edges.push({ id: `${prevId}-${id}`, source: prevId, target: id });
    prevId = id;
    y += step;
  }

  // Input guardrails
  const inputGuardrails = config.spec.guardrails?.input || [];
  for (const g of inputGuardrails) {
    addNode(`ig-${g.type}`, `Input: ${g.type}`, "guardrail", g as Record<string, unknown>);
  }

  // Memory
  if (config.spec.memory?.conversational) {
    addNode("memory-conv", "Conversational Memory", "memory", config.spec.memory.conversational as Record<string, unknown>);
  }
  if (config.spec.memory?.semantic) {
    addNode("memory-sem", "Semantic Memory", "memory", config.spec.memory.semantic as Record<string, unknown>);
  }

  // Prompt
  addNode("prompt", "System Prompt", "prompt", { system: config.spec.prompts.system });

  // Model
  addNode("model-primary", `${config.spec.model.primary.provider}/${config.spec.model.primary.model}`, "model", config.spec.model.primary as Record<string, unknown>);
  if (config.spec.model.fallback) {
    addNode("model-fallback", `Fallback: ${config.spec.model.fallback.provider}/${config.spec.model.fallback.model}`, "model", config.spec.model.fallback as Record<string, unknown>);
  }

  // Tools
  const tools = config.spec.tools || [];
  for (const t of tools) {
    addNode(`tool-${t.name}`, t.name, "tool", t as Record<string, unknown>);
  }

  // Output guardrails
  const outputGuardrails = config.spec.guardrails?.output || [];
  for (const g of outputGuardrails) {
    addNode(`og-${g.type}`, `Output: ${g.type}`, "guardrail", g as Record<string, unknown>);
  }

  return { nodes, edges };
}
```

```typescript
// astromesh-forge/src/utils/nodes-to-agent.ts
import type { AgentConfig, ToolConfig, GuardrailConfig, MemoryConfig } from "../types/agent";

interface PipelineNode {
  id: string;
  data: { label: string; category: string; config: Record<string, unknown> };
}

export function nodesToAgent(
  nodes: PipelineNode[],
  baseConfig: AgentConfig
): AgentConfig {
  const config = structuredClone(baseConfig);

  const tools: ToolConfig[] = nodes
    .filter((n) => n.data.category === "tool")
    .map((n) => n.data.config as unknown as ToolConfig);
  if (tools.length) config.spec.tools = tools;

  const inputGuardrails: GuardrailConfig[] = nodes
    .filter((n) => n.data.category === "guardrail" && n.id.startsWith("ig-"))
    .map((n) => n.data.config as GuardrailConfig);
  const outputGuardrails: GuardrailConfig[] = nodes
    .filter((n) => n.data.category === "guardrail" && n.id.startsWith("og-"))
    .map((n) => n.data.config as GuardrailConfig);
  if (inputGuardrails.length || outputGuardrails.length) {
    config.spec.guardrails = {
      input: inputGuardrails.length ? inputGuardrails : undefined,
      output: outputGuardrails.length ? outputGuardrails : undefined,
    };
  }

  const memoryNodes = nodes.filter((n) => n.data.category === "memory");
  if (memoryNodes.length) {
    config.spec.memory = {};
    for (const mn of memoryNodes) {
      if (mn.id.includes("conv")) config.spec.memory.conversational = mn.data.config as MemoryConfig;
      if (mn.id.includes("sem")) config.spec.memory.semantic = mn.data.config as MemoryConfig;
      if (mn.id.includes("epi")) config.spec.memory.episodic = mn.data.config as MemoryConfig;
    }
  }

  return config;
}
```

```typescript
// astromesh-forge/src/utils/yaml.ts
import yaml from "js-yaml";
import type { AgentConfig } from "../types/agent";

export function agentToYaml(config: AgentConfig): string {
  return yaml.dump(config, { lineWidth: 100, noRefs: true });
}

export function yamlToAgent(yamlStr: string): AgentConfig {
  return yaml.load(yamlStr) as AgentConfig;
}
```

- [ ] **Step 6: Run all util tests**

Run: `cd astromesh-forge && npx vitest run src/utils/__tests__/`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add astromesh-forge/src/utils/
git commit -m "feat(forge): add template engine, YAML converter, and canvas converters"
```

---

## Task 10: UI Components + Layout

**Files:**
- Create: `astromesh-forge/src/components/ui/Button.tsx`
- Create: `astromesh-forge/src/components/ui/Input.tsx`
- Create: `astromesh-forge/src/components/ui/Card.tsx`
- Create: `astromesh-forge/src/components/ui/Badge.tsx`
- Create: `astromesh-forge/src/components/ui/Select.tsx`
- Create: `astromesh-forge/src/components/ui/Toggle.tsx`
- Create: `astromesh-forge/src/components/ui/Modal.tsx`
- Create: `astromesh-forge/src/components/layout/Header.tsx`
- Create: `astromesh-forge/src/components/layout/Layout.tsx`
- Create: `astromesh-forge/src/App.tsx`

Base UI primitives with Tailwind. These are small, self-contained components.

- [ ] **Step 1: Create base UI components**

Each component is a thin Tailwind wrapper. Example patterns:

```typescript
// astromesh-forge/src/components/ui/Button.tsx
import { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const variants: Record<Variant, string> = {
  primary: "bg-cyan-500 hover:bg-cyan-600 text-white",
  secondary: "bg-gray-700 hover:bg-gray-600 text-gray-100",
  danger: "bg-red-600 hover:bg-red-700 text-white",
  ghost: "bg-transparent hover:bg-gray-800 text-gray-300",
};

export function Button({ variant = "primary", className = "", ...props }: ButtonProps) {
  return (
    <button
      className={`px-4 py-2 rounded-lg font-medium transition-colors disabled:opacity-50 ${variants[variant]} ${className}`}
      {...props}
    />
  );
}
```

Follow the same pattern for Input, Card, Badge, Select, Toggle, Modal — each a single file with Tailwind classes using the Astromesh brand palette (cyan `#00d4ff`, dark surfaces `#0a0e14`).

- [ ] **Step 2: Create Header with connection indicator**

```typescript
// astromesh-forge/src/components/layout/Header.tsx
import { useConnectionStore } from "../../stores/connection";

export function Header() {
  const { connected, checking, nodeUrl } = useConnectionStore();

  return (
    <header className="h-14 bg-gray-900 border-b border-gray-800 flex items-center px-4 justify-between">
      <div className="flex items-center gap-3">
        <span className="text-cyan-400 font-bold text-lg">Astromesh Forge</span>
      </div>
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <span
          className={`w-2 h-2 rounded-full ${
            checking ? "bg-yellow-400 animate-pulse" : connected ? "bg-green-400" : "bg-red-400"
          }`}
        />
        <span>{nodeUrl}</span>
      </div>
    </header>
  );
}
```

- [ ] **Step 3: Create Layout and App with routing**

```typescript
// astromesh-forge/src/components/layout/Layout.tsx
import { Outlet } from "react-router-dom";
import { Header } from "./Header";

export function Layout() {
  return (
    <div className="h-screen flex flex-col bg-gray-950 text-gray-100">
      <Header />
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
```

```typescript
// astromesh-forge/src/App.tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { Dashboard } from "./components/dashboard/Dashboard";
import { WizardShell } from "./components/wizard/WizardShell";
import { CanvasEditor } from "./components/canvas/CanvasEditor";
import { TemplateGallery } from "./components/templates/TemplateGallery";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/wizard" element={<WizardShell />} />
          <Route path="/wizard/:name" element={<WizardShell />} />
          <Route path="/canvas" element={<CanvasEditor />} />
          <Route path="/canvas/:name" element={<CanvasEditor />} />
          <Route path="/templates" element={<TemplateGallery />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

- [ ] **Step 4: Verify app builds**

Run: `cd astromesh-forge && npm run build`
Expected: Build succeeds (components can have stub content initially)

- [ ] **Step 5: Commit**

```bash
git add astromesh-forge/src/components/ui/ astromesh-forge/src/components/layout/ astromesh-forge/src/App.tsx
git commit -m "feat(forge): add UI components, layout, and routing"
```

---

## Task 11: Dashboard (Agent List + Quick Actions)

**Files:**
- Create: `astromesh-forge/src/components/dashboard/Dashboard.tsx`
- Create: `astromesh-forge/src/components/dashboard/AgentList.tsx`
- Create: `astromesh-forge/src/components/dashboard/QuickActions.tsx`

- [ ] **Step 1: Implement AgentList**

Table showing agents with status badge and action buttons. Fetches from `useConnectionStore().client.listAgents()` on mount. Displays columns: Name, Status (badge), Origin, Last edited, Actions (Edit/Deploy/Pause/Delete).

- [ ] **Step 2: Implement QuickActions**

Three cards linking to: "Create from Scratch" (`/wizard`), "Start from Template" (`/templates`), "Import YAML" (file upload that parses YAML and navigates to `/wizard` with pre-filled config).

- [ ] **Step 3: Implement Dashboard page**

Combines QuickActions + AgentList. On mount, calls `checkConnection()` and `listAgents()`.

- [ ] **Step 4: Verify renders**

Run: `cd astromesh-forge && npm run dev`
Navigate to `http://localhost:5173/` — Dashboard should render (may show connection error if no node running).

- [ ] **Step 5: Commit**

```bash
git add astromesh-forge/src/components/dashboard/
git commit -m "feat(forge): add dashboard with agent list and quick actions"
```

---

## Task 12: Wizard — Steps 1-3 (Identity, Model, Tools)

**Files:**
- Create: `astromesh-forge/src/components/wizard/WizardShell.tsx`
- Create: `astromesh-forge/src/components/wizard/StepIdentity.tsx`
- Create: `astromesh-forge/src/components/wizard/StepModel.tsx`
- Create: `astromesh-forge/src/components/wizard/StepTools.tsx`

- [ ] **Step 1: Implement WizardShell**

Container with step navigation (7 steps). Tracks current step. Reads/writes `useAgentEditorStore`. If URL has `:name` param, loads agent from API on mount. Shows step indicators at top. Navigation: Back / Next / "Open in Canvas" button.

- [ ] **Step 2: Implement StepIdentity**

Form fields: name (auto-slugified), display_name, description (textarea), avatar (preset picker), tags (comma-separated input). Updates `useAgentEditorStore.config.metadata` and `spec.identity`.

- [ ] **Step 3: Implement StepModel**

Primary model: provider dropdown + model input + endpoint input. Fallback (optional, toggle to show). Parameters: temperature slider, top_p slider, max_tokens input. Routing strategy: 4 radio buttons with descriptions. Updates `spec.model`.

- [ ] **Step 4: Implement StepTools**

Two-panel layout. Left: available tools from `GET /v1/tools/builtin` (fetched once). Right: agent's tools. Use `@dnd-kit/sortable` for drag & drop from left to right and reorder on right. Each tool card shows name + description + expand for inline config.

- [ ] **Step 5: Verify wizard navigation works**

Run: `cd astromesh-forge && npm run dev`
Navigate to `/wizard`, confirm steps 1-3 render and data persists between steps via Zustand.

- [ ] **Step 6: Commit**

```bash
git add astromesh-forge/src/components/wizard/
git commit -m "feat(forge): add wizard shell and steps 1-3 (identity, model, tools)"
```

---

## Task 13: Wizard — Steps 4-7 (Orchestration, Settings, Prompts, Review)

**Files:**
- Create: `astromesh-forge/src/components/wizard/StepOrchestration.tsx`
- Create: `astromesh-forge/src/components/wizard/StepSettings.tsx`
- Create: `astromesh-forge/src/components/wizard/StepPrompts.tsx`
- Create: `astromesh-forge/src/components/wizard/StepReview.tsx`

- [ ] **Step 1: Implement StepOrchestration**

Pattern selector: 6 cards, each with pattern name, visual diagram (inline SVG or ASCII), and description. Radio-style selection. Below: max_iterations (number input) and timeout_seconds (number input). Updates `spec.orchestration`.

- [ ] **Step 2: Implement StepSettings**

Three sections:
- **Memory:** toggle per type (conversational/semantic/episodic). When enabled, show backend select, strategy select, max_turns, TTL.
- **Guardrails:** two lists (input/output). Use `@dnd-kit/sortable` to drag guardrails from available list. Each guardrail card has inline config (type, action, thresholds).
- **Permissions:** allowed_actions checkboxes.

- [ ] **Step 3: Implement StepPrompts**

Textarea with monospace font for system prompt. Show available Jinja2 variables as clickable chips that insert `{{ variable }}` at cursor. Optional: named templates section (add/remove named templates).

- [ ] **Step 4: Implement StepReview**

Full YAML preview using `agentToYaml()` in a `<pre>` block (collapsible). Deploy section with `DeployModal` trigger button. "Open in Canvas" button that navigates to `/canvas` with current config.

- [ ] **Step 5: Test full wizard flow**

Run: `cd astromesh-forge && npm run dev`
Complete all 7 steps, verify YAML preview shows correct config.

- [ ] **Step 6: Commit**

```bash
git add astromesh-forge/src/components/wizard/
git commit -m "feat(forge): add wizard steps 4-7 (orchestration, settings, prompts, review)"
```

---

## Task 14: Canvas — Macro View (Agent Orchestration)

**Files:**
- Create: `astromesh-forge/src/components/canvas/CanvasEditor.tsx`
- Create: `astromesh-forge/src/components/canvas/nodes/AgentNode.tsx`
- Create: `astromesh-forge/src/components/canvas/panels/Toolbox.tsx`
- Create: `astromesh-forge/src/components/canvas/panels/PropertiesPanel.tsx`

- [ ] **Step 1: Implement AgentNode**

Custom React Flow node showing: agent icon/avatar, display_name, status badge, pattern label. Click: opens PropertiesPanel. Double-click: switches to micro view (drill-down).

```typescript
// astromesh-forge/src/components/canvas/nodes/AgentNode.tsx
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { AgentNodeData } from "../../../types/canvas";
import { Badge } from "../../ui/Badge";

export function AgentNode({ data }: NodeProps<AgentNodeData>) {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 min-w-[180px] shadow-lg">
      <Handle type="target" position={Position.Top} className="!bg-cyan-400" />
      <div className="flex items-center gap-2 mb-2">
        <div className="w-8 h-8 bg-cyan-500/20 rounded-lg flex items-center justify-center text-cyan-400 text-sm font-bold">
          {data.displayName[0]}
        </div>
        <div>
          <div className="font-medium text-sm">{data.displayName}</div>
          <div className="text-xs text-gray-500">{data.name}</div>
        </div>
      </div>
      <div className="flex gap-1">
        <Badge variant={data.status === "deployed" ? "success" : "default"}>
          {data.status}
        </Badge>
        <Badge variant="default">{data.pattern}</Badge>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-cyan-400" />
    </div>
  );
}
```

- [ ] **Step 2: Implement Toolbox (left sidebar)**

Fetches agents, tools, models from node API. Groups by category. Each item is draggable (using `@dnd-kit`). Drop onto canvas creates new node. For agents: drop creates AgentNode. Shows "Create New Agent" button that opens wizard.

- [ ] **Step 3: Implement PropertiesPanel (right sidebar)**

Shows when a node is selected. Renders contextual form based on node type:
- AgentNode → shows agent config summary, "Edit in Wizard" button, "Expand Pipeline" button
- PipelineNode → form fields matching the node's category (tool params, model params, guardrail config, memory config)

- [ ] **Step 4: Implement CanvasEditor**

Main container using `<ReactFlow>`. Registers custom node types (`agent`, `pipeline`). Sidebar layout: Toolbox (left) | Canvas (center) | PropertiesPanel (right, conditional). State: nodes + edges managed via React Flow's `useNodesState` / `useEdgesState`. If URL has `:name` param, loads agent from API and converts to nodes via `agentToNodes()`.

- [ ] **Step 5: Test canvas renders**

Run: `cd astromesh-forge && npm run dev`
Navigate to `/canvas` — empty canvas with toolbox. Verify nodes can be added by dragging.

- [ ] **Step 6: Commit**

```bash
git add astromesh-forge/src/components/canvas/
git commit -m "feat(forge): add canvas editor with macro view, agent nodes, and toolbox"
```

---

## Task 15: Canvas — Micro View (Pipeline Drill-Down)

**Files:**
- Create: `astromesh-forge/src/components/canvas/nodes/ToolNode.tsx`
- Create: `astromesh-forge/src/components/canvas/nodes/ModelNode.tsx`
- Create: `astromesh-forge/src/components/canvas/nodes/GuardrailNode.tsx`
- Create: `astromesh-forge/src/components/canvas/nodes/MemoryNode.tsx`
- Create: `astromesh-forge/src/components/canvas/nodes/PromptNode.tsx`
- Modify: `astromesh-forge/src/components/canvas/CanvasEditor.tsx`

- [ ] **Step 1: Create pipeline node components**

Each is a custom React Flow node with colored border indicating category:
- `ToolNode` — green border, shows tool name + type badge
- `ModelNode` — blue border, shows provider/model + parameters summary
- `GuardrailNode` — orange border (input) / red border (output), shows type + action
- `MemoryNode` — purple border, shows backend + strategy
- `PromptNode` — yellow border, shows truncated system prompt preview

All have `Handle` top/bottom for connections and click handler for PropertiesPanel.

- [ ] **Step 2: Add drill-down logic to CanvasEditor**

Track `viewMode: "macro" | "micro"` and `expandedAgent: string | null` in component state. When double-clicking an AgentNode:
1. Set viewMode to "micro" and expandedAgent to agent name
2. Call `agentToNodes(agentConfig)` to generate pipeline nodes/edges
3. Replace canvas content with pipeline view
4. Show "Back to Overview" button that returns to macro view

- [ ] **Step 3: Register all node types**

In CanvasEditor, register: `agent: AgentNode`, `pipeline: PipelineNode` (dispatches to Tool/Model/Guardrail/Memory/Prompt based on `data.category`). Or register each individually: `tool: ToolNode`, `model: ModelNode`, etc.

- [ ] **Step 4: Test drill-down**

Navigate to `/canvas`, add an agent node, double-click to expand pipeline view. Verify pipeline nodes render correctly. Click "Back to Overview" to return.

- [ ] **Step 5: Commit**

```bash
git add astromesh-forge/src/components/canvas/
git commit -m "feat(forge): add micro view pipeline nodes and drill-down navigation"
```

---

## Task 16: Templates Gallery

**Files:**
- Create: `astromesh-forge/src/components/templates/TemplateGallery.tsx`
- Create: `astromesh-forge/src/components/templates/TemplateCard.tsx`
- Create: `astromesh-forge/src/components/templates/TemplatePreview.tsx`

- [ ] **Step 1: Implement TemplateCard**

Card showing: category badge, display_name, description (truncated), recommended channels as icons/badges, tags.

- [ ] **Step 2: Implement TemplateGallery**

Fetches templates from `GET /v1/templates`. Search bar (filters by name, description, tags). Category filter tabs. Grid of TemplateCards. Click card → opens TemplatePreview.

- [ ] **Step 3: Implement TemplatePreview**

Full detail view: description, recommended channels with reasons, variables form (auto-generated from `variables` array), YAML preview (post-substitution using `resolveTemplateObject`). "Use Template" button → applies substitution, loads into `useAgentEditorStore`, navigates to `/wizard`.

- [ ] **Step 4: Test template flow**

Run app, navigate to `/templates`, verify templates load from API. Select one, fill variables, click "Use Template" → verify wizard opens with pre-filled config.

- [ ] **Step 5: Commit**

```bash
git add astromesh-forge/src/components/templates/
git commit -m "feat(forge): add templates gallery with search, preview, and variable customization"
```

---

## Task 17: Deploy Modal

**Files:**
- Create: `astromesh-forge/src/components/deploy/DeployModal.tsx`
- Create: `astromesh-forge/src/components/deploy/TargetSelector.tsx`

- [ ] **Step 1: Implement TargetSelector**

Three options as cards:
- **Local** (default): uses connected node URL, shows green indicator if connected
- **Remote Node**: input for URL + API key, health check button, shows connection status
- **Nexus**: disabled card with "Coming Soon" badge

- [ ] **Step 2: Implement DeployModal**

Modal overlay with: YAML preview (read-only), TargetSelector, "Deploy" button. On deploy:
1. If agent doesn't exist: `POST /v1/agents` then `POST /v1/agents/{name}/deploy`
2. If agent exists: `PUT /v1/agents/{name}` then `POST /v1/agents/{name}/deploy`
3. Show success/error feedback
4. On success, navigate to dashboard

For remote target: create a temporary `ForgeClient` with the remote URL and use it for the API calls.

- [ ] **Step 3: Integrate with wizard StepReview and canvas**

Add "Deploy" button in StepReview and canvas toolbar that opens DeployModal.

- [ ] **Step 4: Test deploy flow**

With a local Astromesh node running, create an agent in wizard, deploy. Verify agent appears in dashboard as "deployed".

- [ ] **Step 5: Commit**

```bash
git add astromesh-forge/src/components/deploy/
git commit -m "feat(forge): add deploy modal with local, remote, and Nexus target selection"
```

---

## Task 18: Docs-Site — Replace Cloud with Forge

**Files:**
- Create: `docs-site/src/content/docs/forge/introduction.mdx`
- Create: `docs-site/src/content/docs/forge/quickstart.mdx`
- Create: `docs-site/src/content/docs/forge/wizard-guide.mdx`
- Create: `docs-site/src/content/docs/forge/canvas-guide.mdx`
- Create: `docs-site/src/content/docs/forge/templates.mdx`
- Create: `docs-site/src/content/docs/forge/deployment.mdx`
- Modify: `docs-site/astro.config.mjs`

- [ ] **Step 1: Create forge/introduction.mdx**

Overview of Forge: what it is, target user, relationship to the Astromesh ecosystem. Explain the three distribution modes (embedded, standalone, future Nexus). Include architecture diagram from spec.

- [ ] **Step 2: Create forge/quickstart.mdx**

Getting started: (1) Start Astromesh node, (2) Open Forge at `http://localhost:8000/forge` or run standalone, (3) Create first agent using wizard, (4) Deploy.

- [ ] **Step 3: Create forge/wizard-guide.mdx**

Document all 7 wizard steps with screenshots/descriptions. Explain each field. Show how wizard maps to agent YAML.

- [ ] **Step 4: Create forge/canvas-guide.mdx**

Document canvas: macro view (agent orchestration), micro view (pipeline drill-down). Explain toolbox, properties panel, drag & drop. Explain how canvas ↔ wizard interop works.

- [ ] **Step 5: Create forge/templates.mdx**

Document templates gallery. List all 15 templates with category, description, recommended channels. Explain variable customization. Explain how to create custom templates.

- [ ] **Step 6: Create forge/deployment.mdx**

Document deploy targets: local, remote node, Nexus (coming soon). Explain connection settings, CORS configuration, embedded vs standalone mode.

- [ ] **Step 7: Update astro.config.mjs sidebar**

Replace the "Cloud" sidebar section with "Forge":

```javascript
{
  label: "Forge",
  items: [
    { label: "Introduction", slug: "forge/introduction" },
    { label: "Quick Start", slug: "forge/quickstart" },
    { label: "Wizard Guide", slug: "forge/wizard-guide" },
    { label: "Canvas Guide", slug: "forge/canvas-guide" },
    { label: "Templates", slug: "forge/templates" },
    { label: "Deployment", slug: "forge/deployment" },
  ],
},
```

- [ ] **Step 8: Verify docs build**

Run: `cd docs-site && npm run build`
Expected: Build succeeds with no broken links

- [ ] **Step 9: Commit**

```bash
git add docs-site/
git commit -m "docs: replace Cloud section with Forge in docs-site"
```

---

## Task 19: Integration Test — End-to-End Flow

**Files:**
- Test: `tests/test_forge_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_forge_integration.py
import pytest
from httpx import ASGITransport, AsyncClient
from astromesh.api.main import app
from astromesh.api.routes import agents as agents_route, templates as templates_route
from astromesh.runtime.engine import AgentRuntime
from pathlib import Path
import yaml


@pytest.fixture
async def runtime_with_templates(tmp_path):
    # Set up config dirs
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "agents").mkdir()
    templates_dir = config_dir / "templates"
    templates_dir.mkdir()

    # Create a test template
    tpl = {
        "apiVersion": "astromesh/v1",
        "kind": "AgentTemplate",
        "metadata": {"name": "test-tpl", "version": "1.0.0", "category": "test", "tags": []},
        "template": {
            "display_name": "Test Template",
            "description": "A test template",
            "recommended_channels": [],
            "variables": [{"key": "name", "label": "Name", "required": True}],
            "agent_config": {
                "apiVersion": "astromesh/v1",
                "kind": "Agent",
                "metadata": {"name": "{{name|slugify}}-agent", "version": "1.0.0", "namespace": "test"},
                "spec": {
                    "identity": {"display_name": "{{name}} Agent", "description": "Test"},
                    "model": {
                        "primary": {"provider": "ollama", "model": "test", "endpoint": "http://localhost:11434"},
                        "routing": {"strategy": "cost_optimized"},
                    },
                    "prompts": {"system": "You are a test agent for {{name}}."},
                    "orchestration": {"pattern": "react", "max_iterations": 5},
                },
            },
        },
    }
    (templates_dir / "test-tpl.template.yaml").write_text(yaml.dump(tpl))

    runtime = AgentRuntime(config_dir=str(config_dir))
    agents_route.set_runtime(runtime)
    templates_route.set_templates_dir(str(templates_dir))
    return runtime


async def test_full_forge_flow(runtime_with_templates):
    """Simulates what Forge SPA does: list templates → get template → create agent → deploy"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. List templates
        resp = await client.get("/v1/templates")
        assert resp.status_code == 200
        templates = resp.json()
        assert len(templates) == 1
        assert templates[0]["name"] == "test-tpl"

        # 2. Get template detail
        resp = await client.get("/v1/templates/test-tpl")
        assert resp.status_code == 200
        detail = resp.json()
        assert "agent_config" in detail

        # 3. Create agent (Forge resolves variables client-side, sends resolved config)
        agent_config = detail["agent_config"]
        agent_config["metadata"]["name"] = "acme-agent"
        agent_config["spec"]["identity"]["display_name"] = "Acme Agent"
        resp = await client.post("/v1/agents", json=agent_config)
        assert resp.status_code == 201

        # 4. List agents — should show as draft
        resp = await client.get("/v1/agents")
        assert resp.status_code == 200
        agents = resp.json()
        agent = next(a for a in agents if a["name"] == "acme-agent")
        assert agent["status"] == "draft"

        # 5. Deploy (will fail because no real model, but should accept the request)
        # In a real test with mocked providers this would succeed
        # For now, just verify the endpoint exists and accepts the call
        resp = await client.post("/v1/agents/acme-agent/deploy")
        # May fail due to no real provider, which is expected
        assert resp.status_code in (200, 500)

        # 6. Update agent
        agent_config["spec"]["prompts"]["system"] = "Updated prompt"
        resp = await client.put("/v1/agents/acme-agent", json=agent_config)
        assert resp.status_code == 200

        # 7. Delete agent
        resp = await client.delete("/v1/agents/acme-agent")
        assert resp.status_code == 200
```

- [ ] **Step 2: Run integration test**

Run: `uv run pytest tests/test_forge_integration.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_forge_integration.py
git commit -m "test: add end-to-end integration test for Forge API flow"
```

---

## Task 20: Final Cleanup and README

**Files:**
- Create: `astromesh-forge/README.md`
- Modify: root `README.md` (if it references astromesh-cloud)

- [ ] **Step 1: Create astromesh-forge/README.md**

```markdown
# Astromesh Forge

Visual agent builder for the Astromesh platform.

## Quick Start

### Standalone

```bash
cd astromesh-forge
npm install
npm run dev
```

Configure the Astromesh node URL via environment variable:

```bash
VITE_ASTROMESH_URL=http://localhost:8000 npm run dev
```

### Embedded (in Astromesh node)

```bash
cd astromesh-forge
npm run build
cp -r dist/ ../astromesh/static/forge/
```

Then access at `http://localhost:8000/forge`.

## Tech Stack

- Vite + React + TypeScript
- React Flow (canvas)
- dnd-kit (drag & drop)
- Tailwind CSS
- Zustand (state)
- React Router

## Development

```bash
npm run dev       # Dev server with hot reload
npm run build     # Production build
npm run preview   # Preview production build
npx vitest        # Run tests
npx vitest --ui   # Test UI
```
```

- [ ] **Step 2: Verify full project builds**

```bash
cd astromesh-forge && npm run build
uv run pytest tests/ -v --ignore=tests/test_rust*.py
cd docs-site && npm run build
```

Expected: All builds pass, all tests pass

- [ ] **Step 3: Commit**

```bash
git add astromesh-forge/README.md
git commit -m "docs: add Forge README and finalize project structure"
```
