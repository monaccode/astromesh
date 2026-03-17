from astromesh_adk.memory import normalize_memory_config


def test_none_returns_empty():
    assert normalize_memory_config(None) == {}


def test_string_shorthand_sqlite():
    config = normalize_memory_config("sqlite")
    assert config["conversational"]["backend"] == "sqlite"
    assert config["conversational"]["strategy"] == "sliding_window"
    assert config["conversational"]["max_turns"] == 50


def test_string_shorthand_redis():
    config = normalize_memory_config("redis")
    assert config["conversational"]["backend"] == "redis"


def test_full_dict_passthrough():
    input_config = {
        "conversational": {"backend": "sqlite", "strategy": "summary", "max_turns": 20},
        "semantic": {"backend": "chromadb", "similarity_threshold": 0.8},
    }
    config = normalize_memory_config(input_config)
    assert config["conversational"]["strategy"] == "summary"
    assert config["semantic"]["backend"] == "chromadb"


def test_dict_shorthand_backends_only():
    config = normalize_memory_config({"conversational": "redis", "semantic": "faiss"})
    assert config["conversational"]["backend"] == "redis"
    assert config["conversational"]["strategy"] == "sliding_window"
    assert config["semantic"]["backend"] == "faiss"
