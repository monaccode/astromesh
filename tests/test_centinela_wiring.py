from astromesh.providers.centinela import CentinelaProvider
from astromesh.providers.factory import create_provider
from astromesh.runtime.engine import build_candidate_provider


def test_build_candidate_provider_centinela():
    provider = build_candidate_provider(
        {
            "source": "centinela",
            "endpoint": "https://ep.example.cloud",
            "model": "centinela-sentiment",
            "contract": {"labels": ["positivo", "neutral", "negativo"]},
        }
    )
    assert isinstance(provider, CentinelaProvider)
    assert provider.model == "centinela-sentiment"
    assert provider._client.endpoint == "https://ep.example.cloud"
    assert provider._client.labels == ["positivo", "neutral", "negativo"]


def test_factory_create_provider_centinela():
    provider = create_provider("centinela", "")
    assert isinstance(provider, CentinelaProvider)
