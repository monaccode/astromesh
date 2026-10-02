# Juez de acciones (`spec.judge`) — capa de decisores, v1

**Fecha:** 2026-10-02
**Estado:** proyectado. Diseño en curso, **no aprobado y no implementado**. Una decisión
sigue abierta (ver «Decisión abierta»). No va al sitio público hasta que se implemente.
**Alcance:** core `astromesh` (`astromesh/runtime/`, `astromesh/decisores/` nuevo, schema del agente)

## Problema

Un agente ejecuta tool calls que decide un LLM. Hoy hay dos situaciones:

- **Tools con `confirm`:** no se ejecutan sin un "sí" escrito por la persona
  (`astromesh/runtime/confirmacion.py`).
- **Tools sin `confirm`:** se ejecutan directo, sin que nadie las mire.

Han aparecido modelos de decisión tipados, como **Jev** (TypeSafe AI). En lugar de texto,
devuelven valores estructurados con probabilidades calibradas, y dicen hacerlo en
milisegundos y a una fracción del costo de un LLM. La pregunta es dónde entra un modelo así
en Astromesh y para qué sirve. Este spec cubre la primera respuesta: un **juez** que, antes de
ejecutar una tool call, estima la probabilidad de que sea correcta.

## Decisiones tomadas

1. **Una capa propia de decisiones, separada del model router y de los patrones.**
   - **No va en el router.** El router elige quién genera texto, y un decisor no genera
     texto. Meterlo ahí repetiría el atajo de Centinela (`astromesh/providers/centinela.py`):
     un "chat falso" para pasar por `ProviderProtocol`, perdiendo las probabilidades, que son
     justamente lo que tiene valor.
   - **No es un patrón.** Un patrón (ReAct, Pipeline, Glyph…) es cómo razona el agente. Hay
     tres puntos donde se le puede preguntar a un decisor, y los tres valen para cualquier
     patrón:
     - **antes de razonar**, para enrutar;
     - **en lugar de razonar**, en cascada: si el decisor tiene confianza, responde él;
     - **antes de ejecutar una acción**, como juez.
2. **La v1 es el juez de acciones.** Las otras dos posiciones (enrutar y cascada) quedan para
   después. Sirve el mismo protocolo de decisor.
3. **Centinela, después.** Esta capa podría absorber a Centinela y eliminar su chat falso,
   pero eso queda fuera de la v1.
4. **El adaptador de Jev queda proyectado.** No hay API key ni documentación pública
   verificable, así que el adaptador se escribe contra el contrato conocido por prensa y queda
   marcado como **no verificado**. La v1 se prueba con un decisor falso y con uno local
   (un LLM al que se le pide una probabilidad).

## Decisión abierta: ¿el juez puede quitar fricción?

El gate de confirmación es **puro respecto del modelo**: el consentimiento lo da el texto de la
persona, nunca una interpretación de un modelo (`confirmacion.py`, docstring del módulo). Jev
es un modelo. La cascada que propone TypeSafe ("confianza > 0,9 → se ejecuta sola"), aplicada
a una tool con `confirm`, reemplazaría el "sí" humano por un modelo, que es exactamente lo que
ese gate existe para impedir.

**Opción A (recomendada): el juez solo agrega fricción, nunca la quita.**

| Tool | Confianza alta | Confianza media | Confianza baja |
|---|---|---|---|
| **Con `confirm`** | Pide el "sí" humano, como hoy | Pide el "sí" humano y el aviso incluye la duda del juez | No se propone. Vuelve al modelo como rechazo |
| **Sin `confirm`** | Se ejecuta, como hoy | **Pasa a pendiente:** pide un "sí" que hoy no se pedía | Rechazo al modelo |

Con A, el valor del juez está en **frenar acciones dudosas que hoy se ejecutan sin que nadie
las mire**, no en ahorrar confirmaciones. Mantiene intacta la propiedad del gate.

**Opción B:** que el juez pueda quitar fricción solo si el YAML lo declara por tool, por
ejemplo `auto_confirm_above: 0.95`. Así, un humano decide de antemano delegarle esa tool al
juez. Es defendible, pero abre una puerta que hoy está cerrada y obliga a auditar quién puede
escribir ese YAML (en Nexus, cualquiera con la API key del tenant).

El resto del spec asume **A**. Si se elige B, cambian solo la tabla de política y el schema.

## Diseño

### 1. Protocolo de decisor (`astromesh/decisores/base.py`)

