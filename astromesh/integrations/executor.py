"""Ejecutor de acciones de integración: declarativas y con handler Python."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from astromesh.integrations import errors
from astromesh.integrations.auth import CredentialMissing, apply_auth
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.handlers import HandlerError, load_handler
from astromesh.integrations.interpolation import (
    OMIT,
    InterpolationError,
    interpolate,
    interpolate_structure,
)
from astromesh.integrations.manifest import ActionSpec, IntegrationManifest
from astromesh.observability.tracing import SpanStatus, TracingContext
from astromesh.tools.base import ToolResult

logger = logging.getLogger(__name__)

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class IntegrationContext:
    """Lo que recibe un handler Python.

    Trae un cliente ya configurado con timeout y auth: un handler no
    reimplementa autenticación ni construye clientes.
    """

    client: httpx.AsyncClient
    base_url: str
    material: dict = field(default_factory=dict)
    auth_headers: dict = field(default_factory=dict)
    agent_name: str = ""
    session_id: str = ""


def _select(payload: Any, path: str | None) -> Any:
    """Camino separado por puntos dentro del payload. Ausente → payload entero."""
    if not path:
        return payload
    current = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _fail(kind: str, message: str, **metadata) -> ToolResult:
    return ToolResult(
        success=False, data=None, error=message, metadata={"error_kind": kind, **metadata}
    )


class HttpActionExecutor:
    """Convierte una acción del manifest en una llamada HTTP y su resultado."""

    async def execute(
        self,
        manifest: IntegrationManifest,
        action: ActionSpec,
        arguments: dict,
        resolved: ResolvedConnection,
        *,
        agent_name: str = "",
        session_id: str = "",
    ) -> ToolResult:
        """Nunca levanta. Todo fallo sale como ToolResult(success=False).

        `tool_fn` re-lanza lo que reciba y eso mata la corrida entera; un 404
        de un proveedor externo no puede tumbar al agente.
        """
        base_url = (resolved.base_url or manifest.base_url or "").rstrip("/")
        if not base_url:
            return _fail(
                errors.BAD_REQUEST,
                f"la integración '{manifest.slug}' no tiene base_url: ni el manifest ni la "
                f"conexión '{resolved.name}' lo declaran",
            )

        try:
            auth_headers, auth_params = apply_auth(manifest.auth, resolved.material)
        except CredentialMissing as exc:
            return _fail(errors.CREDENTIAL_MISSING, str(exc))

        args = self._with_defaults(action, arguments)
        timeout = action.timeout_seconds or manifest.defaults.timeout_seconds
        headers = {**manifest.defaults.headers, **auth_headers}

        if action.handler:
            return await self._run_handler(
                action, args, base_url, headers, resolved, timeout, agent_name, session_id
            )
        return await self._run_request(
            manifest, action, args, base_url, headers, auth_params, timeout
        )

    @staticmethod
    def _with_defaults(action: ActionSpec, arguments: dict) -> dict:
        args = dict(arguments or {})
        for name, spec in (action.parameters or {}).items():
            if name not in args and isinstance(spec, dict) and "default" in spec:
                args[name] = spec["default"]
        return args

    # ASYNC109: el `timeout` no lo implementa esta corrutina, se lo pasa entero a
    # httpx.AsyncClient, que es quien lo aplica. No hay nada que mover a un
    # context manager de cancelación.
    async def _run_handler(
        self,
        action,
        args,
        base_url,
        headers,
        resolved,
        timeout,  # noqa: ASYNC109
        agent_name,
        session_id,
    ) -> ToolResult:
        try:
            fn = load_handler(action.handler)
        except HandlerError as exc:
            return _fail(errors.UPSTREAM_ERROR, str(exc))
        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
                ctx = IntegrationContext(
                    client=client,
                    base_url=base_url,
                    material=resolved.material,
                    auth_headers=headers,
                    agent_name=agent_name,
                    session_id=session_id,
                )
                result = await fn(args, ctx)
            if isinstance(result, ToolResult):
                return result
            return ToolResult(success=True, data=result, metadata={})
        # Atrapar todo es el contrato, no un descuido: un handler con un bug
        # degrada esta llamada, nunca la corrida entera.
        except Exception as exc:  # noqa: BLE001
            logger.warning("handler %s falló: %s", action.handler, exc)
            return _fail(errors.classify_exception(exc), f"{type(exc).__name__}: {exc}")

    # ASYNC109: mismo motivo que _run_handler.
    async def _run_request(
        self,
        manifest,
        action,
        args,
        base_url,
        headers,
        auth_params,
        timeout,  # noqa: ASYNC109
    ) -> ToolResult:
        allow_slash = set(action.allow_slash or [])
        try:
            path = self._render_path(action.request.path, args, allow_slash)
            # "raw", no "query": httpx percent-encodea los params al armar la URL.
            # Codificar acá también daría doble codificación.
            #
            # interpolate_structure, no interpolate, para que un query param
            # opcional sin argumento se omita en vez de reventar — mismo criterio
            # que en el body.
            params = {
                key: str(value)
                for key, value in interpolate_structure(
                    dict(action.request.query or {}), args, allow_slash_params=allow_slash
                ).items()
            }
            params.update(auth_params)
            params.update(self._pagination_params(action, args))
            request_headers = {
                **headers,
                **{
                    k: interpolate(str(v), args, position="raw")
                    for k, v in (action.request.headers or {}).items()
                },
            }
            body = (
                interpolate_structure(action.request.body, args, allow_slash_params=allow_slash)
                if action.request.body is not None
                else None
            )
            # El body entero era un placeholder sin argumento (`body: "{body}"`
            # en la integración http, llamada sin cuerpo): se manda sin body.
            if body is OMIT:
                body = None
        except InterpolationError as exc:
            return _fail(errors.BAD_REQUEST, str(exc))

        # El span lleva slug, acción y status. Nunca headers, body ni credencial:
        # los spans se persisten y este es el mismo camino que la traza de tools.
        tracing = TracingContext(agent_name="", session_id="")
        span = tracing.start_span(
            "integration.call",
            {"integration.slug": manifest.slug, "integration.action": action.name},
        )
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    action.request.method,
                    f"{base_url}{path}",
                    params=params,
                    headers=request_headers,
                    json=body,
                )
        # Ídem: httpx puede levantar por red, DNS, TLS o timeout. `tool_fn`
        # re-lanza lo que reciba, así que nada puede salir de acá como excepción.
        except Exception as exc:  # noqa: BLE001
            span.set_attribute("error_kind", errors.classify_exception(exc))
            tracing.finish_span(span, status=SpanStatus.ERROR)
            logger.warning("%s.%s falló: %s", manifest.slug, action.name, exc)
            return _fail(errors.classify_exception(exc), f"{type(exc).__name__}: {exc}")

        span.set_attribute("http.status_code", response.status_code)
        if response.status_code >= 400:
            span.set_attribute("error_kind", errors.classify_status(response.status_code))
            tracing.finish_span(span, status=SpanStatus.ERROR)
        else:
            tracing.finish_span(span)
        return self._to_result(action, response, args)

    @staticmethod
    def _pagination_params(action: ActionSpec, args: dict) -> dict:
        """Traduce el `cursor` uniforme de la tool al dialecto del proveedor.

        El modelo siempre ve un parámetro llamado `cursor`; cómo se llama en
        el cable lo decide el manifest. En estilo `offset` el cursor es el
        número de items ya consumidos.
        """
        pagination = action.pagination
        if pagination is None or pagination.cursor_in != "query":
            # cursor_in='body': el manifest lo coloca él mismo con `{cursor}`
            # dentro de `request.body`, y interpolate_structure lo omite solo
            # cuando no hay cursor.
            return {}
        params: dict = {}
        cursor = args.get("cursor")
        if pagination.style == "cursor":
            if cursor:
                params[pagination.cursor_param] = str(cursor)
            return params
        if cursor:
            params[pagination.offset_param] = str(cursor)
        if pagination.limit_param and args.get("limit") is not None:
            params[pagination.limit_param] = str(args["limit"])
        return params

    @staticmethod
    def _next_cursor(action: ActionSpec, payload, data, args: dict) -> str | None:
        """Cursor de la página siguiente, o None si no hay más.

        Estilo `cursor`: sale del payload. Estilo `offset`: se calcula
        sumando lo devuelto a lo ya consumido; una página vacía es el final.
        """
        pagination = action.pagination
        if pagination is None:
            return None
        if pagination.style == "cursor":
            value = _select(payload, pagination.cursor_path) if isinstance(payload, dict) else None
            return str(value) if value else None
        if not isinstance(data, list) or not data:
            return None
        try:
            consumed = int(args.get("cursor") or 0)
        except (TypeError, ValueError):
            consumed = 0
        return str(consumed + len(data))

    @staticmethod
    def _render_path(template: str, args: dict, allow_slash: set[str]) -> str:
        """Interpola el path segmento a segmento para respetar allow_slash por parámetro."""

        def _replace(match: re.Match) -> str:
            param = match.group(1)
            return interpolate(
                "{" + param + "}", args, position="path", allow_slash=param in allow_slash
            )

        return _PLACEHOLDER.sub(_replace, template)

    @staticmethod
    def _to_result(action: ActionSpec, response: httpx.Response, args: dict) -> ToolResult:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text

        if response.status_code >= 400:
            kind = errors.classify_status(response.status_code)
            metadata = {"error_kind": kind, "status_code": response.status_code}
            if kind == errors.RATE_LIMITED:
                metadata["retry_after"] = errors.retry_after_seconds(response.headers)
            return ToolResult(
                success=False,
                data=None,
                error=f"HTTP {response.status_code}: {str(payload)[:500]}",
                metadata=metadata,
            )

        metadata: dict = {"status_code": response.status_code}
        # `select` sólo navega mappings. Un payload de texto (o una lista suelta) se
        # devuelve tal cual: navegarlo daría None y se comería la respuesta entera.
        data = (
            _select(payload, action.response.select)
            if action.response and isinstance(payload, dict)
            else payload
        )
        if action.pagination is not None:
            metadata["next_cursor"] = HttpActionExecutor._next_cursor(action, payload, data, args)
        return ToolResult(success=True, data=data, metadata=metadata)
