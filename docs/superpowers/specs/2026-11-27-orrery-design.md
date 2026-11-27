# Astromesh Orrery — Diseño

**Fecha:** 2026-11-27 · **Estado:** borrador, pendiente de aprobación (Juan Carlos).
**Decidido por Juan Carlos:** modelo híbrido (paneles de CLIs oficiales + paneles de agentes Astromesh,
con un supervisor Astromesh), consola, Rust, nombre **Astromesh Orrery** (binario `orrery`), "por donde
irías tú" para el cómo.

## 1. Intención

Un entorno de desarrollo de consola propio, al estilo herdr (multiplexor de agentes) + pi (agente de
código), donde **el cerebro de los agentes nativos es el runtime de Astromesh**. Un orrery es la maqueta
mecánica del sistema solar: muchos cuerpos moviéndose a la vez, coordinados.

**Por qué:** hoy el trabajo diario corre en Claude Code / Codex por separado. Queremos un solo lugar donde
verlos, coordinarlos y mezclarlos con agentes propios, y que ese mismo motor después corra sin pantalla en
pods chicos (CI, Agents as a Service).

**Éxito:**
- Es el entorno de desarrollo diario de Juan Carlos (en Windows 11, su máquina) en lugar de terminales sueltas.
- En un panel corre `claude` o `codex` **con la suscripción que ya paga**, sin pasar por API keys.
- En otro panel corre un agente Astromesh (YAML `astromesh/v1`) que lee, edita, corre comandos en el
  repo y ve/controla a los otros paneles.
- Un supervisor Astromesh reparte una tarea entre paneles y junta el resultado.
- `orrery run --headless` ejecuta el mismo flujo sin interfaz en un contenedor, para CI.

**Objetivos no buscados (non-goals):** editor de código propio (no es un IDE), interfaz web, reemplazar
a astromeshd o reescribir el loop de agentes en Rust, un marketplace de extensiones.

**Anti-objetivos (fracaso aunque funcione):**
- Usar credenciales de suscripción (OAuth de Claude Pro/Max, login de ChatGPT) desde nuestro código para
  llamar a los modelos. Las suscripciones **solo** se usan corriendo la CLI oficial, sin tocar su token.
- Que los pods dependan de una suscripción: en pods solo hay API keys o modelos locales.
- Que un agente controle otro panel saltándose la compuerta de confirmación de Astromesh.
- Duplicar en Rust lógica que ya vive en el core (routing de modelos, memoria, guardrails, traces).

## 2. Restricciones

- **Plataformas:** Windows 11 es la primera (ConPTY), Linux segunda (pods), macOS tercera.
- **Rust estable**, un binario. Interfaz con `ratatui` + `crossterm`; terminales con `portable-pty`
  (ConPTY en Windows) y `vt100`/`alacritty_terminal` para emular la pantalla del panel.
- **El runtime es Python** (`astromeshd` / la API FastAPI del core). Orrery le habla por la API que ya
  existe: `POST /v1/agents/{name}/run` y `WS /v1/ws/agent/{name}` (con `origen` `humano`/`agente`).
- Las tools de workspace (shell, editar, buscar) **no existen** en el core como builtins de código (solo
  `read_file`/`write_file`). Las aporta Orrery (ver §4.3).
- Repo nuevo: `monaccode/astromesh-orrery`, público como Code Mode (mi decisión, ver §7).

## 3. Enfoques considerados

| | Enfoque | A favor | En contra |
|---|---|---|---|
| **A (elegido)** | Binario Rust (interfaz, paneles, sesiones, servidor MCP de workspace) + `astromeshd` como cerebro de agentes nativos | Astromesh sigue siendo el cerebro; reusa routing, memoria, guardrails, Code Mode, Context, A2A; el mismo binario sirve para pods | Dos procesos (Rust + Python) y un protocolo entre ellos |
| B | Loop de agentes reescrito en Rust | Un binario, arranque instantáneo | Duplica el core y deja a Astromesh de lado: contradice el pedido |
| C | Plugins sobre pi o herdr | Lo más rápido para tener algo | No es propio; atado a su roadmap |

## 4. Diseño

### 4.1 Piezas

```
orrery (Rust)
 ├─ TUI ............ ratatui: layout de paneles/pestañas, tecla líder, barra de estado
 ├─ PaneHost ....... un PTY por panel: claude, codex, pi, shell, o un panel de agente nativo
 ├─ Session ........ guarda layout + comandos + cwd por proyecto (.orrery/session.toml), restaura
 ├─ Bus ............ eventos de paneles: salida, "esperando input", salida del proceso
 ├─ MCP server ..... tools de workspace + control de paneles (stdio/HTTP local)
 └─ Runtime link ... arranca/encuentra astromeshd, cliente REST/WS
astromeshd (Python, ya existe)
 └─ agentes YAML ... coder, supervisor, ... con tools MCP apuntando al servidor de Orrery
```

### 4.2 Tipos de panel

- **Panel de CLI** (`claude`, `codex`, `pi`, `shell`, cualquier comando): PTY crudo, como herdr. La CLI
  usa su propio login (la suscripción). Orrery solo lee la pantalla y escribe teclas.
- **Panel de agente nativo:** vista de chat propia (no PTY) que habla con `WS /v1/ws/agent/{name}`;
  muestra tokens, tool calls y confirmaciones pendientes.