Va separado de `ProviderProtocol`.

```python
class Pregunta(BaseModel):
    id: str
    tipo: Literal["choice", "score", "noul"]
    texto: str
    opciones: list[str] | None = None      # choice
    escala: tuple[int, int] | None = None  # score

class Respuesta(BaseModel):
    id: str
    valor: str | int | bool
    probabilidad: float                    # del valor elegido, 0..1
    distribucion: dict[str, float] | None = None

@runtime_checkable
class DecisorProtocol(Protocol):
    async def decidir(self, estado: str, preguntas: list[Pregunta]) -> list[Respuesta]: ...
    async def health_check(self) -> bool: ...
```

Para el juez, la v1 usa una sola pregunta `noul`: «¿Es correcta esta acción para lo que pidió
la persona?».

**Implementaciones de la v1:**

| Decisor | Para qué |
|---|---|
| `fake` | Tests. Devuelve probabilidades fijas o programadas por tool |
| `llm` | Un modelo del router existente al que se le pide JSON `{valor, probabilidad}`. No está calibrado, pero sirve para probar el flujo sin depender de un proveedor nuevo |
| `jev` | **Proyectado, no verificado.** Adaptador HTTP contra el contrato conocido (`state` hasta unos 32k tokens; preguntas `choice`, `score` o `noul`; respuesta con probabilidades). Queda detrás de un flag hasta probarlo contra el endpoint real |

### 2. Configuración en el YAML del agente

```yaml
spec:
  judge:
    decisor:
      source: jev            # fake | llm | jev
      model: jev-1.13.0      # con source: llm, un modelo del router (o un rol)
      endpoint: https://…
      api_key_env: JEV_API_KEY
      timeout_ms: 800
    tools: all               # o una lista de nombres de tool
    umbrales:
      alto: 0.9              # >= alto: confianza alta
      bajo: 0.5              # < bajo: confianza baja; en el medio, media
    on_error: pass           # pass | pending (ver «Fallas del decisor»)
```

- **Sin `spec.judge`**, el agente se comporta exactamente como hoy.
- El schema exige `bajo < alto`, los dos entre 0 y 1.
- `tools` con nombres que el agente no tiene es un error de carga, igual que `confirm` mal
  escrito.

### 3. Dónde engancha

El juez corre en `tool_fn` (`astromesh/runtime/engine.py`, alrededor de la línea 1582),
**antes** del gate de confirmación. Ese único punto lo comparten todos los patrones, Glyph
incluido (`glyph_pattern.py` recibe el mismo `tool_fn`).

```
tool_fn(name, args)
  ├─ ¿la tool está juzgada? → juez.decidir(estado, pregunta)
  │     ├─ baja    → devuelve {"error": "juez_rechazo", …} al modelo; no se ejecuta
  │     ├─ media   → se trata como needs_confirmation=True para ESTA llamada
  │     └─ alta    → sigue
  ├─ gate de confirmación existente (sin cambios)
  └─ ejecución
```

- **Confianza media** reutiliza el mecanismo de pendientes que ya existe: `huella`, `registrar`,
  `permitido` y `cerrar`. No hace falta código de confirmación nuevo. El aviso a la persona
  (`_aviso_confirmacion`) suma una línea con la duda del juez.
- **Si la persona confirma**, la próxima corrida llega con el "sí" y la misma huella.
  `permitido` es verdadero y **el juez no se vuelve a consultar para esa huella**. Sin esto,
  un juez inestable podría pedir confirmación dos veces por la misma acción.
- **Confianza baja** devuelve una observación con la probabilidad y un motivo corto, para que
  el modelo pueda corregirse o explicarle a la persona.

### 4. El estado que ve el juez

El texto que se manda como `state`, recortado al límite del decisor y armado en este orden de
prioridad:

1. la tool, su descripción y los argumentos propuestos;
2. el último mensaje de la persona;
3. los últimos turnos de la conversación;
4. un resumen del system prompt (identidad y reglas), no el prompt completo.

Las conexiones y los secretos nunca entran en el estado. Los argumentos van tal cual, porque
son lo que se juzga.

### 5. Interacciones con lo que ya existe

