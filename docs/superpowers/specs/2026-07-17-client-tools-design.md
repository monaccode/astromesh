# Client tools: tools que el runtime anuncia y no ejecuta — Diseño

**Fecha:** 2026-07-17
**Rama:** `feature/client-tools`
**Estado:** aprobado
**Versión objetivo:** 0.35.0

---

## 1. El agujero

Un agente que maneja una interfaz necesita decir *"mostrá esto"* sin que el runtime tenga que saber qué es "esto". AstroMesh no tiene forma de expresarlo.

Todos los tipos de tool que existen asumen que el **runtime** hace el trabajo: `builtin` corre código Python, `agent` delega en otro agente, `mcp_*` llama a un servidor. No hay ninguno donde el trabajo lo haga **quien está escuchando**.

Desde 0.34.0 un consumidor puede ver los `tool_call` de una corrida en vivo (`on_event`), y desde siempre los ve después en `AgentRunResponse.steps`. Lo que falta es poder **declarar** una tool cuyo propósito es justamente ser vista.

## 2. El agujero de al lado: el ignore silencioso

El loader de tools del YAML (`astromesh/runtime/engine.py:375-400`) tiene dos ramas: `builtin` y `agent`. Cualquier otro `type` **se descarta sin decir nada**: no se registra, no entra en los schemas, el modelo ni la ve.

El tipo por defecto es `internal` (`tool_def.get("type", "internal")`, línea 376), así que **una tool sin `type` no existe**.

Esto no es teórico. Dos agentes del propio repo lo tienen:
- `config/agents/sales-qualifier.agent.yaml` → `lookup_company`, `type: internal`
- `config/agents/autolink-parts.agent.yaml` → dos tools `internal`

Ninguna de esas tres existe en runtime. Los agentes cargan, el modelo nunca las ve, nadie se entera.

Y la documentación lo empeora. `docs/CONFIGURATION_GUIDE.md:123` promete:

```yaml
type: internal            # internal | mcp | webhook | rag
```

**Los cuatro son falsos** — ninguno se carga desde YAML. Los dos que sí funcionan, `builtin` y `agent`, no están en esa línea. Las listas documentada e implementada son casi disjuntas.

Tampoco hay salida por afuera: `ToolLoader.auto_discover()` (`astromesh/tools/__init__.py:27`) importa una lista hardcodeada (`ALL_TOOLS` de `astromesh.tools.builtin`). Sin entry points, no se pueden traer tools en un paquete propio.

---

## 3. `type: client`

Una tool que el runtime **anuncia al modelo y no ejecuta**. Cuando el modelo la llama, el runtime registra la llamada y devuelve una confirmación mínima. Qué se hace con esa llamada es de quien escucha.

**Por qué `client` y no `ui`/`signal`:** nombra *quién la ejecuta* — el cliente, no el runtime — y es el término que el resto del ecosistema agéntico ya usa ("client-side tool"). Describe el contrato, no un caso de uso: sirve igual para una web que monta componentes, un cliente REST que renderiza al terminar, o cualquier otra cosa. `ui` le clavaría nuestro caso a la plataforma.

### Lo que se agrega

**`ToolType.CLIENT = "client"`** en el enum (`astromesh/core/tools.py`).

**`ToolRegistry.register_client_tool(name, description, parameters=None, **kwargs)`** — calcado de `register_agent_tool` (`core/tools.py:84`), sin handler. `parameters` es el JSON Schema que el modelo necesita para llamarla bien.

**Una rama en el loader** (`engine.py:375-400`), junto a `builtin` y `agent`:

```yaml
tools:
  - name: diagram_process
    type: client
    description: "Draw the visitor's process as a flow"
    parameters:
      nodes: {...}
      edges: {...}
```

**Una rama en `execute()`** (`core/tools.py:114`) que devuelve `{"ok": True}` sin ejecutar nada.

### Por qué `{"ok": True}` y no los argumentos

ReAct necesita una observación para continuar el loop, así que algo hay que devolver.

