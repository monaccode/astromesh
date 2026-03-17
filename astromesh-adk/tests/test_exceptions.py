from astromesh_adk.exceptions import (
    ADKError,
    AgentError,
    AgentNotFoundError,
    OrchestrationError,
    ProviderError,
    ProviderUnavailableError,
    AuthenticationError,
    RateLimitError,
    ToolError,
    ToolNotFoundError,
    ToolTimeoutError,
    ToolPermissionError,
    GuardrailError,
    InputBlockedError,
    OutputBlockedError,
    RemoteError,
    RemoteUnavailableError,
    SyncError,
)


def test_exception_hierarchy():
    assert issubclass(AgentError, ADKError)
    assert issubclass(ProviderError, ADKError)
    assert issubclass(ToolError, ADKError)
    assert issubclass(GuardrailError, ADKError)
    assert issubclass(RemoteError, ADKError)


def test_agent_error_subtypes():
    assert issubclass(AgentNotFoundError, AgentError)
    assert issubclass(OrchestrationError, AgentError)


def test_provider_error_subtypes():
    assert issubclass(ProviderUnavailableError, ProviderError)
    assert issubclass(AuthenticationError, ProviderError)
    assert issubclass(RateLimitError, ProviderError)


def test_tool_error_subtypes():
    assert issubclass(ToolNotFoundError, ToolError)
    assert issubclass(ToolTimeoutError, ToolError)
    assert issubclass(ToolPermissionError, ToolError)


def test_guardrail_error_subtypes():
    assert issubclass(InputBlockedError, GuardrailError)
    assert issubclass(OutputBlockedError, GuardrailError)


def test_remote_error_subtypes():
    assert issubclass(RemoteUnavailableError, RemoteError)
    assert issubclass(SyncError, RemoteError)


def test_error_message():
    err = ProviderUnavailableError("all providers failed", attempts=["openai", "ollama"])
    assert str(err) == "all providers failed"
    assert err.attempts == ["openai", "ollama"]


def test_guardrail_error_has_reason():
    err = InputBlockedError("blocked", reason="PII detected")
    assert err.reason == "PII detected"