| Con | Regla |
|---|---|
| **`spec.chain`** | Un paso de chain corre con `desde_humano=False` y nunca puede confirmar (por eso hoy chain y `confirm` no conviven, `engine.py:_build_agent`). Dentro de una chain, la confianza **media se trata como baja**: rechazo, nunca pendiente. Si no, se repite la fuga de `_PENDIENTES` que ese chequeo evita |
| **`prefetch`** | No se juzga. Prefetch solo admite lecturas sin `confirm` (`runtime/prefetch.py`) y corre antes del modelo, así que no hay decisión del LLM que juzgar |
| **Tools `mode: propose`** (api, mcp) | No se ejecutan, se proponen. El juez puede anotar la propuesta con su probabilidad, pero no la bloquea: la ejecución ya es de otro |
| **Sub-agentes** (`type: agent`) | Se juzga la llamada al sub-agente como cualquier tool. Las tools del sub-agente las juzga el sub-agente, si declara `spec.judge` |

### 6. Fallas del decisor

Un decisor caído, lento (más de `timeout_ms`) o con una respuesta inválida **no puede dejar
al agente sin funcionar** sin que nadie lo decida. Por eso `on_error` existe:

- `pass` (por defecto): la llamada sigue como hoy, sin juez. Se registra en la traza y en una
  métrica. Con la opción A, eso es volver al comportamiento de hoy, no abrir nada nuevo.
- `pending`: la llamada pasa a pendiente. Es para agentes donde ejecutar sin juez es peor que
  molestar a la persona.

### 7. Observabilidad

- **Un span `judge`** por llamada, con decisor, probabilidad, banda (alta, media o baja),
  latencia y resultado (`ejecuta`, `pendiente` o `rechazo`).
- **Un evento de corrida `judge`**, para que la consola de Cortex y el stream de Nexus lo
  muestren junto a `tool_call` y `tool_result`.
- **Uso:** la llamada al decisor entra en `usage.by_model` con el rol `judge`, para que Nexus
  la cobre como a cualquier modelo.

### 8. Cómo se mide

Con A, la métrica no es "confirmaciones evitadas", sino:

- **frenos útiles:** acciones que el juez mandó a pendiente o rechazó y que la persona después
  no confirmó, o que estaban mal;
- **frenos de más:** acciones buenas que frenó;
- **latencia y costo agregados** por corrida.

Se calibra con un set de casos de agentes reales (CLARUS y Agora), corriendo el juez en
**modo sombra**: decide y registra, pero no actúa. Hay que agregar `modo: sombra` al schema
para eso. Recién con datos de sombra se fijan los umbrales por defecto.

## Pruebas

- **Unitarias del protocolo y de la política,** con el decisor `fake`: cada combinación de
  banda × con o sin `confirm` × dentro o fuera de chain.
- **El juez no se consulta dos veces** para una huella ya confirmada.
- **Fallas:** timeout, respuesta inválida y decisor caído, con `on_error: pass` y con
  `on_error: pending`.
- **Glyph:** el juez actúa sobre las llamadas de un programa igual que sobre las de ReAct.
- **Sin `spec.judge`,** la suite actual pasa sin cambios.
- **El adaptador de Jev solo tiene tests contra un servidor falso** hasta que haya key. Así
  queda marcado en el código y en el CHANGELOG cuando entre.

## Fuera de alcance de la v1

- La cascada en la entrada (el decisor responde en lugar del LLM) y el enrutamiento por
  decisor.
- Absorber a Centinela en esta capa.
- La opción B (`auto_confirm_above`), salvo que se decida lo contrario.
- Soporte en el builder visual de Cortex. Al principio, Cortex solo valida `spec.judge` en el
  schema y muestra el evento `judge` en la consola.

## Preguntas abiertas

1. **A o B** (ver arriba). Es la única que bloquea el plan.
2. **¿Juzgar todas las tools o solo las que escriben?** Juzgar lecturas cuesta latencia y
   aporta poco. Una opción es que `tools: all` signifique "todas las que escriben", con
   lecturas solo por lista explícita.
3. **¿Qué decisor `llm` usamos por defecto** para probar sin Jev: el `default` del agente o un
   rol `judge` propio?
4. **Jev:** conseguir acceso al early access (typesafe.ai) para verificar el contrato antes de
   sacar el adaptador de detrás del flag.

## Fuentes sobre Jev

Todas son de prensa. Ninguna es documentación de la API.

- Tom's Hardware, «TypeSafe AI's Jev offers an alternative to LLMs…»
- DEV, «How JEV works — the AI that decides instead of chatting»
- TechCrunch, 2026-09-18
- Towards Data Science, «Jev vs LLMs: when AI moves from generation to decision-making»
