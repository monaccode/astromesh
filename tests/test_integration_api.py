async def test_list_integrations(client):
    response = await client.get("/v1/integrations")
    assert response.status_code == 200
    body = response.json()
    slugs = {item["slug"] for item in body["integrations"]}
    assert {"http", "whatsapp", "google_drive"} <= slugs
    assert body["count"] == len(body["integrations"])


async def test_integration_detail_lists_actions_and_required_credentials(client):
    response = await client.get("/v1/integrations/whatsapp")
    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "whatsapp"
    assert body["auth"]["scheme"] == "bearer"
    assert body["auth"]["credential"] == "access_token"
    names = {a["name"] for a in body["actions"]}
    assert "send_text" in names
    action = next(a for a in body["actions"] if a["name"] == "send_text")
    assert action["writes"] is True
    assert action["parameters"]["type"] == "object"


async def test_unknown_integration_is_404(client):
    assert (await client.get("/v1/integrations/no_existe")).status_code == 404


async def test_detail_never_exposes_credential_values(client, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "SECRETO-XYZ")
    body = (await client.get("/v1/integrations/whatsapp")).text
    assert "SECRETO-XYZ" not in body


async def test_list_tools_reports_integration_actions(client):
    body = (await client.get("/v1/tools")).json()
    names = {t["name"] for t in body["tools"]}
    assert "whatsapp_send_text" in names


async def test_run_request_accepts_connections_field():
    from astromesh.api.routes.agents import AgentRunRequest

    request = AgentRunRequest(query="hola", connections={"c": {"access_token": "T"}})
    assert request.connections == {"c": {"access_token": "T"}}
    assert AgentRunRequest(query="hola").connections is None
