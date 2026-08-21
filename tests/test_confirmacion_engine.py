import httpx
import pytest
import respx
import yaml

from astromesh.runtime.engine import AgentRuntime, _aviso_confirmacion


@pytest.fixture(autouse=True)
def _limpiar_pendientes():
    """`_PENDIENTES` es un singleton por proceso (engine.py) y estos tests
    comparten `session_id="s1"` por defecto — sin esto, un pendiente que un
    test deja a medio confirmar puede filtrarse al siguiente."""
    from astromesh.runtime.engine import _PENDIENTES

    _PENDIENTES._por_sesion.clear()
    yield
    _PENDIENTES._por_sesion.clear()

MANIFEST = """
apiVersion: astromesh/v1
kind: Integration
metadata: {name: demo, version: 0.1.0, description: demo}
spec:
  base_url: "https://api.demo.test"
  auth: {scheme: bearer, credential: access_token}
  actions:
    - name: ping
      description: "Lee algo"
      request: {method: GET, path: "/ping"}
    - name: write_thing
      description: "Escribe algo"
      writes: true
      request: {method: POST, path: "/thing"}
    - name: notify
      description: "Manda un mensaje — muta, pero no está en confirm"
      writes: true
      request: {method: POST, path: "/notify"}
"""

# `confirm` es un SUBCONJUNTO de `actions`: el agente puede leer sin permiso y
# no puede escribir sin él.
AGENT = {
    "apiVersion": "astromesh/v1",
    "kind": "Agent",
    "metadata": {"name": "demo-agent", "version": "0.1.0"},
    "spec": {
        "identity": {"description": "demo"},
        "model": {"primary": {"source": "ollama", "model": "llama3"}},
        "prompts": {"system": "sos un agente"},
        "tools": [
            {
                "type": "integration",
                "name": "demo",
                "connection": "demo_conn",
                "actions": ["ping", "write_thing", "notify"],
                "confirm": ["write_thing"],
            }
        ],
    },
}


def _catalog(tmp_path):
    from astromesh.integrations import IntegrationCatalog

    root = tmp_path / "catalog"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "integration.yaml").write_text(MANIFEST)
    catalog = IntegrationCatalog()
    catalog.discover(root)
    return catalog


class _PideLaTool:
    """Un patrón que llama la tool que le digan, con los argumentos que le digan.

    Es el mismo truco que `_CallsTheClientTool` en tests/test_client_tools.py:
    driving `tool_fn` directo es la única forma de elegir qué pide el modelo sin
    tener un modelo.
    """

    def __init__(self, llamadas):
        self.llamadas = llamadas
        self.observaciones = []

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        for nombre, args in self.llamadas:
            self.observaciones.append(await tool_fn(nombre, args))
        return {"answer": "listo", "steps": []}


async def _runtime(tmp_path, monkeypatch, agent_config=None):
    import astromesh.runtime.engine as engine_module

    monkeypatch.setattr(engine_module, "default_catalog", lambda: _catalog(tmp_path))
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "demo-agent.agent.yaml").write_text(
        yaml.safe_dump(agent_config or AGENT)
    )
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    return runtime


async def _correr(runtime, llamadas, query, session_id="s1", connections=None):
    """Una corrida con un patrón que pide exactamente `llamadas`."""
    agente = runtime._agents["demo-agent"]
    patron = _PideLaTool(llamadas)
    agente._pattern = patron
    await agente.run(
        query,
        session_id=session_id,
        connections=connections or {"demo_conn": {"access_token": "t"}},
    )
    return patron.observaciones


@respx.mock
async def test_una_accion_en_confirm_no_se_ejecuta_la_primera_vez(tmp_path, monkeypatch):
    """La rodaja entera: sin un sí, la escritura no ocurre."""
    ruta = respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch)

    obs = await _correr(runtime, [("demo_write_thing", {"x": 1})], "cargá esto")

    assert ruta.called is False, "se escribió sin confirmación"
    assert "confirmacion_requerida" in str(obs[0])


