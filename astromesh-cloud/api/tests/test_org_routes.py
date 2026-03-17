import pytest


@pytest.fixture
async def auth_headers(client):
    resp = await client.post("/api/v1/auth/dev/login", params={"email": "orgtest@test.com", "name": "Org Test"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_get_my_org(client, auth_headers):
    response = await client.get("/api/v1/orgs/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "slug" in data
    assert data["name"] == "Org Test's Org"
