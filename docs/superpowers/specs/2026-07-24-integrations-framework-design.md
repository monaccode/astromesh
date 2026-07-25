# Marco de integraciones: manifests declarativos que producen tools — Diseño

**Fecha:** 2026-07-24
**Rama:** `feature/integrations-framework`
**Estado:** aprobado
**Versión objetivo:** 0.37.0

---

## 1. El agujero

AstroMesh tiene un patrón de **tool**. No tiene un patrón de **integración**.

La diferencia importa cuando el objetivo es conectar decenas de servicios externos. Una tool es una función suelta: nombre, descripción, esquema, handler. Una integración es un servicio con identidad propia — una base_url, un esquema de autenticación, una credencial que pertenece a alguien, y N acciones que comparten todo eso. Hoy lo segundo hay que fabricarlo a mano, tool por tool, y no escala.

Concretamente, lo que falta:

**No hay credenciales.** `ToolContext.secrets` existe (`astromesh/tools/base.py:32`) y **nunca se puebla**. El único constructor del camino caliente, `_make_builtin_handler` (`astromesh/runtime/engine.py:56-67`), crea el contexto sin `secrets`; el otro, en `ToolRegistry.register_builtin` (`astromesh/core/tools.py:241`), le pasa `secrets={}` literal. Así que `SendSlackTool` (`astromesh/tools/builtin/communication.py:57`) sólo funciona si le escribís la webhook URL en claro en el YAML del agente. Tres tools del catálogo actual leen `context.secrets` y las tres leen un dict vacío, siempre.

**No hay descubrimiento.** `ToolLoader.auto_discover()` (`astromesh/tools/__init__.py:27`) importa `ALL_TOOLS`, una lista hardcodeada de 17 clases en `astromesh/tools/builtin/__init__.py:20`. Cada integración nueva sería una edición a un archivo central compartido — el cuello de botella exacto que impide crecer rápido.

**No hay agrupación.** Un `BuiltinTool` es una clase Python por acción. Una integración con 12 acciones son 12 clases repitiendo base_url, headers y manejo de auth.

**MCP está muerto.** `MCPClient` (`astromesh/mcp/client.py:14`) y `ToolRegistry.register_mcp_server` (`astromesh/core/tools.py:214`) existen, y **nadie los llama**. El YAML no soporta `type: mcp`; cae en la rama de tipo no soportado (`engine.py:567`) y se ignora con warning. La salida "usá MCP para las integraciones" hoy no está disponible.

**`requires_approval` es un campo muerto.** Declarado en `ToolDefinition` (`astromesh/core/tools.py:37`), no lo lee nadie. El único HITL que existe es de *workflows* (`StepType.APPROVAL`, spec `2026-07-11-atlas-slice2-hitl-approval-design.md`), no del camino de tools de un agente.

---

## 2. Qué se construye

Un catálogo de integraciones **declarativas**: cada una es un manifest YAML que describe base_url, autenticación y acciones. Un motor genérico convierte cada acción en una tool que el agente puede llamar. Las acciones que no caben en un request HTTP declaran un handler Python.

El criterio de éxito no es "tenemos Instagram". Es: **agregar la integración número nueve debe ser un archivo YAML y un PR, sin tocar ningún archivo compartido y sin escribir un test.**

### Decisiones que enmarcan el resto

| Decisión | Elegido | Descartado |
|---|---|---|
| Dónde vive el código | in-tree, catálogo auto-descubierto | pip separado / entry points / todo MCP |
| Autoría de acciones | manifest declarativo + escape a Python | sólo Python / DSL multi-paso en YAML |
| Credenciales | Nexus custodia, el core las recibe por corrida | store propio en el core |
| Habilitación | integración + allowlist explícita de acciones | acción por acción / integración completa |
| Alcance de este spec | sólo core: marco + contrato + 3 manifests | incluir el lado Nexus |

---

## 3. Arquitectura

Paquete nuevo `astromesh/integrations/`, hermano de `tools/`:

