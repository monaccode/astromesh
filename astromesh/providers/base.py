"""Base provider types for the Astromesh model routing layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Protocol, runtime_checkable


class RoutingStrategy(str, Enum):
    """Strategy used by the model router to select a provider."""

    COST_OPTIMIZED = "cost_optimized"
    LATENCY_OPTIMIZED = "latency_optimized"
    QUALITY_FIRST = "quality_first"
    ROUND_ROBIN = "round_robin"
    CAPABILITY_MATCH = "capability_match"


@dataclass
class CompletionResponse:
    """Unified response returned by any provider."""

    content: str
    model: str
    provider: str
    usage: dict
    latency_ms: float
    cost: float
    tool_calls: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class CompletionChunk:
    """A single chunk emitted while streaming a completion."""

    content: str
    model: str
    provider: str
    done: bool = False
    usage: dict | None = None


@dataclass
class ProviderHealth:
    """Tracks the health status of a provider endpoint."""

    is_healthy: bool = True
    last_check: float = 0.0
    consecutive_failures: int = 0
    avg_latency_ms: float = 0.0
    circuit_open: bool = False
    circuit_open_until: float = 0.0


@runtime_checkable
class ProviderProtocol(Protocol):
    """Protocol that every LLM provider adapter must implement."""

    async def complete(self, messages: list[dict], **kwargs) -> CompletionResponse:
        """Return a full completion for the given messages."""
        ...

    async def stream(self, messages: list[dict], **kwargs) -> AsyncIterator[CompletionChunk]:
        """Yield completion chunks for the given messages."""
        ...

    async def health_check(self) -> bool:
        """Return True if the provider is reachable and healthy."""
        ...

    def supports_tools(self) -> bool:
        """Whether this provider supports tool/function calling."""
        ...

    def supports_vision(self) -> bool:
        """Whether this provider supports vision/image inputs."""
        ...

    def estimated_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate the dollar cost for the given token counts."""
        ...
