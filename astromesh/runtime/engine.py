import json
import logging
import os
import uuid
from pathlib import Path

import yaml

from astromesh.chain.compiler import chain_workflow_name, compile_chain
from astromesh.chain.output import build_data, normalize_output_schema, schema_prompt_block
from astromesh.core.memory import MemoryManager
from astromesh.core.model_router import ModelRouter
from astromesh.core.prompt_engine import PromptEngine
from astromesh.core.schema import InvalidToolParameters, normalize_tool_parameters
from astromesh.core.tools import ToolRegistry
from astromesh.errors import AgentConfigError
from astromesh.integrations import default_catalog
from astromesh.integrations.credentials import CredentialResolver
from astromesh.memory.factory import build_conversation_backend
from astromesh.orchestration.patterns import (
    ParallelFanOutPattern,
    PipelinePattern,
    PlanAndExecutePattern,
    ReActPattern,
)
from astromesh.orchestration.supervisor import SupervisorPattern
from astromesh.orchestration.swarm import SwarmPattern
from astromesh.runtime.confirmacion import Pendientes, huella
from astromesh.runtime.prefetch import ejecutar_prefetch, validar_prefetch
from astromesh.runtime.provider_registry import load_provider_registry, resolve_block

logger = logging.getLogger(__name__)

# Colores del DFS que detecta ciclos entre agentes: sin visitar / en la pila / cerrado.
_WHITE, _GRAY, _BLACK = 0, 1, 2

# Compartida por proceso: el gate tiene que ver lo que propuso la corrida
# anterior de la misma sesión, y cada corrida arma su propio engine.
_PENDIENTES = Pendientes()


def _emit(on_event, event: dict) -> None:
    """Hand one event to the caller's observer, if there is one.

    An observer that raises is logged and ignored: watching a run must never be
    able to break it. This mirrors ChannelEventBus.emit(), which likewise
    swallows a subscriber's failure rather than propagating it into the producer.
    """
    if on_event is None:
        return
    try:
        on_event(event)
    except Exception:
        logger.exception("on_event callback raised; ignoring")


def _agent_disk_persist_enabled() -> bool:
    return os.environ.get("ASTROMESH_PERSIST_AGENTS", "1").lower() not in (
        "0",
        "false",
        "no",
    )


def _validate_agent_filesystem_name(name: str) -> None:
    if not name or not isinstance(name, str):
        raise ValueError("Invalid agent name")
    if name != Path(name).name or ".." in name:
        raise ValueError("Invalid agent name")


def _make_builtin_handler(tool_instance, agent_name, rag_pipeline=None):
    """Create an async handler closure for a builtin tool instance.

    Sólo la mitad *del agente* del ToolContext se puede cerrar acá: esta clausura
    se arma una vez al cargar el agente y la comparten todas las corridas y todas
    las sesiones. Lo que varía por corrida (la sesión, y los secretos que la
    corrida trae) llega en `_run_context` al momento de la llamada — ver
    `ToolRegistry.execute`. Antes se pasaba `session_id=""` fijo, que era eso
    mismo pero resuelto mal: ninguna builtin tool podía saber en qué sesión
    estaba.
    """

    async def _handler(_run_context=None, **arguments):
        from astromesh.tools.base import ToolContext

        run = _run_context or {}
        ctx = ToolContext(
            agent_name=agent_name,
            session_id=run.get("session", ""),
            trace_span=None,
            secrets=run.get("secrets") or {},
        )
        ctx.rag_pipeline = rag_pipeline
        result = await tool_instance.execute(arguments, ctx)
        return result.to_dict()

    # Marca de opt-in: `register_internal` la usan también handlers ajenos con
    # firmas arbitrarias, y pasarles un kwarg que no declaran los rompería.
    _handler.wants_run_context = True
    return _handler


def _public_caller_context(context: dict | None) -> dict:
    """El subconjunto del context del llamador que un patrón puede ver.

    Las claves con prefijo `_` son **reservadas del runtime** por convención
    (`_provider_override`, `_history_messages`): describen cómo ejecutar la
    corrida, no son parámetros de la invocación, y ningún patrón tiene por qué
    leerlas.

    Filtrarlas no es cosmética, es la invariante que ya declara `tool_fn` más
    abajo — «los args se persisten en la traza y una credencial ahí quedaría
    escrita en disco». `_provider_override` trae la API key del header
    `X-Astromesh-Provider-Key`: si viajara dentro de `_caller_context`, un
    programa Glyph que hiciera `f(v=context)` la mandaría a `tool_args` y la
    traza la escribiría en disco, y un `ask("...", context=context)` la
    serializaría al proveedor del modelo.
    """
    if not isinstance(context, dict):
        return {}
    return {k: v for k, v in context.items() if not k.startswith("_")}


def _truncate(text: str | None, limit: int) -> str:
    """Truncate text to limit chars, appending a marker if truncated."""
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated at {len(text)} chars]"


# Las claves que CADA tipo de tool lee de verdad en `_build_agent`. Lo que no
# está acá se ignora en silencio, y ese silencio ya costó un release: la
# plantilla de CLARUS declaró `confirm` contra un runtime 0.32.0 que no lo
# conocía, el pod arrancó feliz, y la escritura al ERP siguió sin gatear hasta
# que alguien entró al pod a mirar.
#
# `confirm` va en las comunes A PROPÓSITO aunque sólo lo lea `integration`: mal
# puesto ya tiene su propio warning más abajo, que además explica por qué no
# gatea. Reportarlo dos veces taparía el bueno.
_CLAVES_COMUNES = frozenset({"type", "name", "confirm"})
_CLAVES_POR_TIPO: dict[str, frozenset[str]] = {
    "builtin": frozenset({"config", "rate_limit"}),
    "agent": frozenset({"agent", "description", "parameters", "context_transform"}),
    "client": frozenset({"description", "parameters", "rate_limit"}),
    # `description` NO está: `register_integration_tool` usa la del manifiesto
    # de la integración (`core/tools.py:178`), no la del YAML.
    "integration": frozenset({"connection", "actions", "rate_limit"}),
}


def claves_ignoradas(tool_def: dict) -> list[str]:
    """Las claves de un tool_def que este runtime NO va a leer, ordenadas.

    Devuelve vacío para un tipo no soportado: esa tool ya se descarta entera con
    su propio warning al final del loop, que además nombra los tipos válidos.
    """
    conocidas = _CLAVES_POR_TIPO.get(tool_def.get("type", "internal"))
    if conocidas is None:
        return []
    return sorted(set(tool_def) - _CLAVES_COMUNES - conocidas)


def _aviso_confirmacion(tool_name: str, argumentos: dict) -> str:
    """La frase que le dice a la persona qué va a pasar si confirma.

    La escribe el runtime, nunca el modelo — es la pieza que cierra el bypass
    de "el modelo le pregunta una cosa a la persona y usa el sí para otra":
    lo que la persona lee acá es, por construcción, lo mismo que `tool_fn` va
    a ejecutar si responde que sí.

    Los argumentos se listan `clave: valor` en vez de volcar el dict crudo:
    un `{'monto': 999999}` con comillas y llaves es ruido en un chat de
    WhatsApp.

    El orden de inserción del dict lo controla el MODELO — es él quien arma
    `arguments` para la tool call. Truncar el string ya renderizado (como
    hacía la versión anterior) dejaba que un argumento de texto libre puesto
    primero se comiera el resto: `_aviso_confirmacion('praxis_crear_record',
    {'nota': 'x'*480, 'monto': 999999})` cortaba antes de llegar a `monto`.
    Eso convierte el aviso en algo que el modelo puede curar en vez de un
    disclosure real. Por eso se ordenan las claves (alfabético, no depende
    del modelo) y se trunca CADA VALOR por separado con un tope chico: así
    toda clave aparece siempre, con una porción acotada de su valor. 80 chars
    alcanza para leer un monto, un ID o el arranque de un texto libre sin que
    un solo argumento gigante tape a los demás; el corte de 500 en el total
    ya no hace falta con el tope por valor.

    Dos límites que este aviso NO cierra, a propósito:
    - Si la corrida lanza DESPUÉS de que `tool_fn` registró el pendiente, el
      bloque que arma este aviso nunca se ejecuta (vive después del loop del
      agente) y el `finally` que envuelve la corrida no toca pendientes en
      `ok=False`. El pendiente sobrevive sin que nadie lo haya mostrado, y un
      "si" en el próximo turno lo ejecutaría. Acotado en la práctica — ese
      turno fallido no se persiste, así que el modelo tendría que rearmar los
      mismos argumentos de memoria — pero real.
    - La garantía de esta función es "se redactó", no "le llegó a la
      persona": si el envío por el canal (WhatsApp, etc.) falla después de
      que `result["answer"]` ya lleva el aviso, quien recibe el error no vio
      el detalle, y el pendiente sigue vivo para el próximo turno.
    """
    claves = sorted((argumentos or {}).keys())
    partes = ", ".join(f"{k}: {_truncate(str(argumentos[k]), 80)}" for k in claves)
    detalle = f"{tool_name} con {partes}" if partes else tool_name
    return f"Para confirmar respondé SI. Voy a ejecutar: {detalle}"


