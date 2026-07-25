import httpx
import respx

from astromesh.integrations import errors
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor
from astromesh.integrations.manifest import IntegrationManifest, load_manifest

MANIFEST = """
apiVersion: astromesh/v1
kind: Integration
metadata: {name: demo, version: 0.1.0, description: demo}
spec:
  base_url: "https://api.demo.test/v1"
  auth: {scheme: bearer, credential: access_token}
  defaults: {timeout_seconds: 5, headers: {X-Demo: "1"}}
  actions:
    - name: list_items
      description: "Lista"
      parameters:
        owner: {type: string, required: true}
        limit: {type: integer, default: 25}
      request:
        method: GET
        path: "/{owner}/items"
        query: {limit: "{limit}"}
      response: {select: "data"}
      pagination: {style: cursor, cursor_param: after, cursor_path: "paging.next"}
    - name: create_item
      description: "Crea"
      parameters:
        title: {type: string, required: true}
        count: {type: integer, default: 1}
      request:
        method: POST
        path: "/items"
        body: {title: "{title}", count: "{count}"}
    - name: custom
      description: "Handler"
      handler: "python:tests.test_integration_executor:_handler"
      parameters:
        x: {type: string, required: true}
"""

OFFSET_MANIFEST = MANIFEST.replace(
    '      pagination: {style: cursor, cursor_param: after, cursor_path: "paging.next"}',
    "      pagination: {style: offset, limit_param: per_page, offset_param: skip}",
)

CONN = ResolvedConnection(name="c", material={"access_token": "T0K3N"})


async def _handler(arguments, ctx):
    from astromesh.tools.base import ToolResult

    return ToolResult(success=True, data={"echo": arguments["x"], "base": ctx.base_url})


async def _boom(arguments, ctx):
    raise RuntimeError("boom")


def _manifest(tmp_path, text: str = MANIFEST) -> IntegrationManifest:
    path = tmp_path / "integration.yaml"
    path.write_text(text)
    return load_manifest(path)


@respx.mock
async def test_get_builds_url_query_headers_and_selects(tmp_path):
    route = respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, json={"data": [{"id": 1}], "paging": {"next": "C2"}})
    )
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(
        m, m.action("list_items"), {"owner": "acme", "limit": 10}, CONN
    )
    assert result.success is True
    assert result.data == [{"id": 1}]
    assert result.metadata["next_cursor"] == "C2"
    assert result.metadata["status_code"] == 200
    request = route.calls[0].request
    assert request.url.params["limit"] == "10"
    assert request.headers["Authorization"] == "Bearer T0K3N"
    assert request.headers["X-Demo"] == "1"


@respx.mock
async def test_default_is_applied_when_argument_absent(tmp_path):
    route = respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    m = _manifest(tmp_path)
    await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert route.calls[0].request.url.params["limit"] == "25"


@respx.mock
async def test_cursor_argument_is_sent_as_configured_param(tmp_path):
    route = respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    m = _manifest(tmp_path)
    await HttpActionExecutor().execute(
        m, m.action("list_items"), {"owner": "acme", "cursor": "C9"}, CONN
    )
    assert route.calls[0].request.url.params["after"] == "C9"


@respx.mock
async def test_offset_pagination_sends_limit_and_offset(tmp_path):
    m = _manifest(tmp_path, OFFSET_MANIFEST)
    route = respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    await HttpActionExecutor().execute(
        m, m.action("list_items"), {"owner": "acme", "limit": 10, "cursor": "40"}, CONN
    )
    params = route.calls[0].request.url.params
    assert params["skip"] == "40"
    assert params["per_page"] == "10"


@respx.mock
async def test_offset_pagination_reports_the_next_offset(tmp_path):
    m = _manifest(tmp_path, OFFSET_MANIFEST)
    respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, json={"data": [{"id": 1}, {"id": 2}]})
    )
    result = await HttpActionExecutor().execute(
        m, m.action("list_items"), {"owner": "acme", "cursor": "40"}, CONN
    )
    # 40 ya consumidos + 2 devueltos = el modelo pide desde 42.
    assert result.metadata["next_cursor"] == "42"


