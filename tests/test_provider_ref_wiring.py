import yaml

from astromesh.providers.centinela import CentinelaProvider
from astromesh.runtime.engine import AgentRuntime, build_candidate_provider
from astromesh.runtime.provider_registry import resolve_block


def _providers_doc(providers):
    return {
        "apiVersion": "astromesh/v1",
        "kind": "ProviderConfig",
        "metadata": {"name": "g"},
        "spec": {"providers": providers},
    }


def test_provider_ref_resolves_to_centinela_provider():
    reg = {
        "centinela-sentiment": {
            "type": "centinela",
            "endpoint": "https://ep.test",
            "contract": {"labels": ["positivo", "negativo"]},
            "models": ["centinela-sentiment"],
        }
    }
    block = resolve_block({"providerRef": "centinela-sentiment"}, reg)
    prov = build_candidate_provider(block)
    assert isinstance(prov, CentinelaProvider)
    assert prov._client.endpoint == "https://ep.test"


def test_engine_loads_registry_at_init(tmp_path):
    (tmp_path / "providers.centinela.yaml").write_text(
        yaml.safe_dump(
            _providers_doc(
                {
                    "centinela-sentiment": {
                        "type": "centinela",
                        "endpoint": "https://ep.test",
                        "models": ["centinela-sentiment"],
                    }
                }
            )
        )
    )
    engine = AgentRuntime(config_dir=str(tmp_path))
    assert "centinela-sentiment" in engine._provider_registry


def test_engine_build_role_routers_resolves_provider_ref(tmp_path):
    (tmp_path / "providers.centinela.yaml").write_text(
        yaml.safe_dump(
            _providers_doc(
                {
                    "centinela-sentiment": {
                        "type": "centinela",
                        "endpoint": "https://ep.test",
                        "contract": {"labels": ["positivo"]},
                        "models": ["centinela-sentiment"],
                    }
                }
            )
        )
    )
    engine = AgentRuntime(config_dir=str(tmp_path))
    routers = engine._build_role_routers(
        {"default": {"candidates": [{"providerRef": "centinela-sentiment"}]}}
    )
    provs = list(routers["default"]._providers.values())  # ModelRouter stores providers here
    assert len(provs) == 1
    assert isinstance(provs[0], CentinelaProvider)
    assert provs[0]._client.endpoint == "https://ep.test"