def _parse_args(args):
    """Parse arguments that may be a JSON string (OpenAI) or already a dict."""
    if isinstance(args, str):
        try:
            return json.loads(args)
        except (json.JSONDecodeError, ValueError):
            return {"_raw": args}
    return args


def _normalize_tool_calls(raw_calls: list) -> list[dict]:
    """Normalize tool_calls to plain JSON-serializable dicts."""
    normalized = []
    for tc in raw_calls:
        if isinstance(tc, dict):
            if "function" in tc:
                normalized.append(
                    {
                        "id": tc.get("id"),
                        "name": tc["function"]["name"],
                        "arguments": _parse_args(tc["function"].get("arguments", {})),
                    }
                )
            else:
                normalized.append(tc)
        else:
            normalized.append({"raw": str(tc)})
    return normalized


# Keys each source's wiring below actually reads. Anything else an agent
# declares is dropped on the floor, which is how the `timeout` and `parameters`
# bugs survived 35 releases: the schema accepted them and nobody said a word.
# `temperature`/`max_tokens` are the documented top-level shorthand, folded into
# `parameters` by _model_parameters() for the sources that take parameters.
_SELECTOR_KEYS = frozenset({"source", "provider", "model", "providerRef"})
_SHORTHAND_KEYS = ("temperature", "max_tokens")
_PARAMETER_KEYS = frozenset({"parameters", "timeout", *_SHORTHAND_KEYS})
_CONSUMED_KEYS: dict[str, frozenset[str]] = {
    "ollama": _SELECTOR_KEYS | _PARAMETER_KEYS | {"endpoint"},
    "openai_compat": _SELECTOR_KEYS | _PARAMETER_KEYS | {"endpoint", "api_key", "api_key_env"},
    "litellm": _SELECTOR_KEYS | _PARAMETER_KEYS | {"api_key", "api_key_env"},
    "centinela": _SELECTOR_KEYS
    | {
        "endpoint",
        "endpoint_name",
        "api_key",
        "api_key_env",
        "contract",
        "invalid_policy",
        "max_retries",
    },
}
_CONSUMED_KEYS["openai"] = _CONSUMED_KEYS["openai_compat"]
_CONSUMED_KEYS["azure_openai"] = _CONSUMED_KEYS["openai_compat"]


def _model_parameters(block: dict) -> dict | None:
    """Merge the top-level `temperature`/`max_tokens` shorthand into `parameters`.

    The agent schema documents both as "top-level shorthand for
    parameters.<name>", but nothing ever read them. An explicit entry under
    `parameters` wins over the shorthand.
    """
    params = dict(block.get("parameters") or {})
    for key in _SHORTHAND_KEYS:
        if block.get(key) is not None:
            params.setdefault(key, block[key])
    return params or None


def _warn_unconsumed_keys(block: dict, source: str) -> None:
    """Warn about keys this source's wiring will ignore.

    Only non-None values count: resolve_block() injects endpoint/contract/... as
    None for every source, and warning on those would fire for every providerRef
    block and teach everyone to tune the warning out.
    """
    consumed = _CONSUMED_KEYS.get(source)
    if consumed is None:
        return
    ignored = sorted(k for k, v in block.items() if v is not None and k not in consumed)
    if ignored:
        logger.warning(
            "model block for source %r declares %s, which this source does not use; "
            "the value(s) will be ignored",
            source,
            ", ".join(repr(k) for k in ignored),
        )


def build_candidate_provider(block: dict):
    """Build a provider instance from a candidate/legacy block.

    Accepts `source` (new) or `provider` (legacy) to select the adapter. When
    neither is set, infers `litellm` for prefixed models (contain '/') and
    `openai_compat` otherwise. Returns None for unknown sources, and also for
    `litellm` when the optional `litellm` dependency is not installed (probed
    eagerly here so registration fails loudly instead of only at `complete()`).
    """
    from astromesh.providers.ollama_provider import OllamaProvider
    from astromesh.providers.openai_compat import OpenAICompatProvider

    source = (block.get("source") or block.get("provider") or "").strip().lower()
    model = block.get("model", "")
    if not source:
        source = "litellm" if "/" in model else "openai_compat"

    _warn_unconsumed_keys(block, source)

    if source == "ollama":
        base = (block.get("endpoint") or "http://localhost:11434").rstrip("/")
        return OllamaProvider(
            config={
                "base_url": base,
                "model": model or "llama3",
                "parameters": _model_parameters(block),
                "timeout": float(block.get("timeout", 120)),
            }
        )
    if source in ("openai_compat", "openai", "azure_openai"):
        base = (block.get("endpoint") or "https://api.openai.com/v1").rstrip("/")
        return OpenAICompatProvider(
            config={
                "base_url": base,
                "model": model or "gpt-4o-mini",
                "api_key_env": block.get("api_key_env", "OPENAI_API_KEY"),
                "api_key": block.get("api_key"),
                "parameters": _model_parameters(block),
                "timeout": float(block.get("timeout", 120)),
            }
        )
    if source == "litellm":
        from astromesh.providers import litellm_provider as _llm

        try:
            _llm._import_litellm()
        except Exception:  # noqa: BLE001  (best-effort: este camino nunca puede levantar)
            logger.warning(
                "litellm not installed; skipping candidate model %r (install the 'litellm' extra)",
                model,
            )
            return None
        return _llm.LiteLLMProvider(
            config={
                "model": model or "gpt-4o",
                "api_key": block.get("api_key"),
                "api_key_env": block.get("api_key_env"),
                "parameters": _model_parameters(block),
                "timeout": float(block.get("timeout", 120)),
            }
        )
    if source == "centinela":
        from astromesh.providers.centinela import CentinelaProvider

        return CentinelaProvider(
            config={
                "endpoint": block.get("endpoint"),
                "endpoint_name": block.get("endpoint_name"),
                "api_key": block.get("api_key"),
                "api_key_env": block.get("api_key_env"),
                "model": model or "centinela",
                "contract": block.get("contract") or {},
                "invalid_policy": block.get("invalid_policy", "mark"),
                "max_retries": int(block.get("max_retries", 1)),
            }
        )
    return None


