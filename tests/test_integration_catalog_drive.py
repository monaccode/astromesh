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
    assert set(actions) == {"list_files", "get_file", "search", "upload_file", "read_file"}
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


DRIVE = "https://www.googleapis.com/drive/v3"


def _meta(mime, name="f"):
    return httpx.Response(200, json={"id": "F1", "name": name, "mimeType": mime})


async def _read():
    m = _drive()
    return await HttpActionExecutor().execute(m, m.action("read_file"), {"file_id": "F1"}, CONN)


@respx.mock(assert_all_mocked=True)
async def test_read_file_exports_docs_sheets_and_slides(respx_mock):
    for mime, out in (
        ("application/vnd.google-apps.document", "text/plain"),
        ("application/vnd.google-apps.spreadsheet", "text/csv"),
        ("application/vnd.google-apps.presentation", "text/plain"),
    ):
        respx_mock.get(f"{DRIVE}/files/F1").mock(return_value=_meta(mime))
        route = respx_mock.get(f"{DRIVE}/files/F1/export").mock(
            return_value=httpx.Response(200, text="hola ñ")
        )
        result = await _read()
        assert result.success is True
        assert result.data["texto"] == "hola ñ"
        assert result.data["recortado"] is False
        assert route.calls.last.request.url.params["mimeType"] == out


@respx.mock(assert_all_mocked=True)
async def test_read_file_downloads_text_and_json(respx_mock):
    for mime in ("text/plain", "application/json"):
        respx_mock.get(f"{DRIVE}/files/F1", params={"fields": "id,name,mimeType"}).mock(
            return_value=_meta(mime)
        )
        route = respx_mock.get(f"{DRIVE}/files/F1", params={"alt": "media"}).mock(
            return_value=httpx.Response(200, content=b'{"a": 1}')
        )
        result = await _read()
        assert result.data["texto"] == '{"a": 1}'
        assert route.called


@respx.mock(assert_all_mocked=True)
async def test_read_file_refuses_binaries_without_fetching_content(respx_mock):
    respx_mock.get(f"{DRIVE}/files/F1").mock(return_value=_meta("application/pdf"))
    result = await _read()
    assert result.success is False
    assert result.error == (
        "No puedo leer archivos application/pdf: pedí que lo pasen a un Doc de Google."
    )
    assert respx_mock.calls.call_count == 1


@respx.mock(assert_all_mocked=True)
async def test_read_file_truncates_at_50000(respx_mock):
    respx_mock.get(f"{DRIVE}/files/F1").mock(
        return_value=_meta("application/vnd.google-apps.document")
    )
    respx_mock.get(f"{DRIVE}/files/F1/export").mock(
        return_value=httpx.Response(200, text="a" * 60_000)
    )
    result = await _read()
    assert result.data["recortado"] is True
    assert result.data["texto"].startswith("a" * 50_000 + "\n\n[… recortado")
    assert "60000" in result.data["texto"]


@respx.mock(assert_all_mocked=True)
async def test_read_file_classifies_a_metadata_404(respx_mock):
    respx_mock.get(f"{DRIVE}/files/F1").mock(return_value=httpx.Response(404, text="nope"))
    result = await _read()
    assert result.success is False
    assert result.metadata["error_kind"] == errors.classify_status(404)


@respx.mock(assert_all_mocked=True)
async def test_read_file_refuses_ids_that_escape_the_path_segment(respx_mock):
    m = _drive()
    for bad in ("../x", "a/b", "..", "../../gmail/v1/users/me/messages"):
        result = await HttpActionExecutor().execute(
            m, m.action("read_file"), {"file_id": bad}, CONN
        )
        assert result.success is False, bad
    assert respx_mock.calls.call_count == 0


@respx.mock(assert_all_mocked=True)
async def test_read_file_encodes_query_injection_and_percent_escapes(respx_mock):
    route = respx_mock.get(url__regex=r".*").mock(return_value=httpx.Response(404, text="x"))
    m = _drive()
    for bad, esperado in (("X?alt=media&", "X%3Falt%3Dmedia%26"), ("%2F", "%252F")):
        await HttpActionExecutor().execute(m, m.action("read_file"), {"file_id": bad}, CONN)
        req = route.calls.last.request
        assert req.url.raw_path.decode().startswith(f"/drive/v3/files/{esperado}?fields=")
        assert "alt" not in req.url.params


@respx.mock(assert_all_mocked=True)
async def test_read_file_stops_reading_after_the_byte_cap(respx_mock):
    respx_mock.get(f"{DRIVE}/files/F1", params={"fields": "id,name,mimeType"}).mock(
        return_value=_meta("text/plain")
    )
    leidos = []

    async def cuerpo():
        # 1 MB en trozos de 10 kB; un lector que no corta consumiría todo.
        for _ in range(100):
            leidos.append(1)
            yield b"a" * 10_000

    respx_mock.get(f"{DRIVE}/files/F1", params={"alt": "media"}).mock(
        return_value=httpx.Response(200, content=cuerpo())
    )
    result = await _read()
    assert result.data["recortado"] is True
    assert result.data["texto"].startswith(
        "a" * 50_000 + "\n\n[… recortado: el original tiene más de"
    )
    assert len(leidos) < 100


@respx.mock(assert_all_mocked=True)
async def test_read_file_cap_does_not_leave_a_broken_utf8_tail(respx_mock):
    respx_mock.get(f"{DRIVE}/files/F1", params={"fields": "id,name,mimeType"}).mock(
        return_value=_meta("text/plain")
    )
    # 3 bytes por carácter: el corte a 200.000 bytes cae en medio de uno.
    respx_mock.get(f"{DRIVE}/files/F1", params={"alt": "media"}).mock(
        return_value=httpx.Response(200, content="€".encode() * 100_000)
    )
    result = await _read()
    assert "�" not in result.data["texto"]
    assert result.data["recortado"] is True
