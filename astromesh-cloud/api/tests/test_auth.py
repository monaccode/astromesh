import pytest
from astromesh_cloud.services.auth_service import create_access_token, create_refresh_token, verify_token

def test_create_and_verify_access_token():
    token = create_access_token("user-123", "test@example.com")
    payload = verify_token(token)
    assert payload["sub"] == "user-123"
    assert payload["email"] == "test@example.com"

def test_create_and_verify_refresh_token():
    token = create_refresh_token("user-123")
    payload = verify_token(token, expected_type="refresh")
    assert payload["sub"] == "user-123"

def test_verify_invalid_token():
    with pytest.raises(ValueError, match="Invalid token"):
        verify_token("not-a-real-token")

def test_verify_wrong_type():
    token = create_refresh_token("user-123")
    with pytest.raises(ValueError, match="Invalid token type"):
        verify_token(token, expected_type="access")
