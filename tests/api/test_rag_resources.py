import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from astromesh.api.routes import rag_resources


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    # Skip disk seeding and start from an empty in-memory store per test.
    monkeypatch.setattr(rag_resources, "_pipelines", {})
    monkeypatch.setattr(rag_resources, "_seeded", True)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(rag_resources.router, prefix="/v1")
    return TestClient(app)


def _pipeline(name="kb"):
    return {
        "apiVersion": "astromesh/v1",
        "kind": "RAGPipeline",
        "metadata": {"name": name},
        "spec": {"description": "docs", "vector_store": {"backend": "faiss"}},
    }


def test_create_list_get_roundtrip(client):
    assert client.get("/v1/rag/pipelines").json() == {"pipelines": []}
    r = client.post("/v1/rag/pipelines", json=_pipeline())
    assert r.status_code == 201
    assert r.json() == {"name": "kb", "status": "created"}
    listing = client.get("/v1/rag/pipelines").json()["pipelines"]
    assert listing == [{"name": "kb", "description": "docs", "backend": "faiss"}]
    assert client.get("/v1/rag/pipelines/kb").json() == _pipeline()


def test_duplicate_create_conflicts(client):
    client.post("/v1/rag/pipelines", json=_pipeline())
    assert client.post("/v1/rag/pipelines", json=_pipeline()).status_code == 409


def test_invalid_kind_is_422(client):
    bad = _pipeline()
    bad["kind"] = "Agent"
    assert client.post("/v1/rag/pipelines", json=bad).status_code == 422


def test_update_and_delete(client):
    client.post("/v1/rag/pipelines", json=_pipeline())
    updated = _pipeline()
    updated["spec"]["description"] = "changed"
    assert client.put("/v1/rag/pipelines/kb", json=updated).status_code == 200
    assert client.get("/v1/rag/pipelines/kb").json()["spec"]["description"] == "changed"
    assert client.delete("/v1/rag/pipelines/kb").status_code == 200
    assert client.get("/v1/rag/pipelines/kb").status_code == 404


def test_missing_get_update_delete_are_404(client):
    assert client.get("/v1/rag/pipelines/nope").status_code == 404
    assert client.put("/v1/rag/pipelines/nope", json=_pipeline("nope")).status_code == 404
    assert client.delete("/v1/rag/pipelines/nope").status_code == 404
