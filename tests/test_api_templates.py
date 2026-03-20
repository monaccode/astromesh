import pytest
from httpx import ASGITransport, AsyncClient
from astromesh.api.main import app
from astromesh.api.routes import templates as templates_route
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
            "recommended_channels": [{"channel": "whatsapp", "reason": "Direct messaging"}],
            "variables": [{"key": "company_name", "label": "Company", "required": True}],
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
    yield tpl_dir
    templates_route.set_templates_dir(None)


async def test_list_templates(templates_dir):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "sales-qualifier"
    assert data[0]["category"] == "sales"
    assert "agent_config" not in data[0]


async def test_get_template_detail(templates_dir):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/templates/sales-qualifier")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "sales-qualifier"
    assert "agent_config" in data
    assert data["variables"][0]["key"] == "company_name"


async def test_get_template_not_found(templates_dir):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/templates/nonexistent")
    assert resp.status_code == 404
