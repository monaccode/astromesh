async def test_dev_login_creates_user_and_org(client):
    response = await client.post("/api/v1/auth/dev/login", params={"email": "test@example.com", "name": "Test User"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data

async def test_dev_login_idempotent(client):
    await client.post("/api/v1/auth/dev/login", params={"email": "same@test.com", "name": "Same"})
    response = await client.post("/api/v1/auth/dev/login", params={"email": "same@test.com", "name": "Same"})
    assert response.status_code == 200
