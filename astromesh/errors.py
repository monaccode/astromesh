"""Structured errors for API and runtime (user-facing messages and hints)."""

from __future__ import annotations

import errno
import socket
from typing import Any


class ModelProviderError(RuntimeError):
    """All model backends failed or none are configured."""

    def __init__(
        self,
        message: str,
        *,
        hint: str = "",
        code: str = "model_provider_unavailable",
        cause: BaseException | None = None,
    ) -> None:
        self.hint = hint
        self.code = code
        super().__init__(message)
        self.__cause__ = cause


def explain_no_eligible_providers(registered_provider_names: list[str]) -> ModelProviderError:
    """All registered providers were skipped (e.g. circuit open, capability filter)."""
    reg = ", ".join(registered_provider_names) if registered_provider_names else "(none)"
    return ModelProviderError(
        "No model provider is eligible for this request right now.",
        hint=(
            "Providers may be in circuit-breaker cooldown or excluded by routing (e.g. vision/tools). "
            f"Registered slots: {reg}. Wait a minute and retry, or check provider health."
        ),
        code="model_no_eligible_provider",
    )


def explain_model_provider_failure(
    last_error: BaseException | None,
    *,
    candidate_names: list[str] | None = None,
    registered_provider_names: list[str] | None = None,
) -> ModelProviderError:
    """Build a declarative error from the last provider exception (or missing config)."""
    candidates = candidate_names or []
    registered = registered_provider_names or []
    listed = ", ".join(candidates) if candidates else "(none eligible this request)"

    if not registered:
        return ModelProviderError(
            "No LLM providers are configured for this agent.",
            hint=(
                "Define spec.model.primary (and optional fallback) in the agent YAML with a "
                "valid provider (e.g. ollama with endpoint http://127.0.0.1:11434 when the "
                "API runs on the host)."
            ),
            code="model_no_providers",
        )

    if last_error is None:
        return ModelProviderError(
            f"Every configured model provider failed (tried: {listed}).",
            hint=(
                "Check provider health, API keys, and network access. "
                f"Registered slots: {', '.join(registered)}."
            ),
            code="model_all_providers_failed",
        )

    msg = str(last_error).strip()

    def _walk_io() -> tuple[BaseException | None, int | None]:
        cur: BaseException | None = last_error
        seen: set[int] = set()
        while cur is not None and id(cur) not in seen:
            seen.add(id(cur))
            if isinstance(cur, socket.gaierror):
                return cur, cur.errno
            if isinstance(cur, OSError):
                return cur, cur.errno
            cur = cur.__cause__ or cur.__context__
        return None, None

    root, errno_val = _walk_io()

    # DNS / hostname (Windows 11001 WSAHOST_NOT_FOUND; Unix often socket.gaierror)
    dns_errnos = {11001, 11002}
    for name in ("EAI_NONAME", "EAI_FAIL", "EAI_AGAIN"):
        if hasattr(errno, name):
            dns_errnos.add(getattr(errno, name))
    if isinstance(root, socket.gaierror) or (errno_val is not None and errno_val in dns_errnos):
        return ModelProviderError(
            "Could not resolve the LLM server hostname (DNS lookup failed).",
            hint=(
                "If the agent uses a Docker-only hostname (e.g. http://ollama:11434), switch to "
                "http://127.0.0.1:11434 or http://localhost:11434 when running the API on your "
                f"machine. Underlying: {msg}"
            ),
            code="model_dns_resolution_failed",
            cause=last_error,
        )

    if isinstance(root, ConnectionRefusedError) or (
        errno_val is not None and errno_val in (errno.ECONNREFUSED, 10061)
    ):
        return ModelProviderError(
            "Connection refused by the LLM server (nothing is listening on that host:port).",
            hint=(
                "Start Ollama (or your OpenAI-compatible server) and confirm the agent's "
                f"endpoint matches. Underlying: {msg}"
            ),
            code="model_connection_refused",
            cause=last_error,
        )

    if isinstance(root, TimeoutError) or "timeout" in msg.lower():
        return ModelProviderError(
            "The LLM request timed out.",
            hint="Increase timeout in provider config, reduce load, or check server performance.",
            code="model_timeout",
            cause=last_error,
        )

    low = msg.lower()
    if "404" in msg and "api/chat" in low:
        return ModelProviderError(
            "LLM endpoint returned 404 for /api/chat.",
            hint=(
                "Often means the Ollama model name is wrong or not pulled: run "
                "`ollama pull <model>` and match the agent's model field exactly."
            ),
            code="model_ollama_chat_404",
            cause=last_error,
        )

    reg = ", ".join(registered) if registered else "(unknown)"
    return ModelProviderError(
        f"All model providers failed. Last error: {msg}",
        hint=(
            f"Attempted this request: {listed}. Registered: {reg}. "
            "Verify endpoints, API keys, and that services are reachable."
        ),
        code="model_all_providers_failed",
        cause=last_error,
    )


def model_provider_error_payload(exc: ModelProviderError) -> dict[str, Any]:
    """Shape for HTTP JSON responses."""
    return {
        "error": exc.code,
        "message": str(exc),
        "hint": exc.hint,
    }