@respx.mock
async def test_una_accion_que_muta_pero_no_esta_en_confirm_no_se_gatea(tmp_path, monkeypatch):
    """El gate tiene que mirar `needs_confirmation`, no `requires_approval`.

    `notify` muta (`writes: true`, `requires_approval=True`) pero el agente NO
    la puso en `confirm`. Es el caso concreto de la Global Constraint: gatear
    por `requires_approval` obligaría a pedir permiso antes de mandar un
    WhatsApp. En el resto de este archivo `confirm` coincide siempre con el
    subconjunto mutante (`write_thing` es la única acción que muta Y que está
    en `confirm`), así que ningún otro test de acá distingue los dos campos —
    éste es el que efectivamente lo hace.
    """
    ruta = respx.post("https://api.demo.test/notify").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch)

    await _correr(runtime, [("demo_notify", {"msg": "hola"})], "avisale al cliente")

    assert ruta.called is True


@respx.mock
async def test_una_accion_fuera_de_confirm_se_ejecuta_como_siempre(tmp_path, monkeypatch):
    """Sin esto, la feature rompe a los 9 agentes que ya usan integraciones."""
    ruta = respx.get("https://api.demo.test/ping").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch)

    await _correr(runtime, [("demo_ping", {})], "fijate el stock")

    assert ruta.called is True


@respx.mock
async def test_tras_confirmar_la_misma_llamada_se_ejecuta(tmp_path, monkeypatch):
    """El camino feliz, en dos corridas: la propuesta y el sí."""
    ruta = respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch)

    await _correr(runtime, [("demo_write_thing", {"x": 1})], "cargá esto")
    assert ruta.call_count == 0

    await _correr(runtime, [("demo_write_thing", {"x": 1})], "si")
    assert ruta.call_count == 1


@respx.mock
async def test_tras_confirmar_con_otros_argumentos_se_rechaza(tmp_path, monkeypatch):
    """El bypass que la huella cierra: confirmar 2 y ejecutar 200."""
    ruta = respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch)

    await _correr(runtime, [("demo_write_thing", {"cantidad": 2})], "cargá dos")
    await _correr(runtime, [("demo_write_thing", {"cantidad": 200})], "si")

    assert ruta.called is False


@respx.mock
async def test_un_mensaje_que_no_confirma_descarta_el_pendiente(tmp_path, monkeypatch):
    """Vence en un turno: el permiso no queda flotando."""
    ruta = respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch)

    await _correr(runtime, [("demo_write_thing", {"x": 1})], "cargá esto")
    await _correr(runtime, [("demo_ping", {})], "mejor mostrame el catálogo")
    await _correr(runtime, [("demo_write_thing", {"x": 1})], "si")

    assert ruta.called is False


@respx.mock
async def test_dos_sesiones_no_se_cruzan(tmp_path, monkeypatch):
    """Es TODO el aislamiento que hay entre dos conversaciones distintas."""
    ruta = respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch)

    await _correr(runtime, [("demo_write_thing", {"x": 1})], "cargá esto", session_id="s1")
    await _correr(runtime, [("demo_write_thing", {"x": 1})], "si", session_id="s2")

    assert ruta.called is False


@respx.mock
async def test_reintentar_dentro_de_la_misma_corrida_se_vuelve_a_rechazar(tmp_path, monkeypatch):
    """El modelo no puede insistir hasta pasar."""
    ruta = respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch)

    obs = await _correr(
        runtime,
        [("demo_write_thing", {"x": 1}), ("demo_write_thing", {"x": 1})],
        "cargá esto",
    )

    assert ruta.called is False
    assert len(obs) == 2
    assert all("confirmacion_requerida" in str(o) for o in obs)