@respx.mock
async def test_offset_pagination_ends_when_page_is_empty(tmp_path):
    m = _manifest(tmp_path, OFFSET_MANIFEST)
    respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert result.metadata["next_cursor"] is None


@respx.mock
async def test_absent_next_cursor_is_none(tmp_path):
    respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert result.metadata["next_cursor"] is None


@respx.mock
async def test_post_body_preserves_argument_types(tmp_path):
    import json

    route = respx.post("https://api.demo.test/v1/items").mock(
        return_value=httpx.Response(201, json={"id": 9})
    )
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(
        m, m.action("create_item"), {"title": "hola", "count": 3}, CONN
    )
    assert result.success is True
    assert json.loads(route.calls[0].request.content) == {"title": "hola", "count": 3}


@respx.mock
async def test_connection_base_url_overrides_manifest(tmp_path):
    route = respx.get("https://sandbox.demo.test/acme/items").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    m = _manifest(tmp_path)
    conn = ResolvedConnection(
        name="c", material={"access_token": "T"}, base_url="https://sandbox.demo.test"
    )
    await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, conn)
    assert route.calls[0].request.url.host == "sandbox.demo.test"


@respx.mock
async def test_401_maps_to_credential_invalid(tmp_path):
    respx.get("https://api.demo.test/v1/acme/items").mock(return_value=httpx.Response(401))
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert result.success is False
    assert result.metadata["error_kind"] == errors.CREDENTIAL_INVALID


@respx.mock
async def test_429_carries_retry_after(tmp_path):
    respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "17"})
    )
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert result.metadata["error_kind"] == errors.RATE_LIMITED
    assert result.metadata["retry_after"] == 17.0


@respx.mock
async def test_500_is_upstream_error(tmp_path):
    respx.get("https://api.demo.test/v1/acme/items").mock(return_value=httpx.Response(500))
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert result.metadata["error_kind"] == errors.UPSTREAM_ERROR


@respx.mock
async def test_timeout_is_upstream_error_not_exception(tmp_path):
    respx.get("https://api.demo.test/v1/acme/items").mock(side_effect=httpx.ConnectTimeout("t"))
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert result.success is False
    assert result.metadata["error_kind"] == errors.UPSTREAM_ERROR


async def test_missing_credential_is_a_result_not_an_exception(tmp_path):
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(
        m, m.action("list_items"), {"owner": "acme"}, ResolvedConnection(name="c", material={})
    )
    assert result.success is False
    assert result.metadata["error_kind"] == errors.CREDENTIAL_MISSING


async def test_missing_required_argument_is_bad_request(tmp_path):
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {}, CONN)
    assert result.success is False
    assert result.metadata["error_kind"] == errors.BAD_REQUEST


async def test_traversal_argument_is_bad_request(tmp_path):
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(
        m, m.action("list_items"), {"owner": "../../me"}, CONN
    )
    assert result.success is False
    assert result.metadata["error_kind"] == errors.BAD_REQUEST


async def test_handler_action_receives_context(tmp_path):
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("custom"), {"x": "hola"}, CONN)
    assert result.success is True
    assert result.data == {"echo": "hola", "base": "https://api.demo.test/v1"}


async def test_handler_exception_degrades_the_call_not_the_run(tmp_path):
    m = _manifest(tmp_path)
    action = m.action("custom")
    action.handler = "python:tests.test_integration_executor:_boom"
    result = await HttpActionExecutor().execute(m, action, {"x": "1"}, CONN)
    assert result.success is False
    assert result.metadata["error_kind"] == errors.UPSTREAM_ERROR


@respx.mock
async def test_non_json_response_is_returned_as_text(tmp_path):
    respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, text="no soy json")
    )
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert result.success is True
    assert result.data == "no soy json"


@respx.mock
async def test_credential_never_appears_in_result(tmp_path):
    respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert "T0K3N" not in str(result.to_dict())
