"""Peer client for inter-node communication in Astromesh OS."""

import logging

import httpx

logger = logging.getLogger("astromesh.peers")


class PeerClient:
    """Manages communication with peer Astromesh nodes."""

    def __init__(self, peers_config: list[dict]):
        self._peers = peers_config or []
        self._http = httpx.AsyncClient(timeout=30.0)
        self._peer_index: dict[str, dict] = {p["name"]: p for p in self._peers}
        self._round_robin: dict[str, int] = {}

    def find_peers(self, service: str) -> list[dict]:
        return [p for p in self._peers if service in p.get("services", [])]

    def list_peers(self) -> list[dict]:
        return list(self._peers)

    def to_dict(self) -> list[dict]:
        return [
            {"name": p["name"], "url": p["url"], "services": p.get("services", [])}
            for p in self._peers
        ]

    async def health_check(self, peer_name: str) -> bool:
        peer = self._peer_index.get(peer_name)
        if not peer:
            return False
        try:
            resp = await self._http.get(f"{peer['url']}/v1/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def health_check_all(self) -> dict[str, bool]:
        results = {}
        for peer in self._peers:
            results[peer["name"]] = await self.health_check(peer["name"])
        return results

    async def forward(self, service: str, method: str, path: str, **kwargs) -> dict:
        peers = self.find_peers(service)
        if not peers:
            raise RuntimeError(f"No peer available for service '{service}'")

        idx = self._round_robin.get(service, 0) % len(peers)
        self._round_robin[service] = idx + 1

        peer = peers[idx]
        url = f"{peer['url']}{path}"

        try:
            resp = await self._http.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("Failed to forward to peer %s: %s", peer["name"], e)
            for i in range(1, len(peers)):
                next_peer = peers[(idx + i) % len(peers)]
                try:
                    resp = await self._http.request(method, f"{next_peer['url']}{path}", **kwargs)
                    resp.raise_for_status()
                    return resp.json()
                except Exception:
                    continue
            raise RuntimeError(f"All peers for service '{service}' failed") from e

    async def close(self):
        await self._http.aclose()
