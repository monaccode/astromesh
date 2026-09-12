"""`spec.prefetch`: búsquedas de solo lectura que corren antes del LLM.

Un turno que siempre empieza buscando lo mismo (quién escribe, qué está
pendiente) gasta un viaje al LLM por búsqueda sólo para decidir hacerla, y la
búsqueda en sí cuesta milisegundos. Este bloque las corre antes y deja el
resultado en la variable `prefetch` del prompt.

Sólo lecturas: una acción de integración con `request.method: GET` que no esté
en `confirm`. Una declaración inválida NO carga el agente —a diferencia del
resto del spec, que avisa y sigue—: un prefetch salteado en silencio deja al
modelo sin los datos, y el síntoma sería negarle el acceso a alguien que sí está.
"""

from jinja2 import TemplateError

from astromesh.core.tools import ToolType
from astromesh.errors import AgentConfigError
from astromesh.observability.tracing import SpanStatus


def validar_prefetch(agente, declarado, tools, *, prompt_engine):
    """Las entradas normalizadas de `spec.prefetch`, o `[]` si no hay bloque."""
    if declarado is None:
        return []
    if not isinstance(declarado, list):
        raise AgentConfigError(f"agent {agente!r}: spec.prefetch tiene que ser una lista")

    vistos = set()
    entradas = []
    for i, entrada in enumerate(declarado):
        donde = f"agent {agente!r}: spec.prefetch[{i}]"
        if not isinstance(entrada, dict):
            raise AgentConfigError(f"{donde} tiene que ser un objeto")
        nombre = entrada.get("name")
        if not isinstance(nombre, str) or not nombre:
            raise AgentConfigError(f"{donde} no tiene `name`")
        if nombre in vistos:
            raise AgentConfigError(f"{donde} repite el name {nombre!r}")
        vistos.add(nombre)

        tool = entrada.get("tool")
        definicion = tools.get(tool) if isinstance(tool, str) else None
        if definicion is None:
            raise AgentConfigError(
                f"{donde} ({nombre!r}) usa la tool {tool!r}, que el agente no tiene registrada"
            )
        if definicion.tool_type != ToolType.INTEGRATION:
            raise AgentConfigError(
                f"{donde} ({nombre!r}): {tool!r} no es una acción de integración"
            )
        accion = (definicion.integration_config or {}).get("action_spec")
        metodo = getattr(getattr(accion, "request", None), "method", None)
        if metodo != "GET":
            raise AgentConfigError(
                f"{donde} ({nombre!r}): {tool!r} es {metodo}; prefetch sólo corre lecturas (GET)"
            )
        if definicion.needs_confirmation:
            raise AgentConfigError(f"{donde} ({nombre!r}): {tool!r} está en confirm")

        argumentos = entrada.get("arguments") or {}
        if not isinstance(argumentos, dict):
            raise AgentConfigError(f"{donde} ({nombre!r}): `arguments` tiene que ser un objeto")
        when = entrada.get("when")
        if when is not None and not isinstance(when, str):
            raise AgentConfigError(f"{donde} ({nombre!r}): `when` tiene que ser un string")

        # Un `when` o un `arguments` que no parsean matan TODOS los turnos del
        # agente en runtime (ejecutar_prefetch los evalúa recién ahí) — se
        # compilan acá, sin evaluar, para que ese error aparezca al cargar y
        # no en el primer mensaje real. `prefetch.x` no existe todavía en este
        # punto y eso es esperado: compilar no lee variables.
        if when is not None:
            try:
                prompt_engine.compile_expression(when)
            except TemplateError as exc:
                raise AgentConfigError(
                    f"{donde} ({nombre!r}): `when` no es una expresión Jinja válida: {exc}"
                ) from exc
        for clave, valor in argumentos.items():
            if not isinstance(valor, str):
                continue
            try:
                prompt_engine.compile_template(valor)
            except TemplateError as exc:
                raise AgentConfigError(
                    f"{donde} ({nombre!r}): `arguments.{clave}` no es un template Jinja "
                    f"válido: {exc}"
                ) from exc

        entradas.append({"name": nombre, "tool": tool, "arguments": argumentos, "when": when})
    return entradas


_TRUNCAR = 5_000


async def ejecutar_prefetch(
    entradas, *, tools, prompt_engine, context, tool_context, tracing, parent_span_id
):
    """Corre las entradas en orden y devuelve `{name: resultado}`.

    Cada entrada ve el contexto de la corrida y lo que ya dejaron las
    anteriores. Una búsqueda que falla no tumba la corrida: queda
    `{success: False, ...}` y el modelo conserva sus tools para buscar solo.
    """
    resultados = {}
    for entrada in entradas:
        variables = {**(context or {}), "prefetch": resultados}

        # `when` compiló al cargar (validar_prefetch), pero evaluarlo puede
        # seguir fallando en runtime — depende de datos, p.ej. divide por
        # cero. Ese error entra al MISMO try que la tool: degrada igual que
        # una búsqueda fallida. Un `when` falso, en cambio, sigue siendo un
        # `continue` que no abre span ni el turno.
        span = None
        estado = SpanStatus.OK
        try:
            if entrada["when"] is not None and not prompt_engine.evaluate(
                entrada["when"], variables
            ):
                continue
            span = tracing.start_span(
                "tool.prefetch", {"tool": entrada["tool"]}, parent_span_id=parent_span_id
            )
            argumentos = {
                clave: prompt_engine.render(valor, variables) if isinstance(valor, str) else valor
                for clave, valor in entrada["arguments"].items()
            }
            span.set_attribute("tool_args", argumentos)
            resultado = await tools.execute(entrada["tool"], argumentos, tool_context)
        except Exception as exc:  # noqa: BLE001 — un `when` roto o una lectura fallida no tumban el turno
            resultado = {"success": False, "data": None, "metadata": {}, "error": str(exc)}
            if span is not None:
                span.set_attribute("error_message", str(exc))
            estado = SpanStatus.ERROR
        if span is not None:
            span.set_attribute("tool_result", str(resultado)[:_TRUNCAR])
            tracing.finish_span(span, status=estado)
        resultados[entrada["name"]] = resultado
    return resultados
