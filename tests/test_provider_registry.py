import yaml

from astromesh.runtime.provider_registry import load_provider_registry, resolve_block


def _write(directory, name, doc):
    (directory / name).write_text(yaml.safe_dump(doc))


def _pc(providers):
    return {"apiVersion": "astromesh/v1", "kind": "ProviderConfig",
            "metadata": {"name": "x"}, "spec": {"providers": providers}}


def test_load_merges_multiple_files(tmp_path):
    _write(tmp_path, "providers.yaml",
           _pc({"openai": {"type": "openai_compat", "endpoint": "https://o"}}))
    _write(tmp_path, "providers.centinela.yaml",
           _pc({"centinela-sentiment": {"type": "centinela", "endpoint": "https://c"}}))
    reg = load_provider_registry(tmp_path)
    assert set(reg) == {"openai", "centinela-sentiment"}
    assert reg["centinela-sentiment"]["type"] == "centinela"


def test_load_missing_dir_is_empty(tmp_path):
    assert load_provider_registry(tmp_path / "nope") == {}


def test_load_skips_malformed_keeps_sibling(tmp_path):
    (tmp_path / "providers.bad.yaml").write_text("foo: [1, 2\n")  # unclosed flow seq -> YAMLError
    _write(tmp_path, "providers.centinela.yaml", _pc({"m": {"type": "centinela"}}))
    reg = load_provider_registry(tmp_path)
    assert "m" in reg


def test_load_duplicate_name_later_file_wins(tmp_path):
    _write(tmp_path, "providers.a.yaml", _pc({"dup": {"type": "openai_compat", "endpoint": "A"}}))
    _write(tmp_path, "providers.b.yaml", _pc({"dup": {"type": "openai_compat", "endpoint": "B"}}))
    reg = load_provider_registry(tmp_path)
    assert reg["dup"]["endpoint"] == "B"  # sorted order: a before b, b wins


def test_resolve_centinela_ref_fills_source_and_fields():
    reg = {"centinela-sentiment": {"type": "centinela", "endpoint": "https://ep",
                                   "endpoint_name": "centinela-sentiment-prod",
                                   "api_key_env": "HF_TOKEN",
                                   "contract": {"labels": ["pos", "neg"]},
                                   "models": ["centinela-sentiment"]}}
    out = resolve_block({"providerRef": "centinela-sentiment"}, reg)
    assert out["source"] == "centinela"
    assert out["endpoint"] == "https://ep"
    assert out["endpoint_name"] == "centinela-sentiment-prod"
    assert out["api_key_env"] == "HF_TOKEN"
    assert out["contract"]["labels"] == ["pos", "neg"]
    assert out["model"] == "centinela-sentiment"


def test_resolve_explicit_field_overrides_entry():
    reg = {"m": {"type": "centinela", "endpoint": "https://entry", "models": ["m"]}}
    out = resolve_block({"providerRef": "m", "endpoint": "https://override"}, reg)
    assert out["endpoint"] == "https://override"


def test_resolve_block_without_ref_is_unchanged():
    block = {"source": "openai_compat", "model": "gpt-4o"}
    assert resolve_block(block, {}) == block


def test_resolve_unknown_ref_yields_skippable_block():
    out = resolve_block({"providerRef": "missing"}, {})
    assert out.get("source") not in ("centinela", "openai_compat", "openai", "ollama", "litellm")