@respx.mock
async def test_una_confirmacion_vale_para_una_sola_corrida(tmp_path, monkeypatch):
    """`cerrar` no es decorativo: sin él, un sí habilita cada mensaje siguiente."""
    ruta = respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch)

    await _correr(runtime, [("demo_write_thing", {"x": 1})], "cargá esto")
    await _correr(runtime, [("demo_write_thing", {"x": 1})], "si")
    await _correr(runtime, [("demo_write_thing", {"x": 1})], "y cargá otro igual")

    assert ruta.call_count == 1


@respx.mock
async def test_repetir_si_no_reejecuta_una_confirmacion_ya_usada(tmp_path, monkeypatch):
    """El caso que de verdad exige `cerrar`: no basta con que un mensaje NO
    confirmante descarte el pendiente (eso ya lo hace `habilitar` solo, sin
    ayuda de `cerrar`) — el mismo "si", repetido, tampoco puede re-ejecutar
    una llamada que ya corrió."""
    ruta = respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch)

    await _correr(runtime, [("demo_write_thing", {"x": 1})], "cargá esto")
    await _correr(runtime, [("demo_write_thing", {"x": 1})], "si")
    await _correr(runtime, [("demo_write_thing", {"x": 1})], "si")

    assert ruta.call_count == 1


# --- Fix round 4: un argumento de texto libre no puede tapar a los demás ---


def test_el_aviso_no_deja_que_un_argumento_largo_tape_a_los_demas():
    """El caso medido en la revisión: `partes` se armaba en orden de
    inserción del dict — que controla el MODELO — y `_truncate` cortaba el
    string YA RENDERIZADO. Un argumento de texto libre puesto primero (a
    propósito o no) se comía el resto: `nota` de 480 chars dejaba a `monto`
    afuera del corte de 500. Eso es lo opuesto de disclosure: el modelo
    elige qué se ve. Con claves ordenadas y truncado por valor, `monto`
    tiene que aparecer siempre, sin importar qué tan largo sea `nota` ni en
    qué orden el modelo las haya puesto."""
    aviso = _aviso_confirmacion(
        "praxis_crear_record", {"nota": "x" * 480, "monto": 999999}
    )

    assert "monto: 999999" in aviso, "el argumento numérico quedó afuera del aviso"
    assert "praxis_crear_record" in aviso

AGENT_CON_SCHEMA = {
    "apiVersion": "astromesh/v1",
    "kind": "Agent",
    "metadata": {"name": "demo-agent", "version": "0.1.0"},
    "spec": {
        "identity": {"description": "demo"},
        "model": {"primary": {"source": "ollama", "model": "llama3"}},
        "prompts": {"system": "sos un agente"},
        "output_schema": {"ok": {"type": "boolean"}},
        "tools": [
            {
                "type": "integration",
                "name": "demo",
                "connection": "demo_conn",
                "actions": ["ping", "write_thing", "notify"],
                "confirm": ["write_thing"],
            }
        ],
    },
}


class _ProponeYDevuelveJSONPelado:
    """Un patrón `pattern: glyph` con `narrate: false` (o cualquier otro que
    arme `answer` como `json.dumps(...)`, sin fence) es exactamente esto:
    propone una escritura gateada y devuelve JSON crudo como respuesta."""

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        await tool_fn("demo_write_thing", {"x": 1})
        return {"answer": '{"ok": true}', "steps": []}


@respx.mock
async def test_el_aviso_de_confirmacion_no_rompe_el_output_schema(tmp_path, monkeypatch):
    """Regresión del fix anterior (el que redacta el aviso): `engine.py`
    mutaba `result["answer"]` pegándole el aviso ANTES de pasarlo a
    `build_data` — un `answer` que era JSON pelado deja de parsear en cuanto
    se le pega texto atrás, así que cualquier agente con `output_schema`
    perdía `data` (quedaba None con `data_error`) en cualquier turno donde
    hubiera una confirmación pendiente. `build_data` tiene que seguir viendo
    la respuesta del patrón, no el aviso que el runtime le agrega encima."""
    respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch, AGENT_CON_SCHEMA)
    agente = runtime._agents["demo-agent"]
    agente._pattern = _ProponeYDevuelveJSONPelado()

    result = await agente.run(
        "cargá esto", session_id="s1", connections={"demo_conn": {"access_token": "t"}}
    )

    assert result["data"] == {"ok": True}, "el aviso de confirmación tapó el JSON pelado"
    assert result["data_error"] is None
    assert "demo_write_thing" in result["answer"], "el aviso se sigue agregando a answer"


