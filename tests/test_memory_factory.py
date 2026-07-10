import pytest
from astromesh.memory.factory import build_conversation_backend


def test_returns_none_when_no_backend():
    assert build_conversation_backend({}) is None
    assert build_conversation_backend({"backend": None}) is None


def test_builds_redis_backend_lazily():
    be = build_conversation_backend(
        {"backend": "redis", "connection": {"url": "redis://localhost:6379/0"}, "ttl": 100}
    )
    # Check by class name, not isinstance: test_memory_backends.py pops and
    # re-imports astromesh.memory.backends.redis_conv with a fake aioredis,
    # leaving a distinct RedisConversationBackend class object in sys.modules,
    # so identity-based isinstance is fragile under full-suite ordering.
    assert type(be).__name__ == "RedisConversationBackend"
    assert be._ttl == 100  # aioredis.from_url is lazy; no live server needed


def test_redis_defaults_ttl():
    be = build_conversation_backend(
        {"backend": "redis", "connection": {"url": "redis://localhost:6379/0"}}
    )
    assert be._ttl == 259200


def test_unknown_backend_raises():
    with pytest.raises(ValueError):
        build_conversation_backend({"backend": "cassandra"})