```
astromesh/integrations/
  __init__.py       IntegrationCatalog — descubre, valida, cachea
  manifest.py       dataclasses + parseo/validación de integration.yaml
  auth.py           AuthScheme: credencial → headers/query del request
  executor.py       HttpActionExecutor: acción + args + credencial → ToolResult
  credentials.py    ConnectionRef, CredentialBundle, CredentialResolver
  handlers.py       resolución del escape `python:modulo:funcion`
  errors.py         mapeo HTTP → error_kind
  schema.py         normalización de `parameters` a JSON Schema (§4.4)
  catalog/
    http/integration.yaml
    whatsapp/integration.yaml
    google_drive/
      integration.yaml
      handlers.py
```

**Por qué no dentro de `tools/builtin/`.** Un `BuiltinTool` es una clase que se instancia. Una integración es *datos* que producen N tools. Meterlas en `tools/builtin/` obligaría a `ALL_TOOLS` a crecer con clases sintéticas — es decir, conservaría el cuello de botella que este spec existe para eliminar.

`IntegrationCatalog.discover()` recorre `catalog/*/integration.yaml` al bootstrap, valida cada manifest y cachea el resultado. Un manifest inválido se registra con `logger.error` nombrando archivo y causa, y se salta: una integración rota no puede impedir que arranque el runtime. Mismo criterio warn-don't-break que ya usa el loader de tools (`engine.py:574`).

---

## 4. El manifest

El ejemplo usa `instagram` porque ejercita los dos modos (declarativo y escape) en un solo manifest. Es **ilustrativo**: el catálogo que entrega este spec son otros tres (§10), e `instagram` es una de las que quedan habilitadas para después.

```yaml
apiVersion: astromesh/v1
kind: Integration
metadata:
  name: instagram
  version: 0.1.0
  description: "Instagram Graph API"
spec:
  base_url: "https://graph.facebook.com/v21.0"
  auth:
    scheme: bearer               # bearer | header | query | basic | none
    credential: access_token     # clave esperada en el bundle de la conexión
  defaults:
    timeout_seconds: 30
    headers: {}
    rate_limit: {window_seconds: 60, max_calls: 30}
  actions:
    - name: list_media
      description: "Lista el media de una cuenta business"
      parameters:                          # taquigrafía, igual que el YAML de agentes
        ig_user_id: {type: string, description: "ID de la cuenta", required: true}
        limit: {type: integer, description: "Máximo de items", default: 25}
      request:
        method: GET
        path: "/{ig_user_id}/media"
        query:
          fields: "id,caption,permalink,timestamp"
          limit: "{limit}"
      response:
        select: "data"
      pagination:
        style: cursor
        cursor_param: after
        cursor_path: "paging.cursors.after"

    - name: publish_photo
      description: "Publica una foto en la cuenta"
      writes: true
      handler: "python:astromesh.integrations.catalog.instagram.handlers:publish_photo"
      parameters:
        image_url: {type: string, description: "URL pública de la imagen", required: true}
        caption: {type: string, description: "Texto del post"}
```

### 4.1 Campos de `spec`

- **`base_url`** — opcional. Si el manifest no lo trae, la conexión debe aportarlo (es el caso de `http`). Si lo trae, la conexión puede sobreescribirlo (sandboxes, self-hosted, endpoints regionales).
- **`auth.scheme`** — cómo se pone la credencial en el cable, nada más. El core no negocia, no refresca y no conoce `client_secret`.
  - `bearer` → `Authorization: Bearer <cred>`
  - `header` → header con nombre configurable (`auth.header_name`)
  - `query` → parámetro de query (`auth.param_name`)
  - `basic` → `Authorization: Basic base64(user:pass)`, credencial `{username, password}`
  - `none` → sin auth (APIs internas abiertas)