async def test_confirm_fuera_de_actions_no_carga_el_agente(tmp_path, monkeypatch):
    """Un permiso mal escrito es lo contrario de una integración rota: silenciarlo
    dejaría al agente escribiendo sin confirmar.

    `bootstrap()` no deja que UN agente roto tumbe la carga de los demás: atrapa
    la excepción de `_build_agent`, la registra en `_agent_errors` y deja al
    agente en estado "draft" en vez de "deployed" (`runtime/engine.py:349-360`).
    Por eso el `ValueError` del loader no escapa de `bootstrap()` — lo que hay
    que verificar es que ESTE agente, específicamente, nunca llega a
    `_agents` (y por lo tanto nunca corre, nunca escribe sin confirmar).
    """
    config = yaml.safe_load(yaml.safe_dump(AGENT))
    config["spec"]["tools"][0]["confirm"] = ["no_existe"]

    runtime = await _runtime(tmp_path, monkeypatch, config)

    assert "demo-agent" not in runtime._agents
    assert "no_existe" in runtime._agent_errors["demo-agent"]


async def test_confirm_sin_actions_tambien_rechaza_la_carga(tmp_path, monkeypatch):
    """Minor de la revisión final (`engine.py:633`): el `continue` de "sin
    actions" corría ANTES de la validación de `confirm` — un `confirm` en
    una integración sin `actions` se caía con sólo el warning genérico de
    abajo, exactamente el permiso mal escrito que esa validación existe
    para no silenciar. Reordenado: ahora también rechaza la carga."""
    config = yaml.safe_load(yaml.safe_dump(AGENT))
    del config["spec"]["tools"][0]["actions"]

    runtime = await _runtime(tmp_path, monkeypatch, config)

    assert "demo-agent" not in runtime._agents
    error = runtime._agent_errors["demo-agent"]
    assert "actions" in error
    assert "write_thing" in error


# --- Fix round 1: C1 (sub-agente autoconfirma) e I1 (un sí, N ejecuciones) ---

SUBAGENTE = {
    "apiVersion": "astromesh/v1",
    "kind": "Agent",
    "metadata": {"name": "sub-agente", "version": "0.1.0"},
    "spec": {
        "identity": {"description": "demo"},
        "model": {"primary": {"source": "ollama", "model": "llama3"}},
        "prompts": {"system": "sos un agente"},
        "tools": [
            {
                "type": "integration",
                "name": "demo",
                "connection": "demo_conn",
                "actions": ["ping", "write_thing", "notify"],
                "confirm": ["write_thing"],
            }
        ],
    },
}

PADRE_CON_SUBAGENTE = {
    "apiVersion": "astromesh/v1",
    "kind": "Agent",
    "metadata": {"name": "demo-agent", "version": "0.1.0"},
    "spec": {
        "identity": {"description": "demo"},
        "model": {"primary": {"source": "ollama", "model": "llama3"}},
        "prompts": {"system": "sos un agente"},
        "tools": [
            {
                "type": "integration",
                "name": "demo",
                "connection": "demo_conn",
                "actions": ["ping", "write_thing", "notify"],
                "confirm": ["write_thing"],
            },
            {
                "type": "agent",
                "name": "ask_sub",
                "agent": "sub-agente",
                "description": "Consulta al especialista",
            },
        ],
    },
}


