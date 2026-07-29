# Encadenamiento de agentes (`spec.chain`)

Disponible desde astromesh **v0.38.1**.

Un agente declara, en su propio YAML, qué otros agentes disparar cuando termina — y bajo qué
condiciones.

```yaml
spec:
  output_schema:
    score: {type: integer}

  chain:
    on_complete:
      - agent: email-composer
        when: "{{ output.data.score > 7 }}"
```

## Por qué no es sólo un `kind: Workflow`

Un workflow describe una secuencia **desde afuera**: alguien más decide qué agentes se
encadenan y en qué orden. Sirve cuando el proceso es el protagonista.

Una cadena vive **en el agente**. El agente sabe por sí mismo a quién despertar al terminar,
así que se puede reusar en cualquier contexto sin que nadie tenga que envolverlo. Y como se
compila a un `WorkflowSpec`, corre sobre el mismo motor: no hay dos formas de ejecutar lo mismo.

Bajo el capó, `spec.chain` se compila **al arrancar el runtime** a un workflow sintético
llamado `__chain__<agente>`. Eso tiene tres consecuencias que importan:

- un ciclo, un `max_depth` excedido o un agente inexistente **impiden el arranque**, con la
  ruta completa en el mensaje — no fallan a mitad de una corrida en producción
- la cadena expandida es **inspeccionable sin ejecutar nada** (`GET /v1/agents/{n}/chain`)
- el prefijo `__chain__` queda reservado: un workflow escrito a mano que lo use es rechazado
  por el loader, para que no pise silenciosamente la cadena de un agente

## Superficie completa

```yaml
spec:
  chain:
    mode: sequential        # sequential | parallel   (default: sequential)
    max_depth: 5            # default: 5

    on_complete:
      - agent: email-composer
        when: "{{ output.data.score > 7 }}"
        input: "{{ output.answer }}"          # default: "{{ output.answer }}"
        retry:
          max_attempts: 3
          backoff: exponential                # fixed | exponential
          initial_delay_seconds: 2
        timeout_seconds: 30
        on_error: continue                    # stop (default) | continue | <agente>

      - agent: crm-logger                     # sin `when` = dispara siempre

      - agent: triage-humano
        default: true                         # sólo si ningún `when` matcheó
```

### Qué dispara

Las reglas se evalúan **todas**, no en cascada. Para cada una:

| forma | cuándo dispara |
|---|---|
| con `when` | si la plantilla rinde `true`, `1` o `yes` |
| sin `when` ni `default` | siempre |
| con `default: true` | sólo si **ninguna regla `when` de esta cadena** dio true |

Las reglas sin `when` **no cuentan como match** a efectos del `default`. En el ejemplo de
arriba, con `score = 2`:

- `email-composer` no dispara (su `when` dio falso)
- `crm-logger` dispara (no tiene `when`)
- `triage-humano` dispara igual, porque ningún `when` matcheó

Puede haber a lo sumo una regla `default`, y no puede llevar `when` — declarar las dos cosas
es un error de arranque.

### `mode`: secuencial o paralelo

`mode` decide **cuándo** corren los eslabones que dispararon, no cuáles.

- `sequential` (default) — uno tras otro. Cada `when` se evalúa justo antes de despachar su
  eslabón, así que puede leer los resultados de los anteriores vía `steps`.
- `parallel` — a la vez. **Todas las guardas se evalúan de una sola vez antes de arrancar
  cualquier eslabón**, contra el output del agente anterior.

Esa diferencia tiene una consecuencia concreta: en `parallel`, un `when` que referencia a un
hermano sería siempre falso. En vez de dejarlo fallar callado, **el compilador lo rechaza al
arrancar** y te dice que uses `sequential`.

La regla `default` siempre corre como paso suelto después del fan-out, porque necesita las
guardas hermanas ya evaluadas para saber si le toca.

### Contexto disponible en `when` e `input`

| variable | contenido |
|---|---|
| `output.answer` | texto de la respuesta del agente inmediatamente anterior |
| `output.data` | objeto validado contra su `output_schema`, o `None` |
| `output.steps` | pasos de orquestación de ese agente |
| `trigger` | payload original: `query`, `session_id`, `context` |
| `steps` | outputs de los eslabones ya ejecutados, por nombre |
| `when` | resultado booleano de cada guarda ya evaluada, por nombre de paso |

`output` siempre refiere al **agente inmediatamente anterior en la cadena**, no al que la
inició. En `A → B → C`, el `when` de la cadena de B ve el `output` de B.

## `spec.output_schema`

Las condiciones sólo son confiables si hay algo estructurado sobre qué condicionar. Para eso
está `output_schema`.

```yaml
spec:
  output_schema:            # taquigrafía, igual que los `parameters` de las tools
    score:  {type: integer}
    urgent: {type: boolean}
```

También se acepta JSON Schema completo (`type: object` + `properties`), sin que nadie lo
reescriba por detrás.