- **`auth.credential`** — el nombre de la clave que se busca en el bundle. Documenta el contrato hacia Nexus: qué material hay que entregar.
- **`defaults`** — timeout, headers fijos (p.ej. `Notion-Version`) y rate limit heredados por todas las acciones, sobreescribibles por acción.

### 4.2 Campos de una acción

- **`parameters`** — taquigrafía `nombre: {type, description, required, default}`. Se normaliza a JSON Schema con la misma función que ya usa el YAML de agentes.
- **`request`** — `method`, `path`, `query`, `headers`, `body`. Declarativo.
- **`handler`** — `python:modulo:funcion`. Escape.
- **`request` y `handler` son mutuamente excluyentes.** Una acción es declarativa o es Python, nunca mitad. El validador falla ruidoso al cargar el manifest, no en la primera llamada.
- **`response.select`** — camino separado por puntos dentro del JSON de respuesta (`"data"`, `"result.items"`). Sin él, se devuelve el payload entero. Existe porque devolverle al modelo 40 KB de envoltorio de Graph API para llegar a 5 items gasta contexto y empeora las decisiones.
- **`pagination`** — declarativa, dos estilos: `cursor` (`cursor_param` + `cursor_path`) y `offset` (`limit_param` + `offset_param`). El ejecutor expone un parámetro `cursor` opcional en el esquema de la tool y devuelve el `next_cursor` en `metadata`. **No** pagina solo hasta el final: eso puede ser cientos de requests y megabytes hacia el modelo. Trae una página y le dice al modelo cómo pedir la siguiente.
- **`writes`** — booleano. Metadato, ver §7.
- **`rate_limit`** — sobreescribe el default del manifest.

### 4.3 Interpolación

`{param}` se sustituye por el argumento correspondiente, URL-encoded según la posición (path segment, query value, o valor JSON en el body).

**No se usa Jinja2, deliberadamente.** Los argumentos los escribe un LLM. Darle a una cadena de origen no confiable un motor de plantillas con acceso a atributos y llamadas es una superficie de ejecución, no una comodidad. El repo ya tiene Jinja2 para prompts, donde el autor es humano; acá el autor es el modelo.

**Guardia de traversal:** un `{param}` interpolado dentro de `path` no puede contener `/`, `..`, ni `%2e%2e` ya decodificado. Un parámetro que legítimamente necesita barras (p.ej. un path de repositorio) lo declara con `allow_slash: true` y aun así se le prohíbe `..`. Sin esta guardia, `{ig_user_id}` con valor `../../me/accounts` reescribe el endpoint.

Un `{param}` sin argumento y sin `default`: si el parámetro es `required` no debería pasar (lo valida el esquema), pero si llega, la acción devuelve `bad_request` en vez de mandar la URL con el literal `{param}` adentro.

### 4.4 Reuso de `_normalize_tool_parameters`

La función vive hoy en `astromesh/runtime/engine.py:80-140` y hace exactamente lo que este marco necesita: convierte la taquigrafía YAML en JSON Schema válido, es idempotente, y respeta al autor que ya escribió JSON Schema real.

**Se muda a `astromesh/integrations/schema.py`** (o un módulo compartido equivalente) y `engine.py` la importa desde ahí. Sin cambio de comportamiento, sin cambio de firma, con sus tests actuales intactos. Es el tipo de mejora dirigida que corresponde hacer en el código que uno está tocando: la alternativa es una segunda copia de una función cuyo docstring explica que existe porque su ausencia rompía requests enteras.

---

## 5. Credenciales

### 5.1 El contrato

El core no guarda, no cifra y no refresca nada. Recibe un bundle resuelto por corrida:

```http
POST /v1/agents/{name}/run
Content-Type: application/json

{
  "query": "...",
  "session_id": "...",
  "context": {},
  "connections": {
    "ig_main":  {"access_token": "EAAG..."},
    "crm_acme": {"api_key": "...", "base_url": "https://crm.acme.internal"}
  }
}
```

`connections` mapea **nombre de conexión** → material de credencial. Las claves del material son las que el manifest declara en `auth.credential`, más un `base_url` opcional que sobreescribe el del manifest.

