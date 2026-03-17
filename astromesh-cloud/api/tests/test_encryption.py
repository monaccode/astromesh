import pytest
from cryptography.fernet import Fernet

@pytest.fixture(autouse=True)
def set_fernet_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ASTROMESH_CLOUD_FERNET_KEY", key)
    import astromesh_cloud.config as cfg
    monkeypatch.setattr(cfg.settings, "fernet_key", key)
    import astromesh_cloud.services.encryption as enc
    enc._fernet = None

def test_encrypt_decrypt_roundtrip():
    from astromesh_cloud.services.encryption import encrypt_key, decrypt_key
    original = "sk-test-12345"
    encrypted = encrypt_key(original)
    assert encrypted != original.encode()
    assert decrypt_key(encrypted) == original