class AgentRuntime:
    def __init__(
        self,
        config_dir="./config",
        service_manager=None,
        peer_client=None,
        observability=None,
    ):
        self._config_dir = Path(config_dir)
        self._provider_registry = load_provider_registry(self._config_dir)
        self._rag_specs = {}
        self._agents: dict[str, Agent] = {}
        self._agent_status: dict[str, str] = {}
        # Por qué un agente quedó en `draft` al arrancar. El log lo dice, pero el
        # log no lo ve quien consulta la API: sin esto, un `spec.program` que no
        # compila se manifiesta como un 404 en el primer run y nada más.
        self._agent_errors: dict[str, str] = {}
        self._agent_configs: dict[str, dict] = {}
        self._compiled_chains: dict[str, object] = {}
        self._prompt_engine = PromptEngine()
        self.service_manager = service_manager
        self.peer_client = peer_client
        self._observability = observability or {}

    async def bootstrap(self):
        # Wire OTLP export FIRST: the early returns below must not leave a deployment untraced.
        # Imported lazily — the module pulls in the traces route (FastAPI) on the enabled path.
        from astromesh.observability.setup import setup_observability

        setup_observability(self._observability)

        # Skip agent loading if agents service is disabled
        if self.service_manager and not self.service_manager.is_enabled("agents"):
            return
        # RAG antes de la salida temprana: un runtime que se administra por API arranca
        # sin agentes en disco, y hasta v0.35.1 eso lo dejaba con _rag_specs vacío para
        # siempre — los agentes registrados después no podían resolver su base de
        # conocimiento. load_all() ya tolera un directorio inexistente.
        from astromesh.rag.loader import RAGPipelineLoader

        self._rag_specs = RAGPipelineLoader(str(self._config_dir / "rag")).load_all()

        agents_dir = self._config_dir / "agents"
        if not agents_dir.exists():
            return
        configs = [yaml.safe_load(f.read_text()) for f in agents_dir.glob("*.agent.yaml")]
        self._detect_circular_refs(configs)
        for config in configs:
            name = config.get("metadata", {}).get("name", "<unknown>")
            try:
                agent = self._build_agent(config)
            except Exception as exc:
                logger.exception("Skipping agent %s: failed to build from config", name)
                if name and name != "<unknown>":
                    self._agent_configs[name] = config
                    self._agent_status[name] = "draft"
                    # El motivo sobrevive al log: `GET /v1/agents` lo devuelve y
                    # `deploy` lo vuelve a producir con el mensaje del compilador.
                    self._agent_errors[name] = f"{type(exc).__name__}: {exc}"
                continue
            self._agents[agent.name] = agent
            self._agent_configs[name] = config
            self._agent_status[name] = "deployed"
            self._agent_errors.pop(name, None)

        self._compile_chains()

    def _compile_chains(self) -> None:
        """Compila la cadena de cada agente que declare `spec.chain`.

        Deliberadamente NO se atrapa la excepción: un ciclo, un max_depth excedido
        o un agente inexistente tienen que impedir el arranque, con la ruta en el
        mensaje. Descubrirlo a mitad de una corrida en producción sería peor.
        """
        self._compiled_chains = {}
        for name in self._agent_configs:
            wf = compile_chain(name, self._agent_configs)
            if wf is not None:
                self._compiled_chains[chain_workflow_name(name)] = wf

    def has_chain(self, agent_name: str) -> bool:
        return chain_workflow_name(agent_name) in self._compiled_chains

    @property
    def agent_configs(self) -> dict:
        """Configs crudos de los agentes; los usa la ruta para leer `spec.chain`."""
        return self._agent_configs

    def compiled_chains(self) -> dict:
        """{nombre de workflow: WorkflowSpec} de las cadenas compiladas."""
        return dict(self._compiled_chains)

    def _detect_circular_refs(self, configs: list[dict]):
        """Detect circular agent-as-tool references. Raises ValueError if cycle found."""
        # Build adjacency list
        graph: dict[str, list[str]] = {}
        for config in configs:
            name = config["metadata"]["name"]
            agent_tools = [
                t["agent"] for t in config["spec"].get("tools", []) if t.get("type") == "agent"
            ]
            graph[name] = agent_tools

        # DFS cycle detection
        color = dict.fromkeys(graph, _WHITE)

        def dfs(node, path):
            color[node] = _GRAY
            for neighbor in graph.get(node, []):
                if neighbor not in color:
                    continue  # references external agent, skip
                if color[neighbor] == _GRAY:
                    cycle = [*path, neighbor]
                    raise ValueError(f"Circular agent reference detected: {' -> '.join(cycle)}")
                if color[neighbor] == _WHITE:
                    dfs(neighbor, [*path, neighbor])
            color[node] = _BLACK

        for node in graph:
            if color[node] == _WHITE:
                dfs(node, [node])

    def _normalize_model_spec(self, model_spec: dict) -> dict[str, dict]:
        """Normalize legacy and new model schemas into {role: {candidates, strategy}}.

        Always returns a 'default' role. Legacy primary/fallback/extra/routing
        collapse into 'default'; the new schema uses model.default + model.roles.
        """
        roles: dict[str, dict] = {}

        # New schema
        if "default" in model_spec or "roles" in model_spec:
            default_block = model_spec.get("default") or {}
            roles["default"] = {
                "candidates": list(default_block.get("candidates", [])),
                "strategy": default_block.get("strategy", "cost_optimized"),
            }
            for name, block in (model_spec.get("roles") or {}).items():
                if name == "default":
                    continue
                roles[str(name)] = {
                    "candidates": list((block or {}).get("candidates", [])),
                    "strategy": (block or {}).get("strategy", "cost_optimized"),
                }
            return roles

        # Legacy schema → single 'default' role
        candidates: list[dict] = []
        for slot in ("primary", "fallback"):
            block = model_spec.get(slot)
            if isinstance(block, dict) and (block.get("provider") or block.get("source")):
                candidates.append(block)
        extras = model_spec.get("extra")
        if isinstance(extras, dict):
            candidates.extend(
                block
                for block in extras.values()
                if isinstance(block, dict) and (block.get("provider") or block.get("source"))
            )
        strategy = (model_spec.get("routing") or {}).get("strategy", "cost_optimized")
        roles["default"] = {"candidates": candidates, "strategy": strategy}
        return roles

    @staticmethod
    def _conversation_backend(nombre: str, memory_spec: dict):
        """El backend conversacional del agente, o None si no declara memoria.

        Un backend que el factory no sabe construir degrada a SIN MEMORIA con
        un warning, en vez de tirar: es el mismo criterio que las claves de más
        en una tool unas líneas más abajo — una parte del manifiesto que este
        runtime no entiende no vuelve inválido al agente entero, pero el
        operador tiene que poder verlo en el log del pod sin entrar a la base.

        Hoy `build_conversation_backend` sólo construye `redis`
        (`astromesh/memory/factory.py:23-30`), y el `agent.schema.json` de este
        repo todavía anuncia `sqlite`, `postgres` e `in_memory`: hasta que el
        factory los implemente, declararlos cae por acá.
        """
        conv = (memory_spec or {}).get("conversational")
        if not conv:
            return None
        try:
            return build_conversation_backend(conv)
        except ValueError as err:
            logger.warning(
                "agent %r declara memoria conversacional con backend %r que este "
                "runtime no construye (%s): va a correr SIN memoria y se vuelve a "
                "presentar en cada mensaje.",
                nombre,
                conv.get("backend"),
                err,
            )
            return None
        except KeyError as err:
            # `redis` lee `connection.url` sin default: sin esa clave el
            # manifiesto revienta acá, no en la primera corrida.
            logger.warning(
                "agent %r declara memoria conversacional %r sin %s: va a correr SIN memoria.",
                nombre,
                conv.get("backend"),
                err,
            )
            return None
        except ImportError as err:
            # El backend es un EXTRA opcional (`astromesh[redis]`): esta build
            # no lo tiene instalado. Degradar y avisar, no dejar al agente en
            # `draft`: el resto de sus capacidades funciona perfectamente, y un
            # agente muerto por una dependencia de memoria es una falla mucho
            # más grande que un agente sin memoria. El mensaje nombra el extra
            # para que quien lea el log sepa qué instalar.
            logger.warning(
                "agent %r declara memoria conversacional %r y esta build no "
                "tiene el paquete (%s): instalá el extra correspondiente "
                "(p.ej. `astromesh[redis]`). Va a correr SIN memoria.",
                nombre,
                conv.get("backend"),
                err,
            )
            return None

    def _build_role_routers(self, model_spec: dict) -> dict[str, "ModelRouter"]:
        """Build one ModelRouter per role from the normalized spec."""
        roles = self._normalize_model_spec(model_spec)
        routers: dict[str, ModelRouter] = {}
        for role_name, cfg in roles.items():
            router = ModelRouter({"strategy": cfg.get("strategy", "cost_optimized")})
            registered = 0
            for i, raw_block in enumerate(cfg.get("candidates", [])):
                block = resolve_block(raw_block, self._provider_registry)
                try:
                    prov = build_candidate_provider(block)
                except Exception:
                    logger.exception("role %s candidate %d failed to build", role_name, i)
                    continue
                if prov is None:
                    logger.warning(
                        "role %s candidate %d (source %r) not registered; skipping",
                        role_name,
                        i,
                        block.get("source") or block.get("provider"),
                    )
                    continue
                router.register_provider(f"cand{i}", prov)
                registered += 1
            if registered == 0 and role_name != "default":
                logger.warning(
                    "role %s registered 0 providers; requests to it will fall back to 'default'",
                    role_name,
                )
                continue
            if registered == 0:
                logger.warning("role %s registered 0 providers", role_name)
            routers[role_name] = router
        if "default" not in routers:
            routers["default"] = ModelRouter({"strategy": "cost_optimized"})
        return routers

    def _resolve_rag(self, spec: dict):
        from astromesh.rag.agent_rag import AgentRAG
        from astromesh.rag.factory import build_pipeline

        knowledge = spec.get("knowledge") or {}
        name = knowledge.get("pipeline")
        if not name:
            return None
        rag_spec = self._rag_specs.get(name)
        if rag_spec is None:
            logger.warning("agent references unknown RAGPipeline '%s'; skipping KB", name)
            return None
        try:
            pipeline = build_pipeline(rag_spec)
        except Exception:
            logger.warning("failed to build RAGPipeline '%s'; skipping KB", name, exc_info=True)
            return None
        top_k = knowledge.get("top_k", rag_spec.retrieval.get("top_k", 5))
        return AgentRAG(pipeline, top_k=top_k)

    def _credential_resolver(self) -> CredentialResolver:
        """Un resolver por runtime; lee config/connections.yaml una sola vez."""
        if getattr(self, "_resolver", None) is None:
            self._resolver = CredentialResolver(self._config_dir / "connections.yaml")
        return self._resolver

    def _build_agent(self, config):
        spec = config["spec"]
        metadata = config["metadata"]
        # `confirm` y `spec.chain` no pueden convivir: un paso de chain corre
        # con `desde_humano=False` (`workflow/executor.py:_run_agent`) y ESO
        # es justamente lo que hace que un sub-agente nunca pueda
        # autoconfirmarse. Pero la misma propiedad que cierra ese bypass abre
        # otro: `desde_humano=False` nunca llama a `habilitar` NI a
        # `cerrar_si_confirmado`, así que un `tool_fn` que pide confirmación
        # ahí adentro registra un pendiente que NADA va a confirmar (falla
        # cerrado, sólo molesto) y NADA va a barrer jamás — el primer paso de
        # la cadena, además, recibe literalmente `{{ trigger.query }}`: el
        # texto de la persona, ni siquiera un "sí" que un modelo redactó. En
        # un pod con `replicas: 1` corriendo semanas, cada mensaje que pasa
        # por esa cadena deja una entrada en `_PENDIENTES` que no se libera
        # nunca. Rechazar accá, fuerte, es más barato que threadear el
        # session_id del trigger a través de la cadena (deuda aparte) o que
        # ponerle TTL/cap a `_PENDIENTES` (deuda aparte también) — y más
        # seguro que dejarlo andar en silencio.
        if spec.get("chain") and any(td.get("confirm") for td in spec.get("tools", [])):
            raise ValueError(
                f"agent {metadata['name']!r} declara spec.chain y confirm a la vez: "
                "un paso de chain corre con desde_humano=False y jamás puede "
                "confirmar, así que la propuesta queda pendiente para siempre — "
                "sacá confirm de sus tools o sacá spec.chain"
            )
        model_spec = spec.get("model", {})
        routers = self._build_role_routers(model_spec)
        memory_spec = spec.get("memory", {})
        # El backend conversacional se CONSTRUYE acá o no existe: sin esta
        # línea `MemoryManager._conversation` queda en None, y entonces
        # `build_context` y `persist_turn` no hacen nada
        # (`astromesh/core/memory.py:93,138`). El resultado es un agente que se
        # vuelve a presentar en cada mensaje, sin un error en ningún lado y con
        # los spans `memory_build`/`memory_persist` reportando `ok`.
        #
        # Medido con un agente de cobranzas sobre WhatsApp: encontraba la deuda
        # de la persona y al mensaje siguiente le volvía a pedir el teléfono,
        # con `memory.conversational` bien declarado en su manifiesto y Redis
        # arriba y alcanzable. La memoria conversacional era código muerto:
        # `build_conversation_backend` no lo llamaba NADIE.
        memory = MemoryManager(
            agent_id=metadata["name"],
            config=memory_spec,
            conversation=self._conversation_backend(metadata["name"], memory_spec),
        )
        rag = self._resolve_rag(spec)
        tools = ToolRegistry()
        from astromesh.tools import ToolLoader

        loader = ToolLoader()
        loader.auto_discover()
        for tool_def in spec.get("tools", []):
            tool_type = tool_def.get("type", "internal")
            if sobrantes := claves_ignoradas(tool_def):
                # Warning y no raise, por la misma razón que la rama del tipo no
                # soportado: una clave de más no vuelve inválido al resto del
                # agente, y degradarlo a 'draft' por eso sería desproporcionado.
                # Pero el operador tiene que poder verlo en el log del pod sin
                # entrar a la base.
                logger.warning(
                    "agent %r declara la tool %r con %s que este runtime no lee: %s. "
                    "Se ignoran. Si esperabas que hicieran algo, el runtime es viejo "
                    "para ese manifiesto.",
                    metadata["name"],
                    tool_def.get("name"),
                    "una clave" if len(sobrantes) == 1 else "claves",
                    ", ".join(sobrantes),
                )
            if tool_type != "integration" and tool_def.get("confirm"):
                # `confirm` sólo lo lee la rama `integration` (más abajo). En
                # cualquier otro tipo de tool es un permiso mal escrito que
                # nunca gatea nada — exactamente lo que la Global Constraint
                # pide no silenciar. No es un `raise` como el de la rama
                # `integration`: acá no sabemos si el resto del tool_def es
                # válido para ESE tipo, así que degradar a agente "draft" por
                # un campo de más sería desproporcionado — pero el operador
                # tiene que enterarse.
                logger.warning(
                    "agent %r declara confirm=%r en la tool %r de tipo %r, que no es "
                    "'integration' — se ignora, esa tool nunca va a pedir confirmación.",
                    metadata["name"],
                    tool_def.get("confirm"),
                    tool_def.get("name"),
                    tool_type,
                )
            if tool_type == "builtin":
                instance = loader.create(tool_def["name"], config=tool_def.get("config"))
                handler = _make_builtin_handler(
                    instance, metadata["name"], rag_pipeline=(rag.pipeline if rag else None)
                )
                tools.register_internal(
                    name=tool_def["name"],
                    handler=handler,
                    description=instance.description,
                    parameters=instance.parameters,
                    rate_limit=tool_def.get("rate_limit"),
                )
            elif tool_type == "agent":
                tools.register_agent_tool(
                    name=tool_def["name"],
                    agent_name=tool_def["agent"],
                    description=tool_def.get(
                        "description",
                        f"Invoke agent '{tool_def['agent']}'",
                    ),
                    parameters=tool_def.get("parameters"),
                    context_transform=tool_def.get("context_transform"),
                )
                tools.set_runtime(self)
            elif tool_type == "client":
                try:
                    normalized_parameters = normalize_tool_parameters(tool_def.get("parameters"))
                except InvalidToolParameters as exc:
                    # Same warn-don't-break stance as the unsupported-type branch below:
                    # a malformed 'parameters' block on one tool must not degrade the
                    # whole agent to 'draft'. Names the agent, the tool, and what was
                    # wrong, then skips just this tool.
                    logger.warning(
                        "agent %r declares tool %r with parameters of type %r — "
                        "expected a mapping (YAML shorthand or JSON Schema), ignoring it.",
                        metadata["name"],
                        tool_def.get("name"),
                        exc.actual_type,
                    )
                    continue
                tools.register_client_tool(
                    name=tool_def["name"],
                    description=tool_def.get("description", ""),
                    parameters=normalized_parameters,
                    rate_limit=tool_def.get("rate_limit"),
                )
            elif tool_type == "integration":
                slug = tool_def.get("name")
                integration = default_catalog().get(slug)
                if integration is None:
                    logger.warning(
                        "agent %r declara la integración %r, que no existe en el catálogo — "
                        "se ignora.",
                        metadata["name"],
                        slug,
                    )
                    continue
                connection = tool_def.get("connection")
                if not connection:
                    logger.warning(
                        "agent %r declara la integración %r sin 'connection' — se ignora.",
                        metadata["name"],
                        slug,
                    )
                    continue
                action_names = tool_def.get("actions")
                # `confirm` es un SUBCONJUNTO de `actions`. Nombrar algo que el
                # agente no puede llamar es un error de configuración, y acá se
                # rechaza en vez de ignorarse: el resto de esta rama tolera lo
                # malformado con un warning porque una integración rota no debe
                # tumbar al agente, pero un permiso mal escrito es lo contrario
                # — silenciarlo dejaría al agente escribiendo sin confirmar.
                #
                # Va ANTES del `continue` de "sin actions": ese `continue`
                # corría primero y un `confirm` sin `actions` se caía con sólo
                # el warning genérico de abajo — el mismo permiso mal escrito
                # que esto existe para no silenciar.
                confirmables = set(tool_def.get("confirm") or [])
                if not action_names:
                    if confirmables:
                        raise ValueError(
                            f"agent {metadata['name']!r} declara confirm="
                            f"{sorted(confirmables)} en la integración {slug!r} sin "
                            "'actions' — ese permiso nunca puede cumplirse"
                        )
                    # La allowlist es obligatoria: exponer todas las acciones de varias
                    # integraciones infla el prompt y empeora la elección del modelo.
                    logger.warning(
                        "agent %r declara la integración %r sin 'actions' — la allowlist "
                        "es obligatoria, se ignora.",
                        metadata["name"],
                        slug,
                    )
                    continue
                fuera = confirmables - set(action_names)
                if fuera:
                    raise ValueError(
                        f"agent {metadata['name']!r} declara confirm={sorted(fuera)} "
                        f"en la integración {slug!r}, que no está en actions"
                    )
                resolver = self._credential_resolver()
                for action_name in action_names:
                    action = integration.action(action_name)
                    if action is None:
                        logger.warning(
                            "agent %r declara la acción %r de la integración %r, que no "
                            "existe — se ignora sólo esa acción.",
                            metadata["name"],
                            action_name,
                            slug,
                        )
                        continue
                    tools.register_integration_tool(
                        name=f"{integration.slug}_{action.name}",
                        manifest=integration,
                        action=action,
                        connection=connection,
                        resolver=resolver,
                        rate_limit=(
                            tool_def.get("rate_limit")
                            or action.rate_limit
                            or integration.defaults.rate_limit
                        ),
                        needs_confirmation=action.name in confirmables,
                    )
            else:
                # Until 0.35.0 this fell off the end of the chain in silence: the tool
                # was never registered, never reached the model, and nothing said so —
                # you got an agent with no tools and nothing to look at. 'internal' is
                # the default type, so a tool with no 'type' landed here too.
                # It warns rather than raises: raising would stop bootstrap() for every
                # existing YAML that declares one. The error comes in 1.0.
                logger.warning(
                    "agent %r declares tool %r with unsupported type %r — ignoring it. "
                    "YAML supports: builtin, agent, client, integration.",
                    metadata["name"],
                    tool_def.get("name"),
                    tool_type,
                )
        pattern = self._build_pattern(
            spec, tools.get_tool_schemas(spec.get("permissions", {}).get("allowed_actions"))
        )
        prompts = spec.get("prompts", {})
        for name, tmpl in prompts.get("templates", {}).items():
            self._prompt_engine.register_template(name, tmpl, scope=metadata["name"])
        # Después de registrar TODAS las tools: el prefetch nombra una por su
        # nombre registrado (`<slug>_<acción>`).
        prefetch = validar_prefetch(metadata["name"], spec.get("prefetch"), tools)
        return Agent(
            name=metadata["name"],
            version=metadata.get("version", "0.1.0"),
            namespace=metadata.get("namespace", "default"),
            description=spec.get("identity", {}).get("description", ""),
            routers=routers,
            memory=memory,
            tools=tools,
            pattern=pattern,
            system_prompt=prompts.get("system", ""),
            prompt_engine=self._prompt_engine,
            guardrails=spec.get("guardrails", {}),
            permissions=spec.get("permissions", {}),
            orchestration_config=spec.get("orchestration", {}),
            rag=rag,
            output_schema=normalize_output_schema(spec.get("output_schema")),
            prefetch=prefetch,
        )

    def _build_pattern(self, spec: dict, tool_schemas: list[dict] | None = None):
        """Instancia el patrón de orquestación declarado en el YAML.

        `glyph` se importa acá adentro y no arriba: `astromesh_glyph` es un extra
        opcional, y `astromesh/api/main.py` tiene que seguir importando sin extras
        o la imagen de astromesh-os no bootea.

        Cuando el spec trae `program`, se compila acá contra el catálogo de tools
        del agente. Un programa roto se convierte así en un fallo de despliegue con
        línea y mensaje, en vez de un error en la cara del primer cliente.
        """
        pattern_map = {
            "react": ReActPattern,
            "plan_and_execute": PlanAndExecutePattern,
            "parallel_fan_out": ParallelFanOutPattern,
            "pipeline": PipelinePattern,
            "supervisor": SupervisorPattern,
            "swarm": SwarmPattern,
        }
        pattern_name = spec.get("orchestration", {}).get("pattern", "react")
        program = spec.get("program")

        if program is not None and pattern_name != "glyph":
            raise AgentConfigError(
                f"el agente declara `program` pero su pattern es {pattern_name!r}: "
                "un programa Glyph sólo lo ejecuta `pattern: glyph`"
            )

        if pattern_name == "glyph":
            orchestration = spec.get("orchestration", {})
            try:
                glyph_pattern = _import_glyph_pattern(pattern_name)
            except ImportError as exc:
                if program is not None:
                    # Sin programa, caer a react es una degradación tolerable. Con
                    # programa NO lo es: el agente pasaría de cero llamadas al
                    # modelo a un ReAct completo —400x el costo, medido— y encima
                    # ignorando en silencio el programa que declara su YAML. Es
                    # exactamente el fallo silencioso que la decisión 2 del spec
                    # prohíbe, así que acá es un error de despliegue.
                    raise AgentConfigError(
                        "el agente declara `program` pero el extra `glyph` no está "
                        "instalado (dentro del monorepo: `uv sync --extra glyph`; el paquete "
                        "todavía no está en PyPI): un programa fijo "
                        "no puede degradarse a `react` sin cambiar el costo de la "
                        "corrida en dos órdenes de magnitud"
                    ) from exc
                logger.warning(
                    "el agente pide pattern=glyph pero el extra no está instalado "
                    "(dentro del monorepo: `uv sync --extra glyph`; el paquete todavía "
                    "no está en PyPI); se usa react",
                )
                return ReActPattern()

            if program is not None:
                # Compila para que un programa roto no cargue. La excepción sube:
                # es un error de configuración y tiene que ser ruidoso.
                _compile_glyph_program(program, tool_schemas or [])

            # `narrate: false` ahorra la segunda llamada al modelo devolviendo
            # el resultado del programa como JSON. Un agente que alimenta a
            # otro eslabón consume `output.data`, no prosa.
            return glyph_pattern(
                max_repairs=int(orchestration.get("max_repairs", 2)),
                narrate=bool(orchestration.get("narrate", True)),
                program=program,
            )

        return pattern_map.get(pattern_name, ReActPattern)()

    async def run(
        self,
        agent_name,
        query,
        session_id,
        context=None,
        parent_trace_id=None,
        on_event=None,
        connections=None,
        desde_humano: bool = True,
    ):
        agent = self._agents.get(agent_name)
        if not agent:
            raise ValueError(f"Agent '{agent_name}' not found")
        return await agent.run(
            query,
            session_id,
            context,
            parent_trace_id=parent_trace_id,
            on_event=on_event,
            connections=connections,
            desde_humano=desde_humano,
        )

    def agent_error(self, name: str) -> str | None:
        """Por qué `name` no pudo construirse, si es que falló al arrancar."""
        return self._agent_errors.get(name)

    def list_agents(self):
        result = []
        seen = set()
        # Include deployed agents from _agents
        for a in self._agents.values():
            result.append(
                {
                    "name": a.name,
                    "version": a.version,
                    "namespace": a.namespace,
                    "status": self._agent_status.get(a.name, "deployed"),
                }
            )
            seen.add(a.name)
        # Include non-deployed agents from _agent_configs
        for name, config in self._agent_configs.items():
            if name not in seen:
                metadata = config.get("metadata", {})
                entry = {
                    "name": name,
                    "version": metadata.get("version", "0.1.0"),
                    "namespace": metadata.get("namespace", "default"),
                    "status": self._agent_status.get(name, "draft"),
                }
                # Sólo cuando lo hay: un draft registrado por API todavía no se
                # intentó construir y no tiene nada que contar.
                if (error := self._agent_errors.get(name)) is not None:
                    entry["error"] = error
                result.append(entry)
        return result

    def _agent_yaml_path(self, name: str) -> Path:
        _validate_agent_filesystem_name(name)
        return self._config_dir / "agents" / f"{name}.agent.yaml"

    def _persist_agent_yaml(self, name: str, config: dict) -> None:
        if not _agent_disk_persist_enabled():
            return
        path = self._agent_yaml_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    def _remove_agent_yaml(self, name: str) -> None:
        if not _agent_disk_persist_enabled():
            return
        try:
            path = self._agent_yaml_path(name)
        except ValueError:
            return
        if path.is_file():
            path.unlink()

    async def register_agent(self, config: dict) -> None:
        """Register an agent dynamically from a config dict (same schema as YAML).
        Stores the config and sets status to 'draft' without building the agent.
        The agent must be explicitly deployed via deploy_agent()."""
        name = config.get("metadata", {}).get("name") or config.get("spec", {}).get(
            "identity", {}
        ).get("name")
        if not name:
            raise ValueError("Agent config must include metadata.name or spec.identity.name")
        self._agent_configs[name] = config
        self._agent_status[name] = "draft"
        self._persist_agent_yaml(name, config)

    async def deploy_agent(self, name: str) -> None:
        """Build and deploy a registered agent, making it available for execution."""
        if name not in self._agent_configs:
            raise ValueError(f"Agent '{name}' not found")
        config = self._agent_configs[name]
        agent = self._build_agent(config)
        self._agents[agent.name] = agent
        self._agent_status[name] = "deployed"
        self._agent_errors.pop(name, None)
        self._persist_agent_yaml(name, config)
        # Una cadena registrada en caliente tiene que quedar disponible sin reiniciar.
        self._compile_chains()

    def pause_agent(self, name: str) -> None:
        """Pause a deployed agent, removing it from active execution."""
        if self._agent_status.get(name) != "deployed":
            raise ValueError(f"Agent '{name}' is not deployed")
        if name in self._agents:
            del self._agents[name]
        self._agent_status[name] = "paused"

    async def update_agent(self, name: str, config: dict) -> None:
        """Update an agent's config. Pauses if deployed, resets status to draft."""
        if name not in self._agent_configs:
            raise ValueError(f"Agent '{name}' not found")
        if self._agent_status.get(name) == "deployed":
            self.pause_agent(name)
        self._agent_configs[name] = config
        self._agent_status[name] = "draft"
        self._persist_agent_yaml(name, config)

    def unregister_agent(self, name: str) -> None:
        """Remove a dynamically registered agent."""
        if name not in self._agents and name not in self._agent_configs:
            raise ValueError(f"Agent '{name}' not found")
        self._agents.pop(name, None)
        self._agent_configs.pop(name, None)
        self._agent_status.pop(name, None)
        self._agent_errors.pop(name, None)
        self._remove_agent_yaml(name)

    def register_rag_pipeline(self, raw: dict) -> str:
        """Registra (o reemplaza) un RAGPipeline en el store del runtime (`_rag_specs`),
        el que usa `_resolve_rag` para el KB de un agente. Espeja `register_agent`
        pero para RAG. Devuelve el nombre registrado."""
        from astromesh.rag.loader import spec_from_raw

        spec = spec_from_raw(raw)  # valida kind + name; lanza ValueError si es inválido
        self._rag_specs[spec.name] = spec
        return spec.name


