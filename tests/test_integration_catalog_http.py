import json

import httpx
import respx

from astromesh.integrations import IntegrationCatalog
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor


def _http():
    catalog = IntegrationCatalog()
    catalog.discover()
    return catalog.get("http")


def test_manifest_has_no_base_url_so_the_connection_must_bring_it():
    assert _http().base_url is None


def test_exposes_the_four_verbs():
    assert {a.name for a in _http().actions} == {"get", "post", "put", "delete"}


def test_write_verbs_are_marked_as_writes():
    actions = {a.name: a for a in _http().actions}
    assert actions["get"].mutates is False
    assert actions["post"].writes is True
    assert actions["put"].writes is True
    assert actions["delete"].writes is True


@respx.mock
async def test_get_against_a_connection_base_url():
    route = respx.get("https://crm.acme.internal/customers").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    manifest = _http()
    conn = ResolvedConnection(
        name="crm", material={"api_key": "K"}, base_url="https://crm.acme.internal"
    )
    result = await HttpActionExecutor().execute(
        manifest, manifest.action("get"), {"path": "/customers"}, conn
    )
    assert result.success is True
    assert result.data == {"ok": True}
    assert route.calls[0].request.headers["X-Api-Key"] == "K"


async def test_without_base_url_it_fails_cleanly():
    manifest = _http()
    result = await HttpActionExecutor().execute(
        manifest, manifest.action("get"), {"path": "/x"}, ResolvedConnection("c", {"api_key": "K"})
    )
    assert result.success is False
    assert "base_url" in result.error


@respx.mock
async def test_post_sends_the_body_through():
    route = respx.post("https://crm.acme.internal/customers").mock(
        return_value=httpx.Response(201, json={"id": 1})
    )
    manifest = _http()
    conn = ResolvedConnection("crm", {"api_key": "K"}, base_url="https://crm.acme.internal")
    result = await HttpActionExecutor().execute(
        manifest, manifest.action("post"), {"path": "/customers", "body": {"name": "Ana"}}, conn
    )
    assert result.success is True
    assert json.loads(route.calls[0].request.content) == {"name": "Ana"}


async def test_path_traversal_is_rejected():
    manifest = _http()
    conn = ResolvedConnection("crm", {"api_key": "K"}, base_url="https://crm.acme.internal")
    result = await HttpActionExecutor().execute(
        manifest, manifest.action("get"), {"path": "/../../admin"}, conn
    )
    assert result.success is False
