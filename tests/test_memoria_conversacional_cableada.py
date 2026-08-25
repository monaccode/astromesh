"""El backend conversacional tiene que llegar al MemoryManager.

Sin este cableado `MemoryManager._conversation` queda en None y tanto
`build_context` como `persist_turn` no hacen NADA (`astromesh/core/memory.py`),
con los spans `memory_build`/`memory_persist` reportando `ok`. Un agente así se
vuelve a presentar en cada mensaje y no hay error en ningún lado.
"""

from astromesh.runtime.engine import AgentRuntime


def test_redis_declarado_construye_backend():
    spec = {
        "conversational": {
            "backend": "redis",
            "connection": {"url": "redis://astromesh-redis:6379"},
            "strategy": "sliding_window",
            "max_turns": 40,
        }
    }
    backend = AgentRuntime._conversation_backend("agente-x", spec)
    assert backend is not None, "un agente que declara redis tiene que salir con backend"
    assert type(backend).__name__ == "RedisConversationBackend"


def test_sin_memoria_declarada_no_hay_backend():
    assert AgentRuntime._conversation_backend("agente-x", {}) is None
    assert AgentRuntime._conversation_backend("agente-x", {"conversational": {}}) is None


def test_backend_no_soportado_degrada_con_warning(caplog):
    """No tira: un pedazo del manifiesto que este runtime no entiende no vuelve
    inválido al agente entero. Pero tiene que quedar en el log del pod."""
    import logging

    with caplog.at_level(logging.WARNING):
        backend = AgentRuntime._conversation_backend(
            "agente-x", {"conversational": {"backend": "postgres"}}
        )
    assert backend is None
    assert "postgres" in caplog.text
    assert "SIN memoria" in caplog.text


def test_redis_sin_url_degrada_en_vez_de_reventar_en_la_corrida(caplog):
    """`redis` lee `connection.url` sin default: sin esa clave el KeyError sale
    al construir el agente, no en el primer mensaje de un deudor."""
    import logging

    with caplog.at_level(logging.WARNING):
        backend = AgentRuntime._conversation_backend(
            "agente-x", {"conversational": {"backend": "redis"}}
        )
    assert backend is None
    assert "SIN memoria" in caplog.text


def test_el_agente_construido_lleva_el_backend(monkeypatch):
    """EL QUE IMPORTA: los de arriba prueban el helper, no que su resultado
    llegue al MemoryManager. Sacar `conversation=` de la construcción los deja
    pasar a todos — este es el único que se pone rojo.

    Espía la construcción del MemoryManager en vez de fabricar un AgentRuntime
    entero: lo que se afirma es el CABLEADO, y montar el resto del runtime sólo
    agregaría formas de que el test se rompa por motivos que no son éste.
    """
    from astromesh.runtime import engine as engine_mod

    visto = {}
    real = engine_mod.MemoryManager

    def espia(**kwargs):
        visto.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(engine_mod, "MemoryManager", espia)
    monkeypatch.setattr(AgentRuntime, "_build_role_routers", lambda self, spec: {})
    monkeypatch.setattr(AgentRuntime, "_resolve_rag", lambda self, spec: None)

    rt = AgentRuntime.__new__(AgentRuntime)
    try:
        rt._build_agent(
            {
                "metadata": {"name": "negociador"},
                "spec": {
                    "model": {"primary": {"provider": "openai_compat", "model": "kimi-k2.5"}},
                    "orchestration": {"pattern": "react"},
                    "prompts": {"system": "x"},
                    "memory": {
                        "conversational": {
                            "backend": "redis",
                            "connection": {"url": "redis://astromesh-redis:6379"},
                            "strategy": "sliding_window",
                            "max_turns": 40,
                        }
                    },
                },
            }
        )
    except Exception:
        # `_build_agent` sigue necesitando el resto del runtime; la memoria ya
        # se construyó antes de eso, que es lo único que este test mira.
        pass

    assert "conversation" in visto, (
        "el MemoryManager se construyó SIN `conversation`: build_context y "
        "persist_turn no van a hacer nada y el agente no va a recordar nada"
    )
    conv = visto["conversation"]
    assert conv is not None
    assert type(conv).__name__ == "RedisConversationBackend"


def test_un_extra_que_falta_degrada_en_vez_de_matar_al_agente(caplog, monkeypatch):
    """Un backend cuyo paquete no está instalado NO puede dejar al agente en
    `draft`: el resto de sus capacidades anda, y un agente muerto por una
    dependencia de memoria es una falla mucho más grande que un agente sin
    memoria. Pasó de verdad: al cablear el backend, la imagen del repo —que
    instala `--extra glyph` pero no `redis`— dejó de cargar un agente de
    `config/agents/` que hasta entonces arrancaba (sin memoria, en silencio).
    """
    import logging

    from astromesh.memory import factory

    def sin_paquete(_conv):
        raise ImportError("No module named 'redis'")

    monkeypatch.setattr("astromesh.runtime.engine.build_conversation_backend", sin_paquete)
    assert factory  # el módulo real sigue existiendo; se parchea el uso, no la fuente

    with caplog.at_level(logging.WARNING):
        backend = AgentRuntime._conversation_backend(
            "agente-x",
            {"conversational": {"backend": "redis", "connection": {"url": "redis://x"}}},
        )
    assert backend is None
    assert "SIN memoria" in caplog.text
    # El log tiene que decir QUÉ instalar, o no sirve de nada.
    assert "extra" in caplog.text.lower()
