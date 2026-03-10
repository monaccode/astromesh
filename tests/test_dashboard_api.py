# tests/test_dashboard_api.py
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from astromesh.api.routes.dashboard import router


def _make_app():
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    return app


class TestDashboardAPI:
    async def test_dashboard_returns_html(self):
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/dashboard/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "<html" in resp.text.lower()

    async def test_dashboard_contains_key_elements(self):
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/dashboard/")
        html = resp.text
        # Verify key UI sections exist
        assert "traces" in html.lower() or "Traces" in html
        assert "metrics" in html.lower() or "Metrics" in html
        assert "/v1/traces" in html  # fetches from traces API
        assert "/v1/metrics" in html  # fetches from metrics API

    async def test_dashboard_contains_workflow_section(self):
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/dashboard/")
        html = resp.text
        assert "workflow" in html.lower()

    async def test_dashboard_has_auto_refresh(self):
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/dashboard/")
        html = resp.text
        # Should have some form of auto-refresh (setInterval or similar)
        assert "setInterval" in html or "auto-refresh" in html.lower()
