"""instagram y facebook: la familia Meta Graph, copiada de whatsapp."""

import json

import httpx
import respx

from astromesh.integrations import IntegrationCatalog, errors
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor

GRAPH = "https://graph.facebook.com/v21.0"
CONN = ResolvedConnection(name="meta", material={"access_token": "T0K3N"})


def _get(slug):
    catalog = IntegrationCatalog()
    catalog.discover()
    return catalog.get(slug)


def test_the_meta_family_shares_base_url_and_auth():
    """Es la razón por la que copiar whatsapp alcanza para las otras dos."""
    for slug in ("whatsapp", "instagram", "facebook"):
        manifest = _get(slug)
        assert manifest.base_url == GRAPH, slug
        assert manifest.auth.scheme == "bearer", slug
        assert manifest.auth.credential == "access_token", slug


@respx.mock
async def test_instagram_list_media_selects_and_paginates():
    route = respx.get(f"{GRAPH}/IG1/media").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"id": "m1"}], "paging": {"cursors": {"after": "CUR2"}}},
        )
    )
    m = _get("instagram")
    result = await HttpActionExecutor().execute(
        m, m.action("list_media"), {"ig_user_id": "IG1", "limit": 5}, CONN
    )
    assert result.success is True
    assert result.data == [{"id": "m1"}]
    assert result.metadata["next_cursor"] == "CUR2"
    assert route.calls[0].request.url.params["limit"] == "5"


@respx.mock
async def test_instagram_publish_photo_chains_container_then_publish():
    container = respx.post(f"{GRAPH}/IG1/media").mock(
        return_value=httpx.Response(200, json={"id": "CONTAINER9"})
    )
    publish = respx.post(f"{GRAPH}/IG1/media_publish").mock(
        return_value=httpx.Response(200, json={"id": "POST7"})
    )
    m = _get("instagram")
    result = await HttpActionExecutor().execute(
        m,
        m.action("publish_photo"),
        {"ig_user_id": "IG1", "image_url": "https://cdn.test/a.jpg", "caption": "hola"},
        CONN,
    )
    assert result.success is True
    assert result.data == {"id": "POST7"}
    assert result.metadata["creation_id"] == "CONTAINER9"
    assert container.calls[0].request.url.params["image_url"] == "https://cdn.test/a.jpg"
    assert container.calls[0].request.url.params["caption"] == "hola"
    assert publish.calls[0].request.url.params["creation_id"] == "CONTAINER9"


@respx.mock
async def test_instagram_publish_surfaces_creation_id_when_publish_fails():
    """El contenedor quedó creado: sin el id, se pierde y no se puede reintentar."""
    respx.post(f"{GRAPH}/IG1/media").mock(
        return_value=httpx.Response(200, json={"id": "CONTAINER9"})
    )
    respx.post(f"{GRAPH}/IG1/media_publish").mock(
        return_value=httpx.Response(400, json={"error": {"message": "media not ready"}})
    )
    m = _get("instagram")
    result = await HttpActionExecutor().execute(
        m,
        m.action("publish_photo"),
        {"ig_user_id": "IG1", "image_url": "https://cdn.test/a.jpg"},
        CONN,
    )
    assert result.success is False
    assert result.metadata["creation_id"] == "CONTAINER9"
    assert "publish_container" in result.error


@respx.mock
async def test_instagram_publish_stops_if_the_container_fails():
    respx.post(f"{GRAPH}/IG1/media").mock(return_value=httpx.Response(401))
    publish = respx.post(f"{GRAPH}/IG1/media_publish").mock(
        return_value=httpx.Response(200, json={})
    )
    m = _get("instagram")
    result = await HttpActionExecutor().execute(
        m, m.action("publish_photo"), {"ig_user_id": "IG1", "image_url": "https://x.test/a"}, CONN
    )
    assert result.success is False
    assert result.metadata["error_kind"] == errors.CREDENTIAL_INVALID
    assert not publish.called


@respx.mock
async def test_instagram_publish_without_caption_omits_it():
    container = respx.post(f"{GRAPH}/IG1/media").mock(
        return_value=httpx.Response(200, json={"id": "C1"})
    )
    respx.post(f"{GRAPH}/IG1/media_publish").mock(return_value=httpx.Response(200, json={}))
    m = _get("instagram")
    await HttpActionExecutor().execute(
        m, m.action("publish_photo"), {"ig_user_id": "IG1", "image_url": "https://x.test/a"}, CONN
    )
    assert "caption" not in container.calls[0].request.url.params


@respx.mock
async def test_facebook_create_post_sends_the_message():
    route = respx.post(f"{GRAPH}/PAGE1/feed").mock(
        return_value=httpx.Response(200, json={"id": "PAGE1_99"})
    )
    m = _get("facebook")
    result = await HttpActionExecutor().execute(
        m, m.action("create_post"), {"page_id": "PAGE1", "message": "buenas"}, CONN
    )
    assert result.success is True
    assert json.loads(route.calls[0].request.content) == {"message": "buenas"}


@respx.mock
async def test_facebook_optional_link_is_omitted_when_absent():
    """Un campo opcional sin argumento se omite; mandarlo vacío rompería el post."""
    route = respx.post(f"{GRAPH}/PAGE1/feed").mock(return_value=httpx.Response(200, json={}))
    m = _get("facebook")
    await HttpActionExecutor().execute(
        m, m.action("create_post"), {"page_id": "PAGE1", "message": "x"}, CONN
    )
    assert "link" not in json.loads(route.calls[0].request.content)


@respx.mock
async def test_facebook_link_travels_when_given():
    route = respx.post(f"{GRAPH}/PAGE1/feed").mock(return_value=httpx.Response(200, json={}))
    m = _get("facebook")
    await HttpActionExecutor().execute(
        m,
        m.action("create_post"),
        {"page_id": "PAGE1", "message": "x", "link": "https://a.test"},
        CONN,
    )
    assert json.loads(route.calls[0].request.content)["link"] == "https://a.test"


@respx.mock
async def test_facebook_list_page_posts_selects_data():
    respx.get(f"{GRAPH}/PAGE1/posts").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "p1"}]})
    )
    m = _get("facebook")
    result = await HttpActionExecutor().execute(
        m, m.action("list_page_posts"), {"page_id": "PAGE1"}, CONN
    )
    assert result.data == [{"id": "p1"}]
