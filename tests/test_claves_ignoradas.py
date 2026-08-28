"""Una clave de más en una tool no rompe nada — y ese es el problema.

`_build_agent` lee el tool_def con `.get()`, así que una clave que el runtime no
conoce se ignora **en silencio**: no falla, no avisa, no hace nada. Es el mismo
modo de fallar que hasta 0.35.0 tenía una tool de tipo no soportado, cerrado
entonces con un warning, y el mismo que costó un release en CLARUS — la
plantilla declaraba `confirm` contra un runtime 0.32.0 que no lo conocía, y
nadie se enteró hasta entrar al pod.
"""

import logging

import yaml

from astromesh.runtime.engine import AgentRuntime, claves_ignoradas


def test_una_clave_conocida_no_se_reporta():
    assert claves_ignoradas({"type": "client", "name": "x", "description": "d"}) == []


def test_una_clave_de_mas_se_reporta_ordenada():
    tool = {"type": "client", "name": "x", "zzz": 1, "aaa": 2}
    assert claves_ignoradas(tool) == ["aaa", "zzz"]


def test_confirm_nunca_se_reporta_acorralado_por_su_propio_aviso():
    # `confirm` mal puesto ya tiene un warning propio, que además dice POR QUÉ
    # no gatea. Reportarlo también acá lo duplicaría y taparía el bueno.
    assert claves_ignoradas({"type": "client", "name": "x", "confirm": ["a"]}) == []


def test_una_clave_valida_para_otro_tipo_se_reporta():
    # `connection` es de `integration`. En un `client` no hace nada, y que
    # exista en OTRO tipo es justo lo que la vuelve fácil de escribir por error.
    assert claves_ignoradas({"type": "client", "name": "x", "connection": "c"}) == ["connection"]


def test_description_en_una_integracion_se_reporta():
    # Caso real: la plantilla `atencion` de CLARUS le ponía `description` al
    # tool de PRAXIS. `register_integration_tool` usa `action.description` del
    # manifiesto de la integración (`core/tools.py:178`), así que la del YAML
    # nunca llegaba a ningún lado.
    assert claves_ignoradas(
        {"type": "integration", "name": "praxis", "connection": "c", "description": "d"}
    ) == ["description"]


def test_un_tipo_no_soportado_no_se_reporta():
    # Ese caso ya tiene su propio warning al final del loop, que además nombra
    # los tipos válidos. Sus claves son irrelevantes: la tool entera se ignora.
    assert claves_ignoradas({"type": "webhook", "name": "x", "loquesea": 1}) == []


async def test_el_aviso_sale_de_verdad_al_construir_el_agente(tmp_path, caplog):
    """El cableado: que el loop llame a la función, no sólo que exista."""
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "demo.agent.yaml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "astromesh/v1",
                "kind": "Agent",
                "metadata": {"name": "demo", "version": "1.0.0"},
                "spec": {
                    "model": {"provider": "openai", "name": "gpt-4o-mini"},
                    "tools": [
                        {
                            "type": "client",
                            "name": "pedir_algo",
                            "description": "d",
                            "confirmm": ["escribir"],
                        }
                    ],
                },
            }
        )
    )
    runtime = AgentRuntime(config_dir=str(config_dir))
    with caplog.at_level(logging.WARNING):
        await runtime.bootstrap()

    avisos = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    # El nombre del agente y el de la tool tienen que estar: sin eso, en un pod
    # con veinte agentes el aviso no dice dónde mirar.
    assert any("demo" in m and "pedir_algo" in m and "confirmm" in m for m in avisos), avisos