No los args: el modelo los escribió, ya los sabe, y devolvérselos duplica `action_input` en `steps` por nada.

Y **no** algo como `{"delivered": true}`, que sería mentira: el runtime señala, no sabe si alguien escuchó. `{"ok": True}` dice lo único cierto — la llamada se registró.

### La propiedad que sale gratis

Una tool `client` llega al consumidor por **dos** caminos:

- **En vivo**, vía `on_event` → `{"type": "tool_call", "id", "name", "arguments"}` (0.34.0).
- **Después**, en `AgentRunResponse.steps` → `action` y `action_input`.

Sirve igual para un consumidor que monta componentes mientras el agente trabaja y para uno que renderiza al final. Es exactamente por qué se llama `client` y no `ui`.

**El corolario incómodo, que va en la doc:** una tool `client` sin nadie escuchando es un no-op silencioso. Es correcto — el runtime hizo su parte, anunciar y registrar — pero hay que decirlo.

---

## 4. El ignore silencioso pasa a avisar

Un `type` no soportado loguea un **WARNING** que nombra la tool, el agente y el tipo, y dice que se está ignorando. El agente **igual carga**.

**Por qué no lanzar.** Sería lo correcto en abstracto, y fue tentador: un error es imposible de ignorar, que es el punto. Pero rompe a `autolink-parts` y `sales-qualifier` — `bootstrap()` deja de arrancar el runtime entero — y a cualquiera afuera con `internal` en un YAML, subir de versión le voltea el servicio. Un breaking change en una versión menor, por tools que hoy ya no hacían nada. El WARNING mata lo que realmente dolía —el silencio— sin ese costo.

Se documenta como deprecado, con el error prometido para la 1.0.

## 5. Se arreglan los YAMLs del repo

`sales-qualifier.agent.yaml` y `autolink-parts.agent.yaml` declaran tools que no existen. Sus `type: internal` pasan a `client`, que es lo único que un YAML puede significar: un YAML no puede aportar un handler Python.

No es limpieza gratuita. `sales-qualifier` es el agente que usa el smoke test del WebSocket, y un agente de ejemplo que miente sobre sus tools es deuda que ya nos tocó pagar una vez.

## 6. La doc que miente

`docs/CONFIGURATION_GUIDE.md:123` pasa a decir la verdad: **`builtin | agent | client`**, con una nota de que `webhook` y `rag` aparecen en `ToolType` pero **no son declarables desde YAML** hoy, y que `internal` está deprecado.

---

## 7. Tests

- `register_client_tool` registra la tool, y **aparece en `get_tool_schemas()`** — si no, el modelo nunca la ve y la feature no existe.
- `execute()` sobre una tool `client` devuelve `{"ok": True}` **sin llamar a ningún handler**.
- Una tool `client` declarada en un YAML **se carga de verdad**: el test que caza que el loader la ignore, que es el fallo que motivó todo esto.
- Un `type` no soportado **loguea el WARNING y el agente igual carga** (`caplog`).
- **La composición con 0.34.0:** una tool `client` emite `tool_call` con sus args vía `on_event`, **y** aparece en `steps` con su `action_input`. Los dos caminos de §3, que son el punto.
- Los YAMLs arreglados cargan y sus tools aparecen en los schemas.

`asyncio_mode = "auto"` (no `@pytest.mark.asyncio`). Tests flat en `tests/`. `uv run pytest -v`.

## 8. Fuera de alcance

- Implementar `webhook` y `rag` desde YAML — features enteras que nadie pidió. Quedan documentadas como no soportadas en vez de prometidas.
- Entry points para tools de terceros (§2). Real, pero es otro diseño.
- Que el error reemplace al warning: 1.0.
- Que el ADK soporte `client`. El ADK duplica el runtime (`astromesh-adk/astromesh_adk/runner.py` arma sus propios `model_fn`/`tool_fn`, cero referencias a `Agent`), así que no hereda nada de esto. Es la misma deuda que le impide emitir eventos.
