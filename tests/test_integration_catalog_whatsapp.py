import json

import httpx
import respx

from astromesh.integrations import IntegrationCatalog
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor

CONN = ResolvedConnection(name="wa", material={"access_token": "T0K3N"})


def _whatsapp():
    catalog = IntegrationCatalog()
    catalog.discover()
    return catalog.get("whatsapp")


def test_uses_the_graph_api_base_and_bearer_auth():
    manifest = _whatsapp()
    assert manifest.base_url == "https://graph.facebook.com/v21.0"
    assert manifest.auth.scheme == "bearer"
    assert manifest.auth.credential == "access_token"


def test_exposes_the_outbound_actions():
    assert {a.name for a in _whatsapp().actions} == {"send_text", "send_template", "get_media"}


def test_send_actions_are_marked_as_writes():
    actions = {a.name: a for a in _whatsapp().actions}
    assert actions["send_text"].writes is True
    assert actions["send_template"].writes is True
    assert actions["get_media"].writes is False


@respx.mock
async def test_send_text_builds_the_graph_payload():
    route = respx.post("https://graph.facebook.com/v21.0/PHONE1/messages").mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})
    )
    manifest = _whatsapp()
    result = await HttpActionExecutor().execute(
        manifest,
        manifest.action("send_text"),
        {"phone_number_id": "PHONE1", "to": "5491100000000", "text": "hola"},
        CONN,
    )
    assert result.success is True
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer T0K3N"
    assert json.loads(request.content) == {
        "messaging_product": "whatsapp",
        "to": "5491100000000",
        "type": "text",
        "text": {"body": "hola"},
    }


@respx.mock
async def test_get_media_resolves_the_media_url():
    respx.get("https://graph.facebook.com/v21.0/MEDIA1").mock(
        return_value=httpx.Response(200, json={"url": "https://lookaside.test/x", "id": "MEDIA1"})
    )
    manifest = _whatsapp()
    result = await HttpActionExecutor().execute(
        manifest, manifest.action("get_media"), {"media_id": "MEDIA1"}, CONN
    )
    assert result.success is True
    assert result.data["url"] == "https://lookaside.test/x"


@respx.mock
async def test_expired_token_maps_to_credential_invalid():
    from astromesh.integrations import errors

    respx.post("https://graph.facebook.com/v21.0/PHONE1/messages").mock(
        return_value=httpx.Response(401, json={"error": {"message": "expired"}})
    )
    manifest = _whatsapp()
    result = await HttpActionExecutor().execute(
        manifest,
        manifest.action("send_text"),
        {"phone_number_id": "PHONE1", "to": "549110", "text": "x"},
        CONN,
    )
    assert result.success is False
    assert result.metadata["error_kind"] == errors.CREDENTIAL_INVALID
