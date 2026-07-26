"""tiktok: lecturas por POST y paginación con el cursor dentro del cuerpo."""

import json

import httpx
import respx

from astromesh.integrations import IntegrationCatalog
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor

TIKTOK = "https://open.tiktokapis.com/v2"
CONN = ResolvedConnection(name="tt", material={"access_token": "T0K3N"})


def _tiktok():
    catalog = IntegrationCatalog()
    catalog.discover()
    return catalog.get("tiktok")


def test_read_only_posts_declare_writes_false_explicitly():
    """No basta con omitirlo: el silencio no distingue 'lee' de 'me olvidé'."""
    actions = {a.name: a for a in _tiktok().actions}
    assert actions["list_videos"].writes is False
    assert actions["get_publish_status"].writes is False
    assert actions["list_videos"].mutates is False
    assert actions["publish_video"].writes is True


@respx.mock
async def test_get_user_info_selects_the_nested_user():
    respx.get(f"{TIKTOK}/user/info/").mock(
        return_value=httpx.Response(200, json={"data": {"user": {"display_name": "Ana"}}})
    )
    m = _tiktok()
    result = await HttpActionExecutor().execute(m, m.action("get_user_info"), {}, CONN)
    assert result.success is True
    assert result.data == {"display_name": "Ana"}


@respx.mock
async def test_list_videos_sends_the_cursor_in_the_body_not_the_query():
    """TikTok pagina por cuerpo; mandarlo en la query devolvería siempre la página 1."""
    route = respx.post(f"{TIKTOK}/video/list/").mock(
        return_value=httpx.Response(200, json={"data": {"videos": [{"id": "v1"}], "cursor": "C2"}})
    )
    m = _tiktok()
    result = await HttpActionExecutor().execute(
        m, m.action("list_videos"), {"cursor": "C1", "max_count": 3}, CONN
    )
    assert result.data == [{"id": "v1"}]
    assert result.metadata["next_cursor"] == "C2"

    request = route.calls[0].request
    body = json.loads(request.content)
    assert body["cursor"] == "C1"
    assert body["max_count"] == 3
    assert "cursor" not in request.url.params


@respx.mock
async def test_list_videos_omits_the_cursor_on_the_first_page():
    route = respx.post(f"{TIKTOK}/video/list/").mock(
        return_value=httpx.Response(200, json={"data": {"videos": []}})
    )
    m = _tiktok()
    await HttpActionExecutor().execute(m, m.action("list_videos"), {}, CONN)
    assert "cursor" not in json.loads(route.calls[0].request.content)


@respx.mock
async def test_publish_video_builds_the_nested_pull_from_url_payload():
    route = respx.post(f"{TIKTOK}/post/publish/video/init/").mock(
        return_value=httpx.Response(200, json={"data": {"publish_id": "PUB1"}})
    )
    m = _tiktok()
    result = await HttpActionExecutor().execute(
        m,
        m.action("publish_video"),
        {"video_url": "https://cdn.test/v.mp4", "title": "mi video"},
        CONN,
    )
    assert result.success is True
    assert result.data == {"publish_id": "PUB1"}
    assert json.loads(route.calls[0].request.content) == {
        "post_info": {"title": "mi video", "privacy_level": "SELF_ONLY"},
        "source_info": {"source": "PULL_FROM_URL", "video_url": "https://cdn.test/v.mp4"},
    }


@respx.mock
async def test_get_publish_status_posts_the_publish_id():
    route = respx.post(f"{TIKTOK}/post/publish/status/fetch/").mock(
        return_value=httpx.Response(200, json={"data": {"status": "PUBLISH_COMPLETE"}})
    )
    m = _tiktok()
    result = await HttpActionExecutor().execute(
        m, m.action("get_publish_status"), {"publish_id": "PUB1"}, CONN
    )
    assert result.data == {"status": "PUBLISH_COMPLETE"}
    assert json.loads(route.calls[0].request.content) == {"publish_id": "PUB1"}