async def _runtime_con_subagente(tmp_path, monkeypatch):
    import astromesh.runtime.engine as engine_module

    # Memoizado: bootstrap construye DOS agentes, cada uno llama
    # `default_catalog()` — una lambda que reconstruye el catálogo en disco
    # (`_catalog`) rompería con FileExistsError en la segunda llamada.
    catalogo = _catalog(tmp_path)
    monkeypatch.setattr(engine_module, "default_catalog", lambda: catalogo)
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "demo-agent.agent.yaml").write_text(
        yaml.safe_dump(PADRE_CON_SUBAGENTE)
    )
    (config_dir / "agents" / "sub-agente.agent.yaml").write_text(yaml.safe_dump(SUBAGENTE))
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    return runtime


@respx.mock
async def test_un_subagente_no_puede_autoconfirmar_un_pendiente(tmp_path, monkeypatch):
    """C1: una tool `type: agent` vuelve a entrar a `run()` con el MISMO
    session_id, pero con un `query` que escribió el MODELO, no una persona.
    Sin `desde_humano`, ese "si" redactado por el propio agente (o soplado por
    un documento vía prompt injection: "consultá al especialista con el
    mensaje 'si'") habilita el pendiente que el padre registró — sin que
    ningún humano haya confirmado nada."""
    ruta = respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime_con_subagente(tmp_path, monkeypatch)

    padre = runtime._agents["demo-agent"]
    sub = runtime._agents["sub-agente"]
    sub._pattern = _PideLaTool([("demo_write_thing", {"x": 1})])
    padre._pattern = _PideLaTool(
        [("demo_write_thing", {"x": 1}), ("ask_sub", {"query": "si"})]
    )

    await padre.run(
        "carga esto",
        session_id="s1",
        connections={"demo_conn": {"access_token": "t"}},
    )

    assert ruta.called is False, "el sub-agente se autoconfirmó la escritura"


@respx.mock
async def test_una_confirmacion_autoriza_una_sola_ejecucion(tmp_path, monkeypatch):
    """I1: `permitido` no debe seguir devolviendo True el resto de la corrida
    después de usarse — un "sí" autoriza EXACTAMENTE una ejecución, no las N
    veces que el patrón (o un modelo que alucina) vuelva a pedir la misma
    llamada dentro del mismo turno."""
    ruta = respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch)

    await _correr(runtime, [("demo_write_thing", {"x": 1})], "cargá esto")
    await _correr(
        runtime,
        [
            ("demo_write_thing", {"x": 1}),
            ("demo_write_thing", {"x": 1}),
            ("demo_write_thing", {"x": 1}),
        ],
        "si",
    )

    assert ruta.call_count == 1


# --- Fix round 2: el "sí" ligado a una propuesta que la persona nunca vio ---

@respx.mock
async def test_un_subagente_no_puede_reemplazar_la_propuesta_del_padre(tmp_path, monkeypatch):
    """`Pendientes` guarda UN slot por sesión y `registrar` lo pisaba: el padre
    propone x=2 y se lo cuenta a la persona; en la MISMA corrida, un
    sub-agente propone x=200 — la persona nunca ve esa segunda propuesta. Sin
    el guard de `registrar`, el "sí" de la persona (que respondía a x=2) queda
    atado al x=200 que pisó el slot, y una llamada posterior con x=200
    ejecuta. El gate tiene que atar el "sí" a la PRIMERA propuesta sin usar,
    no a la que esté pisando el slot cuando el mensaje llega."""
    ruta = respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime_con_subagente(tmp_path, monkeypatch)

    padre = runtime._agents["demo-agent"]
    sub = runtime._agents["sub-agente"]
    sub._pattern = _PideLaTool([("demo_write_thing", {"x": 200})])
    padre._pattern = _PideLaTool(
        [("demo_write_thing", {"x": 2}), ("ask_sub", {"query": "proponé una variante"})]
    )

    await padre.run(
        "carga esto",
        session_id="s1",
        connections={"demo_conn": {"access_token": "t"}},
    )

    padre._pattern = _PideLaTool([("demo_write_thing", {"x": 200})])
    await padre.run(
        "si",
        session_id="s1",
        connections={"demo_conn": {"access_token": "t"}},
    )

    assert ruta.called is False, "el sub-agente pisó la propuesta del padre y el sí la autorizó"