El agente declara qué conexión usa y qué acciones expone:

```yaml
tools:
  - type: integration
    name: instagram
    connection: ig_main
    actions: [list_media, publish_photo]
```

`actions` es obligatorio y es una allowlist. Sin él, el agente no carga esa integración y se registra un warning nombrando agente e integración. La razón es de contexto y de permisos a la vez: exponer las 12 acciones de tres integraciones son 36 esquemas en cada prompt, y el modelo elige peor cuanto más ruido tiene. Una acción no listada no existe para ese agente.

Una acción listada que el manifest no define: warning nombrando agente, integración y acción; se saltea esa acción, el resto de la integración carga. Mismo criterio que el resto del loader.

### 5.2 `CredentialResolver`

Orden de resolución:

1. **Bundle de la corrida** — lo que inyecta Nexus. Máxima prioridad.
2. **`config/connections.yaml`** — para self-hosted sin Nexus, con la misma sintaxis `${VAR}` que ya usa `config/channels.yaml`.
3. **Ausente** — la acción devuelve `ToolResult(success=False, error_kind="credential_missing")`. No revienta el run.

```yaml
# config/connections.yaml
connections:
  ig_main:
    access_token: "${INSTAGRAM_ACCESS_TOKEN}"
  crm_acme:
    api_key: "${CRM_API_KEY}"
    base_url: "${CRM_BASE_URL}"
```

Esto también repara, de paso, el hueco de `ToolContext.secrets`: el resolver es el mecanismo que faltaba para que una tool obtenga una credencial sin que esté escrita en el YAML del agente.

### 5.3 Enhebrado

`AgentRuntime.run(agent_name, query, session_id, context=None, parent_trace_id=None, on_event=None, connections=None)` → `Agent.run(...)` → el dict de contexto que `tool_fn` ya construye en `engine.py:897`:

```python
observation = await self._tools.execute(
    name, args, {"agent": self.name, "session": session_id, "connections": connections or {}}
)
```

**Ninguna firma de patrón de orquestación cambia.** `tool_fn(name, args)` sigue igual; el bundle viaja en la clausura, que es donde ya viven `session_id` y `self.name`. `connections` ausente = `{}`, y todo lo que existe hoy sigue funcionando sin tocarse.

Rutas que lo aceptan: `POST /v1/agents/{name}/run` (campo opcional en `AgentRunRequest`) y el WebSocket `/v1/ws/agent/{name}`.

### 5.4 Contención

El material de credencial entra por `connections`, baja por el dict de contexto, se usa para firmar un request, y muere ahí. En particular:

- **Nunca en `arguments`.** Los args de tool se persisten en la traza (`tool_span.set_attribute("tool_args", args)`, `engine.py:900`). Que la credencial venga por un canal separado de los argumentos del modelo no es sólo higiene: es lo que impide que termine en disco.
- **Nunca en la memoria del agente.** No entra al contexto conversacional ni al episódico.
- **Nunca en la respuesta.** `AgentRunResponse` no la refleja.
- **Nunca en los spans.** El span `integration.call` lleva slug, acción, status y latencia. No lleva headers ni body de auth.
- **Nunca en logs.** El logging de request en DEBUG redacta el header de autorización.

Esto se verifica con una prueba, no con una convención: ver §8.

### 5.5 Requisito de transporte

Aceptar material de credencial en el body implica que el enlace Nexus→runtime debe ser TLS o intra-cluster. Queda escrito acá como requisito heredado por el spec de Nexus. El runtime no lo puede hacer cumplir por sí solo; lo que sí hace es no persistir nunca lo que recibe.

---

## 6. Registro y ejecución

### 6.1 Tipo de tool y nombres

`ToolType.INTEGRATION = "integration"` se suma al enum (`astromesh/core/tools.py:18`). `ToolDefinition` gana `integration_config: dict | None` con `{slug, connection, action}`.

