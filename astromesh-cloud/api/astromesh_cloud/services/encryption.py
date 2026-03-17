from cryptography.fernet import Fernet
from astromesh_cloud.config import settings

_fernet: Fernet | None = None

def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = settings.fernet_key
        if not key:
            raise RuntimeError("ASTROMESH_CLOUD_FERNET_KEY not configured")
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet

def encrypt_key(plaintext: str) -> bytes:
    return _get_fernet().encrypt(plaintext.encode())

def decrypt_key(ciphertext: bytes) -> str:
    return _get_fernet().decrypt(ciphertext).decode()
