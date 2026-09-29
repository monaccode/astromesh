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
    assert "+" not in raw
    assert "/" not in raw
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


CAL = "https://www.googleapis.com/calendar/v3"


def test_the_google_family_includes_calendar():
    manifest = _get("google_calendar")
    assert manifest.auth.scheme == "bearer"
    assert manifest.auth.credential == "access_token"
    assert not any(a.writes for a in manifest.actions)


@respx.mock
async def test_calendar_list_events_defaults_to_primary_and_orders_by_start():
    route = respx.get(f"{CAL}/calendars/primary/events").mock(
        return_value=httpx.Response(200, json={"items": [{"id": "e1"}]})
    )
    m = _get("google_calendar")
    result = await HttpActionExecutor().execute(
        m,
        m.action("list_events"),
        {"time_min": "2026-09-30T00:00:00Z", "time_max": "2026-10-01T00:00:00Z"},
        CONN,
    )
    assert result.data == [{"id": "e1"}]
    q = route.calls.last.request.url.params
    assert q["timeMin"] == "2026-09-30T00:00:00Z"
    assert q["timeMax"] == "2026-10-01T00:00:00Z"
    assert q["singleEvents"] == "true"
    assert q["orderBy"] == "startTime"
    assert q["maxResults"] == "50"
    assert "q" not in q


@respx.mock
async def test_calendar_list_events_omits_empty_range_and_sends_query():
    route = respx.get(f"{CAL}/calendars/work/events").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    m = _get("google_calendar")
    await HttpActionExecutor().execute(
        m, m.action("list_events"), {"calendar_id": "work", "query": "reunión"}, CONN
    )
    q = route.calls.last.request.url.params
    assert q["q"] == "reunión"
    assert "timeMin" not in q
    assert "timeMax" not in q


@respx.mock
async def test_calendar_list_calendars_returns_items():
    respx.get(f"{CAL}/users/me/calendarList").mock(
        return_value=httpx.Response(200, json={"items": [{"id": "primary"}]})
    )
    m = _get("google_calendar")
    result = await HttpActionExecutor().execute(m, m.action("list_calendars"), {}, CONN)
    assert result.data == [{"id": "primary"}]


@respx.mock
async def test_calendar_get_event_hits_the_event_path():
    respx.get(f"{CAL}/calendars/primary/events/e9").mock(
        return_value=httpx.Response(200, json={"id": "e9"})
    )
    m = _get("google_calendar")
    result = await HttpActionExecutor().execute(m, m.action("get_event"), {"event_id": "e9"}, CONN)
    assert result.data == {"id": "e9"}


def _part(mime, text=None, filename="", parts=None):
    part = {"mimeType": mime, "filename": filename, "body": {}}
    if text is not None:
        part["body"]["data"] = base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")
    if parts is not None:
        part["parts"] = parts
    return part


def _message(payload):
    payload["headers"] = [
        {"name": "From", "value": "ana@example.com"},
        {"name": "SUBJECT", "value": "Hola"},
        {"name": "Date", "value": "Mon, 28 Sep 2026"},
    ]
    return {"id": "m1", "threadId": "t1", "payload": payload}


async def _read_message(payload=None, response=None):
    respx.get(f"{GMAIL}/users/me/messages/m1").mock(
        return_value=response or httpx.Response(200, json=_message(payload))
    )
    m = _get("gmail")
    return await HttpActionExecutor().execute(
        m, m.action("read_message"), {"message_id": "m1"}, CONN
    )


@respx.mock
async def test_gmail_read_message_plain_body_and_headers():
    result = await _read_message(_part("text/plain", "Hola ñ"))
    data = result.data
    assert data["texto"] == "Hola ñ"
    assert data["from"] == "ana@example.com"
    assert data["subject"] == "Hola"
    assert data["thread_id"] == "t1"
    assert data["to"] == ""
    assert data["adjuntos"] == []
    assert data["recortado"] is False


@respx.mock
async def test_gmail_read_message_prefers_plain_in_alternative():
    payload = _part(
        "multipart/alternative",
        parts=[_part("text/html", "<b>html</b>"), _part("text/plain", "plano")],
    )
    result = await _read_message(payload)
    assert result.data["texto"] == "plano"


@respx.mock
async def test_gmail_read_message_strips_nested_html_and_decodes_entities():
    html = "<style>p{}</style><p>Hola &amp; adiós</p><script>x()</script><p>&lt;fin&gt;</p>"
    payload = _part(
        "multipart/mixed",
        parts=[_part("multipart/related", parts=[_part("text/html", html)])],
    )
    result = await _read_message(payload)
    assert result.data["texto"] == "Hola & adiós\n<fin>"


@respx.mock
async def test_gmail_read_message_lists_attachments_and_keeps_them_out_of_text():
    payload = _part(
        "multipart/mixed",
        parts=[
            _part("text/plain", "cuerpo"),
            _part("application/pdf", "SECRETO", filename="factura.pdf"),
        ],
    )
    result = await _read_message(payload)
    assert result.data["adjuntos"] == ["factura.pdf"]
    assert result.data["texto"] == "cuerpo"


@respx.mock
async def test_gmail_read_message_truncates_at_20000():
    result = await _read_message(_part("text/plain", "a" * 30_000))
    assert result.data["recortado"] is True
    assert result.data["texto"].startswith("a" * 20_000 + "\n\n[… recortado")
    assert "30000" in result.data["texto"]


@respx.mock
async def test_gmail_read_message_without_body_is_empty_text():
    result = await _read_message(_part("multipart/mixed", parts=[]))
    assert result.success is True
    assert result.data["texto"] == ""


@respx.mock
async def test_gmail_read_message_classifies_404():
    result = await _read_message(response=httpx.Response(404, text="nope"))
    assert result.success is False
    assert result.metadata["error_kind"] == errors.classify_status(404)