**El nombre registrado es `<slug>_<accion>`, con guion bajo.** `instagram_list_media`, no `instagram.list_media`.

Esto no es estilo. OpenAI y Anthropic validan los nombres de función contra `^[a-zA-Z0-9_-]{1,64}$`; un punto hace fallar la request **entera** con 400, no sólo esa tool — el mismo modo de fallo que documenta `_normalize_tool_parameters` en `engine.py:88-97`. La unicidad global sale gratis porque el slug ya es único en el catálogo. El límite de 64 caracteres se valida en el test de conformidad.

### 6.2 Carga en `_build_agent`

Rama nueva junto a `builtin` / `agent` / `client` (`engine.py:519-580`):

```python
elif tool_type == "integration":
    integration = catalog.get(tool_def["name"])          # warning + skip si no existe
    for action_name in tool_def.get("actions", []):
        action = integration.action(action_name)         # warning + skip si no existe
        tools.register_integration_tool(
            name=f"{integration.slug}_{action.name}",
            integration=integration,
            action=action,
            connection=tool_def["connection"],
            rate_limit=tool_def.get("rate_limit") or action.rate_limit,
        )
```

### 6.3 Ejecución

Rama nueva en `ToolRegistry.execute()` (`astromesh/core/tools.py:141`), después de la de rate limit que ya corre para todos los tipos:

1. Saca `connections` del dict de contexto.
2. `CredentialResolver` resuelve `tool.integration_config["connection"]` → material + `base_url` efectivo.
3. Si falta → `credential_missing`.
4. Si la acción tiene `handler` → carga el símbolo y lo invoca con `(arguments, IntegrationContext)`.
5. Si no → `HttpActionExecutor`: construye el request, lo firma, lo manda, mapea la respuesta.

`IntegrationContext` lleva credencial resuelta, base_url efectivo, un `httpx.AsyncClient` ya configurado con timeout y auth, `agent_name` y `session_id`. Un handler Python no vuelve a implementar auth ni a construir clientes: recibe uno que ya sabe firmar.

---

## 7. Errores y escrituras

### 7.1 Ningún error levanta excepción

`tool_fn` re-lanza cualquier excepción (`engine.py:905-909`) y eso **mata la corrida entera**. Un 404 de Instagram no puede tumbar al agente.

Todo sale como `ToolResult(success=False, error=..., metadata={"error_kind": ...})`, que el patrón ReAct ve como observación y sobre la que puede corregir. Los handlers Python quedan envueltos en el mismo `try`: un handler con un bug produce `upstream_error`, no una corrida muerta.

### 7.2 Mapeo de errores

Es parte del contrato porque Nexus lo consume para decidir qué hacer:

| HTTP | `error_kind` | Consumo |
|---|---|---|
| 401, 403 | `credential_invalid` | Nexus dispara refresh de OAuth y reintenta |
| 429 | `rate_limited` (+ `retry_after`) | backoff, no reintento ciego |
| 408, 5xx, timeout, error de red | `upstream_error` | reintentable |
| 4xx restantes | `bad_request` | el modelo corrigió mal los args; que reintente él |
| credencial ausente | `credential_missing` | falta configurar la conexión |
| rate limit local | `rate_limited_local` | lo frenó AstroMesh, no el proveedor |

El `error_kind` viaja en `metadata` del `ToolResult` y como atributo del span.

### 7.3 `writes` no bloquea en v1

`writes: true` se refleja en `ToolDefinition.requires_approval`, se publica en el catálogo (§9) y viaja en el evento `tool_call` para que un consumidor lo interponga del lado del cliente. **El runtime no bloquea.**

Se dice explícito porque `requires_approval` ya existe y no lo lee nadie (§1), y el HITL implementado es sólo de workflows. Enganchar aprobación humana real en el camino de tools de un agente es otro spec. Lo que este marco entrega es la señal correcta y honesta; quien la quiera hacer valer, hoy, la hace valer del lado del cliente.

