import pytest

from astromesh.api.routes.metrics import (
    _counters,
    _histograms,
    get_counters,
    get_histograms,
    increment,
    observe,
)


@pytest.fixture(autouse=True)
def _clear_metrics():
    _counters.clear()
    _histograms.clear()
    yield
    _counters.clear()
    _histograms.clear()


# --- unit tests for helper functions ---


def test_increment_creates_counter():
    increment("requests")
    assert get_counters() == {"requests": 1}


def test_increment_adds_to_existing():
    increment("requests", 3)
    increment("requests", 2)
    assert get_counters()["requests"] == 5


def test_observe_records_values():
    observe("latency", 0.1)
    observe("latency", 0.3)
    hist = get_histograms()
    assert hist["latency"]["count"] == 2
    assert hist["latency"]["min"] == pytest.approx(0.1)
    assert hist["latency"]["max"] == pytest.approx(0.3)
    assert hist["latency"]["avg"] == pytest.approx(0.2)
    assert hist["latency"]["sum"] == pytest.approx(0.4)


def test_get_histograms_empty():
    assert get_histograms() == {}


# --- API endpoint tests ---


async def test_get_metrics_empty(client):
    resp = await client.get("/v1/metrics/")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"counters": {}, "histograms": {}}


async def test_get_metrics_with_data(client):
    increment("agent_runs", 5)
    observe("latency_ms", 120.0)
    observe("latency_ms", 80.0)

    resp = await client.get("/v1/metrics/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["counters"]["agent_runs"] == 5
    assert data["histograms"]["latency_ms"]["count"] == 2
    assert data["histograms"]["latency_ms"]["avg"] == pytest.approx(100.0)


async def test_reset_metrics(client):
    increment("requests", 10)
    observe("duration", 1.5)

    resp = await client.post("/v1/metrics/reset")
    assert resp.status_code == 200
    assert resp.json() == {"status": "reset"}

    resp = await client.get("/v1/metrics/")
    data = resp.json()
    assert data == {"counters": {}, "histograms": {}}
