"""gmail y google_sheets: la familia Google, misma auth que google_drive."""

import base64
import json

import httpx
import respx

from astromesh.integrations import IntegrationCatalog, errors
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor

GMAIL = "https://gmail.googleapis.com/gmail/v1"
SHEETS = "https://sheets.googleapis.com/v4"
CONN = ResolvedConnection(name="g", material={"access_token": "T0K3N"})


def _get(slug):
    catalog = IntegrationCatalog()
    catalog.discover()
    return catalog.get(slug)


def test_the_google_family_shares_the_auth_scheme():
    for slug in ("google_drive", "gmail", "google_sheets"):
        manifest = _get(slug)
        assert manifest.auth.scheme == "bearer", slug
        assert manifest.auth.credential == "access_token", slug


@respx.mock
async def test_gmail_list_messages_passes_the_query_unencoded():
    route = respx.get(f"{GMAIL}/users/me/messages").mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "m1"}], "nextPageToken": "T2"})
    )
    m = _get("gmail")
    result = await HttpActionExecutor().execute(
        m, m.action("list_messages"), {"query": "from:ana@example.com is:unread"}, CONN
    )
    assert result.data == [{"id": "m1"}]
    assert result.metadata["next_cursor"] == "T2"
    assert route.calls[0].request.url.params["q"] == "from:ana@example.com is:unread"


@respx.mock
async def test_gmail_list_messages_omits_q_when_no_query():
    route = respx.get(f"{GMAIL}/users/me/messages").mock(
        return_value=httpx.Response(200, json={"messages": []})
    )
    m = _get("gmail")
    await HttpActionExecutor().execute(m, m.action("list_messages"), {}, CONN)
    assert "q" not in route.calls[0].request.url.params


@respx.mock
async def test_gmail_send_message_builds_base64url_mime():
    route = respx.post(f"{GMAIL}/users/me/messages/send").mock(
        return_value=httpx.Response(200, json={"id": "sent1", "threadId": "th1"})
    )
    m = _get("gmail")
    result = await HttpActionExecutor().execute(
        m,
        m.action("send_message"),
        {"to": "ana@example.com", "subject": "Hola", "body": "¿Cómo va?"},
        CONN,
    )
    assert result.success is True
    assert result.data["id"] == "sent1"

    raw = json.loads(route.calls[0].request.content)["raw"]
    # base64url, no base64 estándar: Gmail rechaza + y / acá.
    assert "+" not in raw and "/" not in raw
    mime = base64.urlsafe_b64decode(raw).decode()
    assert "To: ana@example.com" in mime
    assert "Subject: Hola" in mime


@respx.mock
async def test_gmail_send_message_handles_non_ascii_subject():
    """EmailMessage codifica la cabecera; concatenarla a mano la rompería."""
    route = respx.post(f"{GMAIL}/users/me/messages/send").mock(
        return_value=httpx.Response(200, json={"id": "s"})
    )
    m = _get("gmail")
    await HttpActionExecutor().execute(
        m,
        m.action("send_message"),
        {"to": "a@b.test", "subject": "Reunión mañana ñ", "body": "x"},
        CONN,
    )
    mime = base64.urlsafe_b64decode(json.loads(route.calls[0].request.content)["raw"]).decode()
    # La cabecera va codificada RFC 2047, no en crudo.
    assert "=?utf-8?" in mime.lower()


@respx.mock
async def test_gmail_send_message_threads_the_reply():
    route = respx.post(f"{GMAIL}/users/me/messages/send").mock(
        return_value=httpx.Response(200, json={"id": "s"})
    )
    m = _get("gmail")
    await HttpActionExecutor().execute(
        m,
        m.action("send_message"),
        {"to": "a@b.test", "subject": "re", "body": "x", "reply_to_thread_id": "TH9"},
        CONN,
    )
    assert json.loads(route.calls[0].request.content)["threadId"] == "TH9"


@respx.mock
async def test_gmail_send_message_maps_the_error():
    respx.post(f"{GMAIL}/users/me/messages/send").mock(return_value=httpx.Response(403))
    m = _get("gmail")
    result = await HttpActionExecutor().execute(
        m, m.action("send_message"), {"to": "a@b.test", "subject": "s", "body": "b"}, CONN
    )
    assert result.success is False
    assert result.metadata["error_kind"] == errors.CREDENTIAL_INVALID


@respx.mock
async def test_sheets_get_values_selects_the_rows():
    respx.get(f"{SHEETS}/spreadsheets/SHEET1/values/Hoja1%21A1%3AB2").mock(
        return_value=httpx.Response(200, json={"values": [["a", "b"], ["c", "d"]]})
    )
    m = _get("google_sheets")
    result = await HttpActionExecutor().execute(
        m, m.action("get_values"), {"spreadsheet_id": "SHEET1", "range": "Hoja1!A1:B2"}, CONN
    )
    assert result.success is True
    assert result.data == [["a", "b"], ["c", "d"]]


@respx.mock
async def test_sheets_update_values_sends_rows_as_a_list_not_a_string():
    """El tipo del argumento se conserva: mandar '[[...]]' como texto lo rechaza."""
    route = respx.put(f"{SHEETS}/spreadsheets/SHEET1/values/Hoja1%21A1").mock(
        return_value=httpx.Response(200, json={"updatedCells": 2})
    )
    m = _get("google_sheets")
    result = await HttpActionExecutor().execute(
        m,
        m.action("update_values"),
        {"spreadsheet_id": "SHEET1", "range": "Hoja1!A1", "values": [["x", "y"]]},
        CONN,
    )
    assert result.success is True
    assert json.loads(route.calls[0].request.content) == {"values": [["x", "y"]]}
    assert route.calls[0].request.url.params["valueInputOption"] == "USER_ENTERED"


@respx.mock
async def test_sheets_append_values_uses_insert_rows():
    route = respx.post(f"{SHEETS}/spreadsheets/SHEET1/values/Hoja1%21A%3AD:append").mock(
        return_value=httpx.Response(200, json={"updates": {"updatedRows": 1}})
    )
    m = _get("google_sheets")
    result = await HttpActionExecutor().execute(
        m,
        m.action("append_values"),
        {"spreadsheet_id": "SHEET1", "range": "Hoja1!A:D", "values": [["n"]]},
        CONN,
    )
    assert result.success is True
    assert route.calls[0].request.url.params["insertDataOption"] == "INSERT_ROWS"