### 7.4 Rate limiting

Reusa `_check_rate_limit` (`astromesh/core/tools.py:252`), incluido el acelerador nativo Rust. Precedencia: `rate_limit` del YAML del agente > `rate_limit` de la acción > `defaults.rate_limit` del manifest > nada.

Nota: el limitador es por nombre de tool y por proceso. Con varias réplicas del runtime, el límite efectivo se multiplica por el número de réplicas. No se resuelve acá — se documenta, porque quien configure un límite cerca del límite real del proveedor necesita saberlo.

---

## 8. Pruebas

`respx` para todo el HTTP, como manda la convención del repo. `pytest` con `asyncio_mode = "auto"`.

### 8.1 Conformidad del catálogo — lo importante

Un test parametrizado sobre `catalog/*/integration.yaml` que verifica, para **cada manifest presente y futuro**:

- valida contra el esquema del manifest;
- cada bloque `parameters` normaliza a JSON Schema válido;
- cada nombre `<slug>_<accion>` cumple `^[a-zA-Z0-9_-]{1,64}$` y no excede 64 caracteres;
- ningún `handler:` apunta a un símbolo inexistente o no invocable;
- ninguna acción declara `handler` y `request` a la vez;
- todo `{param}` que aparece en `path`, `query`, `headers` o `body` está declarado en `parameters`;
- toda acción tiene `description` no vacía (es lo único que el modelo lee para decidir);
- el `auth.credential` declarado es coherente con el `scheme`.

**Esto es el corazón del entregable.** Nadie tiene que acordarse de escribir estos tests: el manifest número nueve los hereda por existir. Es lo que convierte "agregar una integración" en un PR de un archivo.

### 8.2 Seguridad

- **Redacción:** correr un agente con una credencial conocida y afirmar que el string no aparece en la traza, ni en la memoria, ni en la respuesta, ni en los logs capturados.
- **Traversal:** `{param}` con valor `../../me/accounts` no escapa del path; con `allow_slash: true` permite `/` pero sigue rechazando `..`.
- **Aislamiento:** dos agentes con conexiones distintas en la misma corrida no se ven la credencial del otro; una acción de la integración A no puede resolver la conexión de B.

### 8.3 Marco

Ejecutor: construcción de URL, interpolación en las cuatro posiciones, `response.select`, paginación cursor y offset, los seis `error_kind`, timeouts, precedencia de rate limit.
Catálogo: descubrimiento, manifest inválido se saltea sin tumbar el bootstrap, resolución de handlers.
Resolver: las tres capas de precedencia y el sobreescribir `base_url` desde la conexión.
Carga: allowlist respetada, acción inexistente saltea sólo esa acción, integración inexistente saltea sólo esa integración.

### 8.4 Las tres integraciones

Una por manifest con `respx`: camino feliz, un error, y — donde aplique — paginación. El upload resumable de Drive con su secuencia de dos llamadas mockeada.

---

## 9. API y observabilidad

- **`GET /v1/integrations`** — catálogo: slug, versión, descripción, y por acción nombre, descripción, `writes` y credenciales requeridas. De paso llena `GET /v1/tools`, que hoy devuelve `{"tools": []}` fijo (`astromesh/api/routes/tools.py:14`).
- **`GET /v1/integrations/{slug}`** — detalle, incluido el esquema JSON de parámetros de cada acción. Es lo que consume Nexus para pintar la UI de conexiones y saber qué material pedir en el OAuth.

Ninguna de las dos expone credenciales: publican *qué claves hace falta entregar*, nunca valores.

Span `integration.call`, hijo del span de la tool: `integration.slug`, `integration.action`, `http.status_code`, `error_kind`, latencia, y si hubo paginación. Sin headers, sin body, sin credencial.

---

## 10. Catálogo v1

Tres manifests, elegidos porque cada uno rompe una parte distinta del marco y porque los demás salen por copia:

