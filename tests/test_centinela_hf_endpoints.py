import huggingface_hub

from astromesh.centinela import hf_endpoints
from astromesh.centinela.endpoints import plan_endpoints


class _FakeEndpoint:
    def __init__(self, url="https://ep.aws.endpoints.huggingface.cloud"):
        self.name = "centinela-sentiment-prod"
        self.repository = "astromesh/Centinela-Qwen3-4B"
        self.status = "running"
        self.url = url
        self.raw = {"model": {"revision": "a" * 40},
                    "compute": {"accelerator": "gpu", "instanceType": "nvidia-a10g",
                                "instanceSize": "x1"}}

    def wait(self, timeout=None):
        return self


def _desired():
    lock = {"schema_version": "1", "models": [{
        "name": "centinela-sentiment", "kind": "classifier", "task": "text-classification",
        "vertical": "finanzas", "hf_repo": "astromesh/Centinela-Qwen3-4B",
        "contract": {"labels": ["positivo"]}, "aliases": {"prod": "v0.1"},
        "revisions": {"v0.1": {"version": "v0.1", "sha": "a" * 40, "gate": "passed",
                               "eval": {"macro_f1": 0.9, "invalid_rate": 0.01}}}}]}
    bindings = {"spec": {"bindings": [{"model": "centinela-sentiment", "alias": "prod"}]}}
    return plan_endpoints(lock, bindings)[0]


def test_get_endpoint_normalizes(monkeypatch):
    monkeypatch.setattr(huggingface_hub, "get_inference_endpoint",
                        lambda *a, **k: _FakeEndpoint())
    got = hf_endpoints.get_endpoint("centinela-sentiment-prod", namespace="org", token="t")
    assert got["revision"] == "a" * 40
    assert got["instance_type"] == "nvidia-a10g"
    assert got["url"].startswith("https://")


def test_get_endpoint_returns_none_on_404(monkeypatch):
    import httpx
    from huggingface_hub.utils import HfHubHTTPError

    def _raise(*a, **k):
        request = httpx.Request("GET", "https://api.huggingface.co")
        response = httpx.Response(404, request=request)
        raise HfHubHTTPError("not found", response=response)

    monkeypatch.setattr(huggingface_hub, "get_inference_endpoint", _raise)
    assert hf_endpoints.get_endpoint("missing", namespace="org", token="t") is None


def test_create_endpoint_passes_mapped_kwargs(monkeypatch):
    captured = {}

    def _create(name, **kwargs):
        captured["name"] = name
        captured.update(kwargs)
        return _FakeEndpoint()

    monkeypatch.setattr(huggingface_hub, "create_inference_endpoint", _create)
    hf_endpoints.create_endpoint(_desired(), namespace="org", token="t")
    assert captured["name"] == "centinela-sentiment-prod"
    assert captured["repository"] == "astromesh/Centinela-Qwen3-4B"
    assert captured["revision"] == "a" * 40
    assert captured["type"] == "protected"
    assert captured["instance_type"] == "nvidia-a10g"


def test_wait_url_returns_url():
    assert hf_endpoints.wait_url(_FakeEndpoint(url="https://x"), timeout=5) == "https://x"
