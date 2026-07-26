import httpx
import respx

from astromesh.integrations import IntegrationCatalog, errors
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor

CONN = ResolvedConnection(name="drive", material={"access_token": "T0K3N"})


def _drive():
    catalog = IntegrationCatalog()
    catalog.discover()
    return catalog.get("google_drive")


def test_actions_and_modes():
    manifest = _drive()
    actions = {a.name: a for a in manifest.actions}
    assert set(actions) == {"list_files", "get_file", "search", "upload_file"}
    assert actions["list_files"].handler is None
    assert actions["upload_file"].handler is not None
    assert actions["upload_file"].writes is True


@respx.mock
async def test_list_files_paginates_by_token():
    route = respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=httpx.Response(200, json={"files": [{"id": "1"}], "nextPageToken": "TOK2"})
    )
    manifest = _drive()
    result = await HttpActionExecutor().execute(
        manifest, manifest.action("list_files"), {"page_size": 10}, CONN
    )
    assert result.success is True
    assert result.data == [{"id": "1"}]
    assert result.metadata["next_cursor"] == "TOK2"
    assert route.calls[0].request.url.params["pageSize"] == "10"


@respx.mock
async def test_list_files_sends_cursor_as_page_token():
    route = respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=httpx.Response(200, json={"files": []})
    )
    manifest = _drive()
    await HttpActionExecutor().execute(
        manifest, manifest.action("list_files"), {"cursor": "TOK2"}, CONN
    )
    assert route.calls[0].request.url.params["pageToken"] == "TOK2"


@respx.mock
async def test_search_passes_the_query():
    route = respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=httpx.Response(200, json={"files": []})
    )
    manifest = _drive()
    await HttpActionExecutor().execute(
        manifest, manifest.action("search"), {"query": "name contains 'informe'"}, CONN
    )
    assert route.calls[0].request.url.params["q"] == "name contains 'informe'"


@respx.mock
async def test_upload_file_runs_the_resumable_session():
    init = respx.post("https://www.googleapis.com/upload/drive/v3/files").mock(
        return_value=httpx.Response(
            200, headers={"Location": "https://upload.googleapis.com/session/ABC"}
        )
    )
    put = respx.put("https://upload.googleapis.com/session/ABC").mock(
        return_value=httpx.Response(200, json={"id": "FILE1", "name": "notas.txt"})
    )
    manifest = _drive()
    result = await HttpActionExecutor().execute(
        manifest,
        manifest.action("upload_file"),
        {"name": "notas.txt", "content": "hola mundo", "mime_type": "text/plain"},
        CONN,
    )
    assert result.success is True
    assert result.data["id"] == "FILE1"
    assert init.called
    assert put.called
    assert init.calls[0].request.headers["Authorization"] == "Bearer T0K3N"
    assert put.calls[0].request.content == b"hola mundo"


@respx.mock
async def test_upload_without_session_url_fails_cleanly():
    respx.post("https://www.googleapis.com/upload/drive/v3/files").mock(
        return_value=httpx.Response(200)  # sin Location
    )
    manifest = _drive()
    result = await HttpActionExecutor().execute(
        manifest, manifest.action("upload_file"), {"name": "x", "content": "y"}, CONN
    )
    assert result.success is False
    assert result.metadata["error_kind"] == errors.UPSTREAM_ERROR


@respx.mock
async def test_upload_init_error_is_classified():
    respx.post("https://www.googleapis.com/upload/drive/v3/files").mock(
        return_value=httpx.Response(401, json={"error": "expired"})
    )
    manifest = _drive()
    result = await HttpActionExecutor().execute(
        manifest, manifest.action("upload_file"), {"name": "x", "content": "y"}, CONN
    )
    assert result.success is False
    assert result.metadata["error_kind"] == errors.CREDENTIAL_INVALID