### `http` — genérica / on-prem
`base_url` y esquema de auth vienen **de la conexión**, no del manifest. Acciones: `get`, `post`, `put`, `delete` con path, query, headers y body parametrizables. Prueba que el marco no asume SaaS público, y cubre APIs internas y legacy sin escribir un manifest por cliente.

### `whatsapp` — Meta Graph, declarativo puro
Bearer sobre `https://graph.facebook.com/v21.0`. Acciones **salientes**: `send_text`, `send_template`, `get_media`. Es la plantilla literal de `instagram` y `facebook`: misma base_url, mismo esquema de auth, misma forma de paginación.

**Alcance y no-alcance.** El canal `astromesh/channels/whatsapp.py` sigue siendo el dueño del webhook *entrante*, la verificación de firma (`verify_request`, línea 35) y el parseo de mensajes. Este spec **no lo toca**. La duplicación de `GRAPH_API_URL` (`channels/whatsapp.py:21`) con el manifest queda reconocida: consolidar — que el canal delegue su envío en la integración — es una mejora candidata posterior, no parte de esto. Refactorizar el canal ahora sería alcance que nadie pidió, con riesgo sobre un camino en producción.

### `google_drive` — OAuth Google + escape a Python
Bearer con access token de Google. Acciones declarativas: `list_files`, `get_file`, `search`. Una acción con `handler:`: `upload_file`, que necesita sesión resumable (init → PUT del contenido) y no cabe en un request. Es la única que ejercita el escape, y es la plantilla de `gmail` y `sheets`.

### Lo que habilita

Con estos tres, las cinco que faltan del pedido original — `instagram`, `facebook`, `gmail`, `sheets`, `tiktok` — son un YAML y un PR cada una, con sus tests de conformidad heredados. Ese es el entregable real; las tres integraciones son la prueba de que el marco funciona, no el objetivo.

---

## 11. Fuera de alcance

Explícito para que el plan no se estire solo:

- **OAuth, consent y refresh de tokens** — de Nexus. El core nunca ve un `client_secret`.
- **Almacén de credenciales cifrado** — de Nexus.
- **El lado Nexus del contrato** — su propio spec, en su propio repo y lenguaje.
- **HITL en el camino de tools de un agente** — spec propio; §7.3 explica qué sí entrega este.
- **Caché de respuestas de integración.**
- **Entry points para plugins de terceros** — el catálogo es in-tree por decisión. Si más adelante hace falta, `IntegrationCatalog.discover()` es el único punto a extender, y el contrato del manifest no cambia.
- **Conectar `MCPClient`** — sigue muerto. Revivirlo es un spec propio y mezclarlo acá confundiría dos mecanismos de integración distintos.
- **Reescribir el canal de WhatsApp** — ver §10.
- **Rate limiting distribuido** — ver §7.4.

---

## 12. Riesgos

**El escape a Python se convierte en la norma.** Si la mitad de las acciones terminan con `handler:`, el marco declarativo no está pagando su costo. Mitigación: el catálogo v1 tiene exactamente una acción con handler sobre ~11; si esa proporción se invierte en las siguientes cinco integraciones, la decisión de §2 hay que revisarla, no forzarla.

**El manifest se queda corto y crece por parches.** Cada campo nuevo (`select`, `pagination`, `allow_slash`) es un paso hacia el DSL que descartamos. Mitigación: campo nuevo sólo cuando lo pidan dos integraciones distintas; una sola usa `handler:`.

**Credenciales en el body.** Mitigado por §5.4 (contención probada) y §5.5 (requisito de transporte), no eliminado. La alternativa — que el core llame de vuelta a Nexus por cada tool — cambia el modo de fallo por latencia y acoplamiento, y no fue lo elegido.

**El `description` de una acción es todo lo que el modelo tiene.** Un manifest con descripciones pobres produce un agente que elige mal, y eso no lo detecta ningún test. Mitigación parcial: el test de conformidad exige `description` no vacía. La calidad sigue siendo del autor.
