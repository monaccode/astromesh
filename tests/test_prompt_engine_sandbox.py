"""El system prompt y el `when` de prefetch los escribe el tenant: sandbox (SSTI)."""

from types import SimpleNamespace

import pytest
from jinja2.exceptions import SecurityError

from astromesh.core.prompt_engine import PromptEngine

PAYLOADS = [
    "{{ ''.__class__ }}",
    "{{ ''.__class__.__mro__[1].__subclasses__() }}",
    "{{ ().__class__.__bases__[0].__subclasses__() }}",
    "{{ cycler.__init__.__globals__.os.popen('id').read() }}",
    "{{ joiner.__init__.__globals__ }}",
    "{{ lipsum.__globals__ }}",
    "{{ lipsum.__globals__['os'].popen('id').read() }}",
    "{{ self.__init__.__globals__ }}",
    "{{ ''.format.__globals__ }}",
    "{% for c in ''.__class__.__mro__[1].__subclasses__() %}{{ c }}{% endfor %}",
    "{{ memory.append('x') }}",
]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_un_payload_ssti_levanta_security_error(payload):
    with pytest.raises(SecurityError):
        PromptEngine().render(payload, {"memory": []})


@pytest.mark.parametrize(
    "expr",
    [
        "''.__class__.__mro__[1].__subclasses__()",
        "cycler.__init__.__globals__",
        "lipsum.__globals__['os']",
        "prefetch.rows.append(1)",
    ],
)
def test_un_when_inseguro_levanta(expr):
    with pytest.raises(SecurityError):
        PromptEngine().evaluate(expr, {"prefetch": {"rows": []}})


def test_un_template_normal_sigue_andando():
    tpl = (
        "{% for m in memory.conversation %}{{ m.role | upper }}: {{ m.content | trim }}\n"
        "{% endfor %}{{ prefetch.x.data.rows[0].nombre | default('?') }}"
        " {{ prefetch.x.data.rows | length }} {{ nada }}"
        "{% if nada %}X{% endif %}{% for i in nada %}Y{% endfor %}"
        "{{ prefetch.x.data.rows | tojson }}{{ ', '.join(['a', 'b']) }}"
    )
    memoria = {
        "conversation": [
            SimpleNamespace(role="user", content=" hola "),
            SimpleNamespace(role="assistant", content="buenas"),
        ]
    }
    prefetch = {"x": {"success": True, "data": {"rows": [{"nombre": "Ana"}]}}}
    salida = PromptEngine().render(tpl, {"memory": memoria, "prefetch": prefetch})
    assert salida == 'USER: hola\nASSISTANT: buenas\nAna 1 [{"nombre": "Ana"}]a, b'


def test_evaluate_de_un_when_sigue_andando():
    e = PromptEngine()
    ctx = {"prefetch": {"uno": {"success": True, "data": {"rows": []}}}}
    assert e.evaluate("prefetch.uno and prefetch.uno.success", ctx) is True
    assert not e.evaluate("prefetch.uno and prefetch.uno.data.rows", ctx)
    assert e.evaluate("sender_phone", {}) is None


async def test_la_corrida_falla_con_un_prompt_ssti(tmp_path, monkeypatch):
    """Un SecurityError al renderizar el system prompt tumba la corrida: no hay
    fallback al template crudo ni a un prompt parcial, y el modelo no se llama."""
    import copy

    from tests.test_prefetch_engine import AGENT, _runtime

    agente = copy.deepcopy(AGENT)
    agente["spec"]["prompts"]["system"] = "{{ cycler.__init__.__globals__.os }}"
    rt = await _runtime(tmp_path, monkeypatch, agente)
    llamado = []

    async def spy_route(*a, **kw):
        llamado.append(1)

    rt._agents["demo-agent"]._routers["default"].route = spy_route
    with pytest.raises(SecurityError):
        await rt._agents["demo-agent"].run(
            "hola", session_id="s1", connections={"demo_conn": {"access_token": "t"}}
        )
    assert llamado == []