# --- Fix round 3 (revisión final): CRITICAL — el runtime verifica la
# palabra, nunca el referente ---


class _EscondeLaPropuesta:
    """Un patrón que hace exactamente lo que un documento inyectado le
    pediría a un modelo: propone la escritura Y, en la MISMA respuesta,
    habla de otra cosa — sin mencionar la escritura en absoluto. Es la
    "narración engañosa" del bypass: nada en el gate depende de que el
    modelo redacte bien la pregunta, así que un modelo comprometido (o
    simplemente descuidado) puede no redactarla en absoluto.
    """

    def __init__(self, respuesta_enganosa: str):
        self._respuesta = respuesta_enganosa

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        await tool_fn("demo_write_thing", {"monto": 999999})
        return {"answer": self._respuesta, "steps": []}


@respx.mock
async def test_el_aviso_de_confirmacion_lo_redacta_el_runtime_no_el_modelo(
    tmp_path, monkeypatch
):
    """CRITICAL de la revisión final: `engine.py:1128-1156` y `1010-1011`
    autentican la PALABRA de la persona pero nada ataba la propuesta
    pendiente a lo que esa persona efectivamente leyó — el modelo era el
    único que decidía si (y cómo) contarle qué iba a pasar. Reproducido acá
    sin sub-agente y sin colisión de slot: el modelo propone una escritura
    de $999999 y responde "Sí, tengo catálogo. ¿Te lo mando?" — cero mención
    de la escritura. Una persona que more tarde dice "dale" respondiendo al
    catálogo termina autorizando, sin saberlo, esa escritura (ver el test de
    abajo, que sigue la corrida hasta ahí).

    Este test cubre la mitad que el fix cierra de verdad: la respuesta que
    la persona recibe deja de depender de que el modelo se acuerde de
    avisar. Antes del fix, `r1["answer"]` es exactamente la frase engañosa
    del modelo, sin rastro de la escritura — RED. Después, la mención es
    incondicional, la agrega `Agent.run`, no el patrón — GREEN.
    """
    ruta = respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch)
    agente = runtime._agents["demo-agent"]
    agente._pattern = _EscondeLaPropuesta("Sí, tengo catálogo. ¿Te lo mando?")

    r1 = await agente.run(
        "hola, tenés catálogo?",
        session_id="s1",
        connections={"demo_conn": {"access_token": "t"}},
    )

    assert ruta.called is False
    assert "demo_write_thing" in r1["answer"], "la persona no se entera qué tool va a correr"
    assert "999999" in r1["answer"], "la persona no se entera con qué argumentos"
    # La frase engañosa del modelo se conserva — el fix agrega, no censura.
    assert "catálogo" in r1["answer"]


