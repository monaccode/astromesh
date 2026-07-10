import pytest

from astromesh.api.routes import rag as rag_route
from astromesh.rag.pipeline import RAGPipeline
from tests.rag_fakes import FakeEmbedder, FakeStore


@pytest.fixture
def fake_pipeline(monkeypatch):
    p = RAGPipeline(chunker=None, embedding_provider=FakeEmbedder(), vector_store=FakeStore())
    monkeypatch.setattr(rag_route, "resolve_pipeline", lambda name: p)
    return p


async def test_ingest_then_query(client, fake_pipeline):
    r1 = await client.post("/v1/rag/ingest", json={"pipeline": "pk", "document": "reembolsos: 30 días", "metadata": {"id": "d1"}})
    assert r1.status_code == 200
    assert r1.json()["chunks"] >= 1

    r2 = await client.post("/v1/rag/query", json={"pipeline": "pk", "query": "reembolsos", "top_k": 3})
    assert r2.status_code == 200
    body = r2.json()
    assert body["query"] == "reembolsos"
    assert any("30 días" in c.get("content", "") for c in body["results"])


async def test_query_unknown_pipeline_404(client, monkeypatch):
    monkeypatch.setattr(rag_route, "resolve_pipeline", lambda name: None)
    r = await client.post("/v1/rag/query", json={"pipeline": "nope", "query": "x"})
    assert r.status_code == 404