- **Detección de "esperando"**: por panel de CLI, una heurística de pantalla por CLI (prompt visible,
  sin salida por N ms) que marca el panel como "te necesita". ACP (Agent Client Protocol) queda como
  mejora futura si sus adaptadores para Claude Code/Codex funcionan con login de suscripción — sin verificar.

### 4.3 Servidor MCP de Orrery

Orrery expone un servidor MCP local que los agentes Astromesh registran como tools MCP normales:

- **Workspace:** `read_file`, `write_file`, `edit_file` (reemplazo exacto), `list_files`, `grep`,
  `run_command` (con timeout, cwd confinado al proyecto).
- **Paneles:** `list_panes`, `read_pane(id, lines)`, `send_to_pane(id, text)`, `spawn_pane(cmd)`,
  `wait_pane(id, until)`.

Las tools que escriben o mandan input a otro panel se marcan como de escritura, y pasan por la compuerta
de confirmación de Astromesh: con `origen: agente` no se auto-confirman. Code Mode (`type: codemode`)
puede envolverlas cuando el agente usa muchas.

### 4.4 Supervisor

Un agente Astromesh (`config/agents/orrery-supervisor.agent.yaml`, se instala con Orrery) que recibe una
tarea, usa `spawn_pane`/`send_to_pane` para repartirla (p. ej. "Claude implementa, un agente nativo
revisa") y `read_pane`/`wait_pane` para juntar. Es un agente como cualquier otro: su modelo lo elige el
`ModelRouter` (API key o local), nunca la suscripción.

### 4.5 Modelos

- Paneles de CLI: lo que la CLI use (suscripción).
- Agentes nativos: providers del core (OpenAI-compat, LiteLLM → Anthropic/OpenAI/Gemini, Ollama, vLLM).
  Orrery no agrega providers; lo frontier llega por los que ya existen.

### 4.6 Headless / pods (fase 2)

`orrery run --headless --spec flow.toml`: sin interfaz; paneles de CLI se permiten solo si el contenedor
trae la CLI con su propia API key (p. ej. `ANTHROPIC_API_KEY` para `claude -p`), agentes nativos
normales; sale con código ≠ 0 si el flujo falla y deja un log/trace por panel. Imagen
`ghcr.io/monaccode/orrery` = binario + core Astromesh.

## 5. Fases

1. **v0 — multiplexor:** paneles PTY (claude, codex, shell), layout, tecla líder, sesiones por proyecto,
   detección de "esperando". Funciona en Windows 11.
2. **v1 — Astromesh adentro:** link con astromeshd (lo arranca si no corre), panel de agente nativo,
   servidor MCP de workspace + paneles, compuerta de confirmación, supervisor.
3. **v2 — headless:** modo sin interfaz, imagen de contenedor, ejemplo de CI con GitHub Actions.

Cada fase se planifica aparte; este documento cubre las tres para que v0 no cierre puertas.

## 6. Qué queda al implementador

Crates exactos de emulación de terminal, formato interno del bus, atajos de teclado concretos,
heurísticas de "esperando" por CLI, formato de `session.toml` y `flow.toml`.

## 7. Decisiones mías (a confirmar al leer)

- Repo público, licencia Apache-2.0 (igual al core y a Code Mode).
- **La compuerta para tools MCP es trabajo en el core (v1).** Hoy `confirm: [...]` solo lo lee
  `type: integration` (`runtime/engine.py`); `requires_approval` es metadato y no gatea. v1 incluye
  un cambio chico en el core: que `confirm` también aplique a `type: mcp`. Las confirmaciones
  pendientes se muestran en la barra de estado de Orrery y en el panel de agente que originó la
  corrida; las contesta la persona (`origen: humano`). El supervisor corre desde un panel abierto por
  la persona, así que sus pendientes se confirman ahí.
- **Headless:** sin persona no hay confirmación. `flow.toml` lista las tools pre-aprobadas para esa
  corrida; cualquier otra tool con `confirm` se rechaza (nunca se queda colgada).
- **Servidor MCP:** HTTP solo en `127.0.0.1`, puerto efímero, token aleatorio por arranque que Orrery
  inyecta al registrar el servidor en astromeshd. Una raíz de workspace por proyecto (directorio del
  `.orrery/`); rutas fuera de ella se rechazan. `run_command` corre shell arbitrario dentro de esa
  raíz, con timeout, y siempre está en `confirm` por defecto.
- **astromeshd:** Orrery lo lanza como proceso hijo (muere con Orrery) vía `uv run` en un entorno
  propio con una versión del core fijada; si ya hay uno corriendo en `ASTROMESH_URL`, lo usa.
- **`wait_pane(until)`** acepta `regex`, `idle_ms`, `exit` o `waiting` (la heurística); el
  supervisor usa `exit`/`regex` cuando puede, y `waiting` solo como último recurso.
- **Windows es compuerta de v0:** v0 no se da por terminado si claude/codex no andan bien en ConPTY.
- **Prueba de aceptación de v1:** desde un panel de supervisor, "Claude implementa X en un panel de
  CLI, un agente nativo revisa el diff y responde aprobado/cambios", de punta a punta en Windows.
- Windows primero porque es tu máquina de trabajo.
- Las tools de workspace viven en Orrery (MCP), no en el core, para que un pod tenga las mismas.
- El supervisor nunca usa la suscripción.