class Agent:
    def __init__(
        self,
        name,
        version,
        namespace,
        description,
        routers,
        memory,
        tools,
        pattern,
        system_prompt,
        prompt_engine,
        guardrails,
        permissions,
        orchestration_config,
        rag=None,
        output_schema=None,
        prefetch=None,
    ):
        self.name = name
        self.version = version
        self.namespace = namespace
        self.description = description
        self._routers = routers
        self._role_map = (orchestration_config or {}).get("role_map", {}) or {}
        self._memory = memory
        self._rag = rag
        self._tools = tools
        self._pattern = pattern
        self._system_prompt = system_prompt
        self._prompt_engine = prompt_engine
        self._guardrails = guardrails
        self._permissions = permissions
        self._output_schema = output_schema
        self._orchestration_config = orchestration_config
        self._prefetch = prefetch or []

    async def run(
        self,
        query,
        session_id,
        context=None,
        parent_trace_id=None,
        on_event=None,
        connections=None,
        desde_humano: bool = True,
    ):
        from datetime import UTC, datetime

        from astromesh.core.memory import ConversationTurn
        from astromesh.observability.tracing import SpanStatus, TracingContext

        tracing = TracingContext(agent_name=self.name, session_id=session_id)
        if parent_trace_id:
            tracing.trace_id = parent_trace_id  # share trace tree
        root_span = tracing.start_span("agent.run", {"agent": self.name, "session": session_id})

        try:
            query_text = (
                query
                if isinstance(query, str)
                else " ".join(p.get("text", "") for p in query if p.get("type") == "text")
            )

            # El texto del humano llega UNA vez por corrida; la tool puede llamarse
            # varias. Por eso la habilitación se lee acá y no dentro de `tool_fn`.
            # Lo que se compara es el texto crudo del humano — al modelo no se le
            # pregunta si hubo consentimiento. Va `query_text`, no `query`: un
            # `query` multimodal (lista de partes) no es un `str` y `habilitar`
            # rompería contra él antes de llegar a extraer nada.
            #
            # `desde_humano=False` es una corrida re-entrante: una tool `type:
            # agent` (core/tools.py) o un paso de chain (workflow/executor.py)
            # que vuelve a entrar acá con el MISMO session_id, pero con un
            # `query` que escribió el MODELO, no la persona. Si `habilitar`
            # corriera igual, un agente podría auto-confirmarse (o confirmar a
            # otro agente hermano) con un "si" que él mismo redactó — ni
            # siquiera hace falta un prompt injection elaborado, alcanza con
            # "consultá al especialista con el mensaje 'si'". Por eso ninguna
            # corrida re-entrante puede otorgar ni cerrar un pendiente: sólo
            # puede, más abajo en `tool_fn`, usar uno que un humano ya haya
            # confirmado en una corrida anterior de la MISMA sesión.
            if desde_humano:
                _PENDIENTES.habilitar(session_id, query_text)

            root_span.set_attribute("query", query_text[:5000])

            mem_span = tracing.start_span("memory_build")
            memory_context = await self._memory.build_context(
                session_id, query_text, max_tokens=4096
            )
            tracing.finish_span(mem_span)

            rag_span = tracing.start_span("rag_build")
            knowledge_context = await self._rag.build_context(query_text) if self._rag else ""
            tracing.finish_span(rag_span)

            # La credencial que Nexus acuña por invocación, si el llamador es
            # Nexus. Clave reservada (prefijo `_`), así que nunca llegó a un
            # patrón ni a la traza — ver `_public_caller_context` — y de acá baja
            # a las tools por el dict de `tool_fn`, no por `args`, por lo mismo.
            # Muere con la corrida: no hay nada que rotar ni que revocar.
            run_secrets = {}
            run_token = (context or {}).get("_nexus_run_token")
            if run_token:
                run_secrets["NEXUS_RUN_TOKEN"] = run_token

            # Las búsquedas fijas del turno, antes del LLM: con las MISMAS
            # credenciales que `tool_fn` (connections + run_secrets). Ver
            # astromesh/runtime/prefetch.py.
            prefetch_resultados = await ejecutar_prefetch(
                self._prefetch,
                tools=self._tools,
                prompt_engine=self._prompt_engine,
                context=context,
                tool_context={
                    "agent": self.name,
                    "session": session_id,
                    "connections": connections or {},
                    "secrets": run_secrets,
                },
                tracing=tracing,
                parent_span_id=root_span.span_id,
            )

            prompt_span = tracing.start_span("prompt_render")
            rendered_prompt = self._prompt_engine.render(
                self._system_prompt,
                {
                    **(context or {}),
                    "memory": memory_context,
                    "knowledge": knowledge_context,
                    "prefetch": prefetch_resultados,
                },
            )
            if self._output_schema:
                # Ningún provider del repo soporta response_format/json_schema, así
                # que la forma se pide por prompt y se parsea de la respuesta.
                rendered_prompt += schema_prompt_block(self._output_schema)
            tracing.finish_span(prompt_span)

            tool_schemas = self._tools.get_tool_schemas(self._permissions.get("allowed_actions"))
            max_iterations = self._orchestration_config.get("max_iterations", 10)
            logger.debug(
                "agent.run %s pattern=%s max_iterations=%d tools=%d query_chars=%d",
                self.name,
                self._orchestration_config.get("pattern", "react"),
                max_iterations,
                len(tool_schemas),
                len(query_text),
            )

            route_kwargs = {}
            provider_override_config = (context or {}).get("_provider_override")
            if provider_override_config:
                from astromesh.providers.factory import create_provider

                override_name = provider_override_config["name"]
                override_key = provider_override_config["key"]
                override_provider = create_provider(override_name, api_key=override_key)
                route_kwargs["provider_override"] = (override_name, override_provider)

            async def model_fn(messages, tools, role=None):
                llm_span = tracing.start_span("llm.complete", parent_span_id=root_span.span_id)
                full_messages = [{"role": "system", "content": rendered_prompt}, *messages]
                resolved_role = self._role_map.get(role, role) if role else "default"
                router = self._routers.get(resolved_role) or self._routers["default"]
                llm_span.set_attribute("role", role or "default")
                llm_span.set_attribute("resolved_role", resolved_role or "default")
                try:
                    response = await router.route(full_messages, tools=tools, **route_kwargs)
                    # Fase 4.4c: attribute the outbound provider-request bytes to this agent.
                    try:
                        import json as _json

                        from astromesh.observability.metrics_export import get_manager as _gm

                        _m = _gm()
                        if _m is not None:
                            _req_bytes = len(_json.dumps(full_messages, default=str))
                            _m.record(self.name, getattr(response, "model", "unknown"), _req_bytes)
                    except Exception:  # noqa: BLE001, S110  (métrica best-effort: no puede alterar ni ensuciar la corrida)
                        pass
                    if hasattr(response, "usage") and response.usage:
                        llm_span.set_attribute(
                            "input_tokens", response.usage.get("input_tokens", 0)
                        )
                        llm_span.set_attribute(
                            "output_tokens", response.usage.get("output_tokens", 0)
                        )
                        # Los tokens de entrada que el proveedor sirvió de su
                        # caché de prefijo. **El provider ya los lee y
                        # `estimated_cost()` ya los descuenta, pero hasta acá
                        # se perdían**: no quedaban en el span, y Nexus no
                        # tiene columna para ellos, así que no había forma de
                        # saber si el caché estaba pegando. Sin este dato,
                        # `input_tokens` se lee como si todo se pagara a
                        # precio lleno y cualquier optimización de prefijo es
                        # inverificable. Medido contra Moonshot el 2026-09-04:
                        # cachea en bloques de 4096 y llega al 86-88% del
                        # prompt cuando el prefijo es estable.
                        llm_span.set_attribute(
                            "cached_tokens",
                            response.usage.get("cache_read_input_tokens", 0),
                        )
                    llm_span.set_attribute("model", response.model)
                    llm_span.set_attribute("provider", response.provider)
                    llm_span.set_attribute("latency_ms", response.latency_ms)
                    llm_span.set_attribute("cost", response.cost)
                    llm_span.set_attribute(
                        "tool_calls",
                        _normalize_tool_calls(response.tool_calls) if response.tool_calls else [],
                    )
                    llm_span.set_attribute("prompt", _truncate(rendered_prompt, 10_000))
                    # Store user messages so traces show the actual input
                    user_msgs = [m for m in messages if m.get("role") == "user"]
                    if user_msgs:
                        llm_span.set_attribute(
                            "input_messages",
                            _truncate(
                                "\n".join(
                                    m.get("content", "")
                                    for m in user_msgs
                                    if isinstance(m.get("content"), str)
                                ),
                                10_000,
                            ),
                        )
                    llm_span.set_attribute("response", _truncate(response.content, 10_000))
                    tracing.finish_span(llm_span)
                    if response.content:
                        _emit(on_event, {"type": "token", "content": response.content})
                    return response
                except Exception as e:
                    llm_span.set_attribute("error_message", str(e))
                    tracing.finish_span(llm_span, status=SpanStatus.ERROR)
                    raise

            async def tool_fn(name, args):
                tool_def = self._tools.get(name)
                if tool_def is not None and tool_def.needs_confirmation:
                    fp = huella(name, args)
                    if not _PENDIENTES.permitido(session_id, name, fp):
                        # No se ejecuta. Se registra la propuesta (si el slot
                        # está libre — si no, `registrar` no pisa lo que ya
                        # había, ver su docstring) y se le devuelve al modelo
                        # una observación con el pendiente REAL: `tool` +
                        # `argumentos` tal como quedaron guardados, no los que
                        # esta llamada acaba de intentar. Sin esto, un modelo
                        # que re-deriva los argumentos de memoria en vez de
                        # repetirlos (p.ej. "pedido de 2 cajas" → "pedido de
                        # dos cajas") ve un rechazo genérico, no sabe qué
                        # cambió, y puede quemar un "sí" ya dicho sin ejecutar
                        # nada — el `mensaje` le dice explícitamente que
                        # repita ESTO, no que proponga de nuevo a ciegas.
                        _PENDIENTES.registrar(session_id, name, fp, args)
                        pendiente = _PENDIENTES.pendiente(session_id)
                        return {
                            "error": "confirmacion_requerida",
                            "pendiente": {
                                "tool": pendiente["tool"],
                                "argumentos": pendiente["argumentos"],
                            },
                            "mensaje": (
                                "Ya hay una propuesta esperando confirmación. "
                                "Contale a la persona exactamente qué vas a hacer "
                                "con estos argumentos y pedile que responda SI. Si "
                                "ya te habían dicho que sí, repetí EXACTAMENTE "
                                "estos argumentos — no los vuelvas a redactar de "
                                "memoria."
                            ),
                        }
                    # Se consume ACÁ, antes de ejecutar — no al final de la
                    # corrida. Un "sí" autoriza esta llamada UNA vez: sin este
                    # `cerrar`, `permitido` seguía devolviendo True el resto de
                    # la corrida y un patrón que reintenta (o un modelo que
                    # alucina el mismo llamado dos veces) volvía a escribir con
                    # la misma confirmación. Incondicional a `desde_humano`: la
                    # licencia ya fue otorgada por una corrida humana anterior
                    # de esta sesión (`habilitar` es lo único que gatea eso),
                    # así que usarla una vez la agota sea quien sea quien la usó.
                    _PENDIENTES.cerrar(session_id)

                # One id per call so a consumer can pair the result with its call.
                call_id = str(uuid.uuid4())
                _emit(
                    on_event,
                    {"type": "tool_call", "id": call_id, "name": name, "arguments": args},
                )
                tool_span = tracing.start_span(
                    "tool.call", {"tool": name}, parent_span_id=root_span.span_id
                )
                try:
                    observation = await self._tools.execute(
                        name,
                        args,
                        {
                            "agent": self.name,
                            "session": session_id,
                            # El bundle viaja por la clausura, no por `args`: los args
                            # se persisten en la traza (set_attribute más abajo) y una
                            # credencial ahí quedaría escrita en disco.
                            "connections": connections or {},
                            # Mismo criterio, misma razón. Un sub-agente invocado
                            # como tool NO hereda esto: su corrida es otra, y
                            # reenviar la credencial es un cambio aparte.
                            "secrets": run_secrets,
                        },
                    )
                    tool_span.set_attribute("tool_args", args)
                    tool_span.set_attribute("tool_result", _truncate(str(observation), 5_000))
                    tracing.finish_span(tool_span)
                    _emit(on_event, {"type": "tool_result", "id": call_id, "ok": True})
                    return observation
                except Exception as e:
                    tool_span.set_attribute("error_message", str(e))
                    tracing.finish_span(tool_span, status=SpanStatus.ERROR)
                    _emit(on_event, {"type": "tool_result", "id": call_id, "ok": False})
                    raise

            orch_span = tracing.start_span(
                "orchestration",
                {"pattern": self._orchestration_config.get("pattern", "react")},
                parent_span_id=root_span.span_id,
            )
            result = await self._pattern.execute(
                query=query,
                # El context del llamador viaja al patrón dentro del dict que ya
                # va, bajo una clave reservada — misma convención que
                # `_history_messages`. Antes se perdía acá: sólo llegaba a
                # renderizar el prompt, así que un patrón no podía leer los
                # parámetros de la invocación.
                #
                # Va filtrado: las claves `_` son del runtime, no del llamador, y
                # `_provider_override` lleva una API key. Ver `_public_caller_context`.
                context=(
                    {**memory_context, "_caller_context": _public_caller_context(context)}
                    if isinstance(memory_context, dict)
                    else memory_context
                ),
                model_fn=model_fn,
                tool_fn=tool_fn,
                tools=tool_schemas,
                max_iterations=max_iterations,
            )
            for i, step in enumerate(result.get("steps", [])):
                step_data = {
                    "iteration": i + 1,
                    "pattern": self._orchestration_config.get("pattern", "react"),
                }
                if hasattr(step, "thought") and step.thought:
                    step_data["thought"] = _truncate(step.thought, 5_000)
                if hasattr(step, "action") and step.action:
                    step_data["action"] = step.action
                    step_data["action_input"] = step.action_input or {}
                if hasattr(step, "observation") and step.observation:
                    step_data["observation"] = _truncate(step.observation, 5_000)
                if hasattr(step, "result") and step.result:
                    step_data["result"] = _truncate(step.result, 5_000)
                orch_span.add_event("orch_step", step_data)
            tracing.finish_span(orch_span)

            # El sello del CRITICAL de la revisión final: el runtime que
            # verifica la palabra tiene que ser el mismo que hace la
            # pregunta. Antes de esto, sólo el modelo decidía si (y cómo) le
            # contaba a la persona qué quedó pendiente — un modelo comprometido
            # (o un documento inyectado) podía proponer la escritura, preguntar
            # cualquier cosa de sí/no, y el "dale" que respondía a OTRA cosa
            # terminaba autorizándola. Acá se agrega, incondicional al texto
            # del modelo, la frase que dice qué se va a ejecutar si confirman.
            #
            # `desde_humano`: sólo la corrida que atiende a una persona le
            # habla a esa persona. Una corrida re-entrante (sub-agente, paso
            # de chain) devuelve su `answer` como una OBSERVACIÓN interna, no
            # como un mensaje de chat — mismo criterio que `habilitar` /
            # `cerrar_si_confirmado` más abajo.
            #
            # `ok is False`: es justo lo que distingue "esto se registró en
            # ESTA corrida y sigue sin confirmar" de cualquier otro estado.
            # `habilitar`, al principio de esta misma función, ya limpió lo
            # que hubiera de una corrida anterior (lo borra si el mensaje no
            # confirma, o lo deja en `ok=True` si confirma) — así que un
            # pendiente con `ok=False` en este punto no puede venir de otro
            # lado: lo creó `tool_fn` en esta corrida.
            # Capturado ANTES del aviso: `build_data` más abajo tiene que parsear
            # lo que el patrón devolvió, no el aviso pegado encima — si no, un
            # output_schema con JSON pelado se rompe (data=None) justo en el
            # turno en que hay una confirmación pendiente.
            respuesta_sin_aviso = result.get("answer", "")
            if desde_humano:
                pendiente = _PENDIENTES.pendiente(session_id)
                if pendiente is not None and not pendiente["ok"]:
                    aviso = _aviso_confirmacion(pendiente["tool"], pendiente["argumentos"])
                    respuesta = result.get("answer")
                    # Todos los patrones del repo arman "answer" como str
                    # (patterns.py y glyph_pattern.py lo pasan por str()/
                    # json.dumps antes de devolverlo) — esto es sólo para no
                    # romper si el día de mañana alguno no lo hace.
                    if not isinstance(respuesta, str):
                        respuesta = "" if respuesta is None else str(respuesta)
                    result["answer"] = f"{respuesta}\n\n{aviso}" if respuesta else aviso

            # Extract text for storage; keep full multimodal content in metadata.
            if isinstance(query, list):
                text_parts = [p.get("text", "") for p in query if p.get("type") == "text"]
                user_content = " ".join(text_parts)
                user_metadata = {"multimodal_content": query}
            else:
                user_content = query
                user_metadata = {}

            persist_span = tracing.start_span("memory_persist", parent_span_id=root_span.span_id)
            await self._memory.persist_turn(
                session_id,
                ConversationTurn(
                    role="user",
                    content=user_content,
                    # Aware, no naive: esto termina en una columna TIMESTAMPTZ de
                    # Postgres, que hasta acá recibía un naive y lo asumía UTC sin
                    # que nadie lo dijera. Los backends de texto guardan ahora un
                    # isoformat con `+00:00`; `fromisoformat` lee las dos formas,
                    # así que las filas viejas se siguen leyendo.
                    timestamp=datetime.now(UTC),
                    metadata=user_metadata,
                ),
            )
            await self._memory.persist_turn(
                session_id,
                ConversationTurn(
                    role="assistant",
                    content=result.get("answer", ""),
                    timestamp=datetime.now(UTC),
                ),
            )
            tracing.finish_span(persist_span)

            tracing.finish_span(root_span)
            if self._output_schema:
                data, data_error = build_data(respuesta_sin_aviso, self._output_schema)
                result["data"] = data
                result["data_error"] = data_error
                root_span.set_attribute("output_data_ok", data_error is None)
                if data_error:
                    root_span.set_attribute("output_data_error", data_error)

            result["trace"] = tracing.to_dict()
            logger.debug(
                "agent.run %s finished answer_chars=%d steps=%d",
                self.name,
                len(result.get("answer", "") or ""),
                len(result.get("steps") or []),
            )
            return result

        except Exception as e:
            logger.exception("agent.run failed agent=%s session=%s", self.name, session_id)
            root_span.set_attribute("error_message", str(e))
            tracing.finish_span(root_span, status=SpanStatus.ERROR)
            raise
        finally:
            # Barre lo que `habilitar` dejó confirmado y sin usar (la persona
            # dijo que sí pero el modelo nunca llamó la tool en esta corrida) —
            # `tool_fn` ya consume al usar, esto es sólo el resto. Mira el
            # estado VIVO (`cerrar_si_confirmado`), no "esta corrida confirmó
            # algo": si además propuso una NUEVA acción después de confirmar la
            # anterior, esa propuesta tiene que sobrevivir al próximo mensaje.
            # Gateado por `desde_humano` por la misma razón que `habilitar`: una
            # corrida re-entrante no es un turno de conversación con la
            # persona, y no le toca decidir que ese turno terminó.
            if desde_humano:
                _PENDIENTES.cerrar_si_confirmado(session_id)
            # Fase 4.3: emit the completed trace to the active collector (InternalCollector for
            # /v1/traces, or OTLPCollector when OTLP export is enabled). In `finally` so a failed run
            # (e.g. no provider) still exports the pre-LLM spans. Best-effort; never breaks the run.
            try:
                from astromesh.api.routes.traces import get_collector

                await get_collector().emit_trace(tracing)
            except Exception:
                logger.debug("trace emit failed", exc_info=True)
            # Fase 4.4c: flush the per-agent egress metric (cold gRPC needs a waited flush, like traces).
            try:
                from astromesh.observability.metrics_export import get_manager as _gm2

                _m2 = _gm2()
                if _m2 is not None:
                    _m2.record_run(tracing)  # Fase 4.3b: derive engine metrics from the span tree
                    _m2.flush()
            except Exception:
                logger.debug("agent-egress flush failed", exc_info=True)