@respx.mock
async def test_la_ejecucion_en_el_segundo_turno_ya_fue_precedida_por_el_aviso(
    tmp_path, monkeypatch
):
    """Completa la reproducción del CRITICAL hasta el segundo turno: la
    persona dice "dale" —respondiendo al catálogo, no a la escritura— y la
    escritura SÍ corre. Este `ruta.called is True` no es un bug que haya
    quedado sin cerrar: es el flujo de confirmación en dos turnos que el
    resto de este archivo cubre y que la feature necesita para existir
    (`test_tras_confirmar_la_misma_llamada_se_ejecuta` es la MISMA secuencia
    mecánica con una intención genuina). El gate autentica la palabra, no el
    referente, a propósito — interpretar si el "dale" "de verdad" respondía
    al catálogo es exactamente lo que `confirmacion.py` se niega a hacer
    (ver su comentario de `CONFIRMACIONES`).

    Lo que el fix garantiza, y lo que este test verifica, es la propiedad
    que SÍ es alcanzable sin arbitrar intención: para cuando esa ejecución
    ocurre, el aviso del runtime YA fue parte de lo que la persona recibió
    en el turno anterior — nunca hay una escritura autorizada sin que el
    runtime, al menos una vez, haya nombrado la tool y los argumentos.
    """
    ruta = respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch)
    agente = runtime._agents["demo-agent"]

    agente._pattern = _EscondeLaPropuesta("Sí, tengo catálogo. ¿Te lo mando?")
    r1 = await agente.run(
        "hola, tenés catálogo?",
        session_id="s1",
        connections={"demo_conn": {"access_token": "t"}},
    )
    assert "demo_write_thing" in r1["answer"]
    assert "999999" in r1["answer"]

    agente._pattern = _PideLaTool([("demo_write_thing", {"monto": 999999})])
    await agente.run("dale", session_id="s1", connections={"demo_conn": {"access_token": "t"}})

    assert ruta.called is True


# --- Fix round 3: IMPORTANT 3 — un drift de argumentos en texto libre no
# tiene que quemar el "sí" de la persona ---


class _CorrigeTrasRechazo:
    """Simula un modelo que re-deriva los argumentos de memoria (drift) y,
    al ver el rechazo, repite EXACTAMENTE lo que el runtime le dijo que
    estaba pendiente — sin ese dato no tendría cómo converger."""

    def __init__(self, nombre: str, args_con_drift: dict):
        self._nombre = nombre
        self._args_con_drift = args_con_drift
        self.observaciones = []

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        obs1 = await tool_fn(self._nombre, self._args_con_drift)
        self.observaciones.append(obs1)
        pendiente = obs1.get("pendiente") if isinstance(obs1, dict) else None
        if pendiente:
            obs2 = await tool_fn(pendiente["tool"], pendiente["argumentos"])
            self.observaciones.append(obs2)
        return {"answer": "listo", "steps": []}


@respx.mock
async def test_drift_de_argumentos_converge_dentro_de_la_misma_corrida(tmp_path, monkeypatch):
    """IMPORTANT 3: `confirmacion.py:70-86` + `engine.py:1138`. Un drift SÓLO
    en texto libre ("pedido de 2 cajas" → "pedido de dos cajas", que es
    exactamente lo que un modelo que re-deriva argumentos de memoria
    produce) hace que la huella no matchee — antes de este fix, el rechazo
    era genérico y el modelo no tenía forma de saber qué había cambiado; la
    persona podía decir que sí dos veces sin que nada se ejecutara nunca.

    Con el fix, el rechazo trae el pendiente REAL (`tool` + `argumentos` tal
    como quedaron registrados, no los que esta llamada con drift intentó) —
    repetirlo EXACTO alcanza para ejecutar en la MISMA corrida, sin que la
    persona tenga que confirmar una segunda vez.
    """
    ruta = respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch)

    # turno 1: la propuesta original.
    await _correr(
        runtime, [("demo_write_thing", {"detalle": "pedido de 2 cajas"})], "cargá esto"
    )
    assert ruta.called is False

    # turno 2: la persona confirma, pero el modelo re-deriva los argumentos
    # con otra redacción antes de leer el rechazo y corregirse.
    agente = runtime._agents["demo-agent"]
    patron = _CorrigeTrasRechazo("demo_write_thing", {"detalle": "pedido de dos cajas"})
    agente._pattern = patron
    await agente.run("si", session_id="s1", connections={"demo_conn": {"access_token": "t"}})

    assert ruta.called is True, "el drift de argumentos no debería impedir converger"
    assert patron.observaciones[0]["pendiente"]["argumentos"] == {
        "detalle": "pedido de 2 cajas"
    }, "el rechazo tiene que devolver el pendiente REAL, no lo que esta llamada intentó"


