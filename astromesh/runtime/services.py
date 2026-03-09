"""Service manager for Astromesh OS node roles."""

DEFAULT_SERVICES = (
    "api",
    "agents",
    "inference",
    "memory",
    "tools",
    "channels",
    "rag",
    "observability",
)


class ServiceManager:
    """Controls which services are active on this node."""

    def __init__(self, services_config: dict[str, bool]):
        self._services: dict[str, bool] = {}
        for service in DEFAULT_SERVICES:
            self._services[service] = services_config.get(service, True)

    def is_enabled(self, service: str) -> bool:
        return self._services.get(service, False)

    def enabled_services(self) -> list[str]:
        return [s for s, enabled in self._services.items() if enabled]

    def validate(self) -> list[str]:
        warnings: list[str] = []
        if self._services.get("agents") and not self._services.get("tools"):
            warnings.append("agents enabled without tools — agents won't be able to use tools")
        if self._services.get("agents") and not self._services.get("memory"):
            warnings.append(
                "agents enabled without memory — agents won't have conversation history"
            )
        return warnings

    def to_dict(self) -> dict[str, bool]:
        return dict(self._services)