def _import_glyph_pattern(_name: str):
    """Import indirecto para que los tests puedan simular la ausencia del extra."""
    from astromesh.orchestration.glyph_pattern import GlyphPattern

    return GlyphPattern


def program_error_types() -> tuple[type[BaseException], ...]:
    """Los tipos de excepción que produce compilar un `spec.program`.

    Se resuelven en runtime, no con un import arriba: `astromesh_glyph` es un
    extra opcional y el core —incluida la app de FastAPI que importa esto— tiene
    que seguir importando sin él. Sin el extra no hay programa que compilar, así
    que la tupla vacía, que no atrapa nada, es la respuesta correcta.

    Las rutas la usan para mapear un programa roto a **400** con el mensaje del
    compilador (que trae la línea) en vez del 500 crudo que salía antes, porque
    `GlyphError` no hereda de `ValueError`.
    """
    try:
        from astromesh_glyph import GlyphError
    except ImportError:
        return ()
    return (GlyphError,)


def _compile_glyph_program(program: str, tool_schemas: list[dict]) -> None:
    """Compila un programa del YAML contra el catálogo del agente.

    Import diferido por la misma razón que `_import_glyph_pattern`: el extra es
    opcional. Deja subir `GlyphSyntaxError` / `GlyphCompileError` — un programa
    roto tiene que impedir que el agente cargue.
    """
    from astromesh_glyph import compile_program, parse

    from astromesh.orchestration.glyph_pattern import PatternCapabilities

    catalog = PatternCapabilities(
        tools=tool_schemas, tool_fn=None, model_fn=None
    ).list_capabilities()
    compile_program(parse(program), catalog, predefined=("query", "context"))