**Cómo funciona.** Ningún provider del repo soporta `response_format` ni `json_schema` nativo,
así que la forma se pide por prompt: el runtime anexa al system prompt una instrucción para que
el modelo responda en prosa y cierre con un bloque ` ```json `. Después extrae ese bloque (el
último, si hay varios; o la respuesta entera si es JSON pelado), lo valida, y lo deja en
`result["data"]`.

**`answer` queda intacta**, con prosa y todo. `data` se agrega al lado.

**Un fallo de validación no corta la corrida.** `data` queda en `None`, el detalle va en
`data_error`, y todo queda registrado en el trace. Un `when` que dependa de ese campo fallará
ese eslabón con un mensaje que nombra la causa. Reintentar al agente porque emitió JSON
inválido no está implementado.

### Qué valida el validador

Es un validador propio, sin dependencias — `jsonschema` no está en las deps base y subirla
ahí obligaría a re-lockear tres proyectos uv y sumaría una dependencia al arranque de la
imagen de astromesh-os.

**Soporta:** `type` (`object`, `string`, `integer`, `number`, `boolean`, `array`, `null`),
`properties`, `required`, `enum`, `items`.

**Ignora, sin avisar:** `allOf`, `anyOf`, `oneOf`, `not`, `$ref`, `patternProperties`,
`additionalProperties`, `format`, `minimum`, `maximum`, `minLength`, `maxLength`, `pattern`,
`minItems`, `maxItems`, `uniqueItems`.

Ignorar en vez de rechazar es deliberado: un schema con `oneOf` sigue validando las partes que
el módulo entiende, en lugar de tumbar el agente entero por una keyword desconocida.

Un detalle que sí se respeta: **`true` no pasa como `integer`**, aunque en Python `bool` sea
subclase de `int`.

## Condiciones estrictas

Los pasos que emite el compilador se evalúan con `StrictUndefined`. Un `when` que referencia un
campo inexistente **falla ese eslabón con un mensaje explícito**, en vez de rendir vacío y
comportarse igual que una condición falsa.

Los workflows escritos a mano conservan el comportamiento histórico (silencioso) salvo que
declaren `strict_conditions: true` en el paso. Es la misma trampa que tenía el workflow de
ejemplo del repo, donde un `when` sobre `output.data.score` no podía dar true y caía al
`default` sin dejar rastro.

## Errores

| situación | comportamiento |
|---|---|
| el eslabón lanza excepción | aplica `retry`; agotado, se marca `error` y manda `on_error` |
| `on_error` sin declarar (default) | corta la cadena |
| `on_error: continue` | se registra el error y la cadena sigue |
| `on_error: <agente>` | salta a ese paso |
| timeout | igual que excepción; el mensaje nombra el `timeout_seconds` |
| `data` inválida | `data = None` + `data_error`; no corta nada por sí sola |
| ciclo | podado **en compilación**; error de arranque |
| `max_depth` excedido | error de arranque, nombrando la ruta completa |
| agente inexistente | error de arranque, nombrando agente y quién lo referencia |

En `parallel`, una rama que falla no tumba a sus hermanas si declaró `on_error: continue`.

**La `answer` del agente invocado se devuelve siempre**, cualquiera sea el estado de la cadena.
El fallo de un eslabón nunca invalida la respuesta que ya se produjo.

## Recursión

Si un eslabón declara su propia cadena, esa cadena también dispara. `A → B → C` emerge sin que
nadie tenga que dibujar el grafo completo.

Los frenos son dos y actúan **al compilar**, no en runtime:

- `max_depth` (default 5)
- detección de ciclos: si un agente ya está en la ruta actual, no se re-expande

Ambos producen un error de arranque con la ruta completa en el mensaje.

## La respuesta

```json
{
  "answer": "Lead calificado 8/10 — presupuesto confirmado...",
  "data":   {"score": 8, "urgent": true},
  "steps":  [],
  "trace":  {},
  "chain": {
    "run_id": "wf-9c2...",
    "status": "partial",
    "mode": "sequential",
    "links": [
      {"agent": "email-composer", "depth": 1, "via": null,
       "status": "success", "answer": "Enviado a ana@acme.com",
       "data": {"sent": true}, "duration_ms": 812},
      {"agent": "crm-logger", "depth": 1, "via": null,
       "status": "error", "error": "timeout tras 30s"}
    ]
  }
}
```

`chain.status`:

| valor | significado |
|---|---|
| `completed` | todos los eslabones que dispararon terminaron bien |
| `partial` | hubo errores pero la cadena siguió |
| `failed` | un eslabón cortó la cadena |

`links[].status` es `success`, `error` (con `error`) o `skipped` (con `reason`:
`condition_false`, `cycle`, `max_depth` o `upstream_stopped`).

**Los eslabones que no dispararon también aparecen**, con `reason: condition_false`. Es más
ruido, pero es la única forma de responder "¿por qué no se mandó el mail?" sin ir a leer el
trace.

Un agente sin `chain` devuelve `chain: null` y la forma de siempre.

## Observabilidad

Toda la cadena cuelga de **un solo árbol de trazas** y comparte la sesión de la corrida.

```
GET /v1/agents/{name}/chain
```

Devuelve el grafo expandido — agentes, condiciones, profundidades, `via`. Como es un artefacto
de tiempo de compilación, se puede pedir sin ejecutar nada. Devuelve `404` si el agente no
existe o no declara cadena.

## Fuera de alcance

- disparo asíncrono fire-and-forget (`chain_run_id` con polling)
- reintento del agente ante `output_schema` inválido
- cadenas que crucen nodos vía `PeerClient` — la coreografía distribuida es su propio diseño
- condiciones semánticas evaluadas por un LLM (`when_llm`)
- editor visual de cadenas en Forge; acá sólo está el endpoint que lo haría posible

## Ejemplo completo

`config/agents/sales-qualifier.agent.yaml` en este repo declara `output_schema` y una cadena
hacia `email-composer`. `config/workflows/example.workflow.yaml` cubre el mismo caso desde
afuera, con un `kind: Workflow`, para comparar los dos enfoques.
