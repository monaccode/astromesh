import pytest

from astromesh.errors import AgentConfigError
from astromesh.runtime.permisos import resolver_permisos

REG = ["praxis_crear_record", "praxis_leer_record", "kb_index", "kb_find", "lookup_company"]


def test_sin_permissions_no_restringe():
    assert resolver_permisos("a", REG, None) is None
    assert resolver_permisos("a", REG, {}) is None


def test_allowed_es_whitelist_con_comodines_fnmatch():
    r = resolver_permisos("a", REG, {"allowed_actions": ["praxis_*", "kb_index"]})
    assert r == {"praxis_crear_record", "praxis_leer_record", "kb_index"}


def test_denied_gana_sobre_allowed():
    r = resolver_permisos(
        "a", REG, {"allowed_actions": ["praxis_*"], "denied_actions": ["praxis_crear_*"]}
    )
    assert r == {"praxis_leer_record"}


def test_solo_denied_resta_de_todas():
    assert resolver_permisos("a", REG, {"denied_actions": ["kb_*"]}) == {
        "praxis_crear_record",
        "praxis_leer_record",
        "lookup_company",
    }


def test_match_es_case_sensitive():
    assert resolver_permisos("a", REG, {"allowed_actions": ["Praxis_*"]}) == frozenset()


def test_patron_sin_match_avisa_con_los_nombres_registrados(caplog):
    resolver_permisos("a", REG, {"allowed_actions": ["praxis", "lookup_company"]})
    msg = " ".join(r.getMessage() for r in caplog.records if r.levelname == "WARNING")
    assert "'praxis'" in msg
    assert "praxis_crear_record" in msg


def test_cero_tools_es_aviso_fuerte(caplog):
    assert resolver_permisos("a", REG, {"allowed_actions": ["nada"]}) == frozenset()
    assert any(r.levelname == "ERROR" and "sin tools" in r.getMessage() for r in caplog.records)


def test_sin_tools_registradas_no_avisa_cero_tools(caplog):
    resolver_permisos("a", [], {"allowed_actions": ["x"]})
    assert not any(r.levelname == "ERROR" for r in caplog.records)


def test_clave_desconocida_se_reporta_como_ignorada(caplog):
    assert resolver_permisos("a", REG, {"filesystem": {"read": ["./"]}}) is None
    assert any(
        "filesystem" in r.getMessage() and "no lee" in r.getMessage() for r in caplog.records
    )


@pytest.mark.parametrize("bad", [{"allowed_actions": "x"}, {"denied_actions": [1]}, ["x"]])
def test_tipo_invalido_es_error_de_config(bad):
    with pytest.raises(AgentConfigError, match="permissions"):
        resolver_permisos("a", REG, bad)