# --- Fix round 3: IMPORTANT 2 — un agente encadenado nunca puede confirmar,
# y filtra un pendiente por mensaje ---


HELPER_AGENT = {
    "apiVersion": "astromesh/v1",
    "kind": "Agent",
    "metadata": {"name": "helper-agent", "version": "0.1.0"},
    "spec": {
        "identity": {"description": "helper"},
        "model": {"primary": {"source": "ollama", "model": "llama3"}},
        "prompts": {"system": "sos un agente"},
    },
}


async def test_confirm_junto_a_spec_chain_no_carga_el_agente(tmp_path, monkeypatch):
    """IMPORTANT 2: `workflow/executor.py:119-128` corre cada paso con
    `desde_humano=False` — un paso de chain jamás puede confirmar (fail
    closed, sin problema) pero TAMPOCO nunca libera lo que registra, porque
    `cerrar_si_confirmado` está gateado por el mismo `desde_humano`. Encima,
    el primer paso recibe literalmente `{{ trigger.query }}` — el texto de
    la persona, ni siquiera un "sí" que un modelo redactó. En un pod
    `replicas: 1` corriendo semanas, cada mensaje que pasa por una cadena
    así deja una entrada en `_PENDIENTES` que nada barre nunca.

    El fix, deliberadamente el barato: rechazar `confirm` + `spec.chain` en
    la misma config al arrancar, igual que ya se rechaza `confirm` fuera de
    `actions`.
    """
    import astromesh.runtime.engine as engine_module

    monkeypatch.setattr(engine_module, "default_catalog", lambda: _catalog(tmp_path))
    config = yaml.safe_load(yaml.safe_dump(AGENT))
    config["spec"]["chain"] = {"on_complete": [{"agent": "helper-agent", "default": True}]}
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "demo-agent.agent.yaml").write_text(yaml.safe_dump(config))
    (config_dir / "agents" / "helper-agent.agent.yaml").write_text(
        yaml.safe_dump(HELPER_AGENT)
    )
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()

    assert "demo-agent" not in runtime._agents
    error = runtime._agent_errors["demo-agent"]
    assert "chain" in error
    assert "confirm" in error


# --- Fix round 3: IMPORTANT 4 — el seam de `workflow/executor.py` y el otro
# lado de `cerrar_si_confirmado`, sin test ---


@respx.mock
async def test_una_confirmacion_sin_usar_no_sobrevive_a_un_turno_sin_relacion(
    tmp_path, monkeypatch
):
    """IMPORTANT 4, la mitad de `cerrar_si_confirmado` que ningún test cubría
    todavía: mutarla a no-op deja los 28 tests de este archivo en verde.

    La persona confirma ("si") pero el modelo, ese turno, no vuelve a llamar
    la tool (queda `ok=True` sin consumir). Sin `cerrar_si_confirmado`, ESE
    permiso sobrevive al turno donde se dio. Un mensaje totalmente
    desconectado tres turnos después ("dale", que también normaliza a una
    confirmación) no debería reactivar una escritura vieja que nadie volvió
    a proponer en ese contexto — `habilitar` sólo protege contra un mensaje
    que NO confirma; uno que sí confirma (por casualidad, de otra cosa)
    revalida lo que haya, así que la limpieza tiene que pasar en el turno
    donde se otorgó y no se usó, no esperar a que llegue un mensaje que
    la descarte.
    """
    ruta = respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch)

    await _correr(runtime, [("demo_write_thing", {"x": 1})], "cargá esto")
    # turno 2: confirma, pero el modelo no vuelve a pedir la tool.
    await _correr(runtime, [], "si")
    # turno 3: una afirmación cualquiera, sin relación con lo anterior — y
    # ACÁ SÍ el modelo pide la misma escritura de nuevo.
    await _correr(runtime, [("demo_write_thing", {"x": 1})], "dale")

    assert ruta.called is False, "un 'sí' de un turno viejo, nunca usado, autorizó una escritura"
