"""HTTP proxy to Astromesh runtime with namespace rewriting, session prefixing, and BYOK."""
import httpx
from astromesh_cloud.config import settings

class RuntimeProxy:
    def __init__(self, base_url: str | None = None):
        self._base_url = (base_url or settings.runtime_url).rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=60.0)

    async def register_agent(self, config: dict) -> dict:
        resp = await self._client.post("/v1/agents", json=config)
        resp.raise_for_status()
        return resp.json()

    async def unregister_agent(self, runtime_name: str) -> dict:
        resp = await self._client.delete(f"/v1/agents/{runtime_name}")
        resp.raise_for_status()
        return resp.json()

    async def run_agent(self, runtime_name: str, query: str, session_id: str, org_slug: str, context: dict | None = None, provider_key: str | None = None, provider_name: str | None = None) -> dict:
        namespaced_session = f"{org_slug}:{session_id}"
        headers = {}
        if provider_key and provider_name:
            headers["X-Astromesh-Provider-Key"] = provider_key
            headers["X-Astromesh-Provider-Name"] = provider_name
        body = {"query": query, "session_id": namespaced_session, "context": context}
        resp = await self._client.post(f"/v1/agents/{runtime_name}/run", json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def delete_memory(self, runtime_name: str, session_id: str) -> None:
        resp = await self._client.delete(f"/v1/memory/{runtime_name}/history/{session_id}")
        resp.raise_for_status()

    async def list_agents(self) -> list[dict]:
        resp = await self._client.get("/v1/agents")
        resp.raise_for_status()
        return resp.json()

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/v1/health")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self):
        await self._client.aclose()
