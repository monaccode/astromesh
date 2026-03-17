"""ADK exception hierarchy."""


class ADKError(Exception):
    """Base exception for all ADK errors."""


# --- Agent errors ---

class AgentError(ADKError):
    """Agent execution failure."""


class AgentNotFoundError(AgentError):
    """Agent not found by name."""


class OrchestrationError(AgentError):
    """Orchestration pattern failure (max iterations, timeout)."""


# --- Provider errors ---

class ProviderError(ADKError):
    """LLM provider failure."""


class ProviderUnavailableError(ProviderError):
    """All providers are down or circuit is open."""

    def __init__(self, message: str, attempts: list[str] | None = None):
        super().__init__(message)
        self.attempts = attempts or []


class AuthenticationError(ProviderError):
    """Invalid API key or credentials."""


class RateLimitError(ProviderError):
    """Provider rate limit exceeded."""


# --- Tool errors ---

class ToolError(ADKError):
    """Tool execution failure."""


class ToolNotFoundError(ToolError):
    """Tool not found by name."""


class ToolTimeoutError(ToolError):
    """Tool execution timed out."""


class ToolPermissionError(ToolError):
    """Tool execution not permitted."""


# --- Guardrail errors ---

class GuardrailError(ADKError):
    """Guardrail blocked content."""

    def __init__(self, message: str, reason: str = ""):
        super().__init__(message)
        self.reason = reason


class InputBlockedError(GuardrailError):
    """Input guardrail blocked the query."""


class OutputBlockedError(GuardrailError):
    """Output guardrail blocked the response."""


# --- Remote errors ---

class RemoteError(ADKError):
    """Remote Astromesh connection failure."""


class RemoteUnavailableError(RemoteError):
    """Remote Astromesh server is unreachable."""


class SyncError(RemoteError):
    """Agent registration/sync with remote failed."""
