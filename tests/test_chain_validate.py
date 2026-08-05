"""Validador mínimo de JSON Schema, sin dependencias externas."""

from astromesh.chain.validate import validate


def test_objeto_valido_no_da_errores():
    schema = {
        "type": "object",
        "properties": {"score": {"type": "integer"}, "urgent": {"type": "boolean"}},
        "required": ["score"],
    }
    assert validate({"score": 8, "urgent": True}, schema) == []


def test_campo_requerido_faltante():
    schema = {"type": "object", "properties": {"score": {"type": "integer"}}, "required": ["score"]}
    errores = validate({}, schema)
    assert len(errores) == 1
    assert "score" in errores[0]


def test_tipo_incorrecto():
    schema = {"type": "object", "properties": {"score": {"type": "integer"}}}
    errores = validate({"score": "ocho"}, schema)
    assert len(errores) == 1
    assert "score" in errores[0]
    assert "integer" in errores[0]


def test_bool_no_es_integer():
    """En Python bool es subclase de int; el validador no debe dejarlo pasar."""
    schema = {"type": "object", "properties": {"score": {"type": "integer"}}}
    assert validate({"score": True}, schema) != []


def test_integer_es_number_valido():
    schema = {"type": "object", "properties": {"ratio": {"type": "number"}}}
    assert validate({"ratio": 3}, schema) == []


def test_enum():
    schema = {"type": "object", "properties": {"tier": {"type": "string", "enum": ["a", "b"]}}}
    assert validate({"tier": "a"}, schema) == []
    assert validate({"tier": "z"}, schema) != []


def test_array_con_items():
    schema = {
        "type": "object",
        "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
    }
    assert validate({"tags": ["x", "y"]}, schema) == []
    errores = validate({"tags": ["x", 3]}, schema)
    assert len(errores) == 1
    assert "tags[1]" in errores[0]


def test_objeto_anidado():
    schema = {
        "type": "object",
        "properties": {
            "lead": {
                "type": "object",
                "properties": {"score": {"type": "integer"}},
                "required": ["score"],
            }
        },
    }
    assert validate({"lead": {"score": 8}}, schema) == []
    errores = validate({"lead": {}}, schema)
    assert "lead.score" in errores[0]


def test_null_permitido():
    schema = {"type": "object", "properties": {"nota": {"type": "null"}}}
    assert validate({"nota": None}, schema) == []


def test_raiz_no_es_objeto():
    schema = {"type": "object", "properties": {}}
    errores = validate(["no", "soy", "objeto"], schema)
    assert len(errores) == 1


def test_keywords_no_soportadas_se_ignoran():
    """oneOf/allOf/format/minimum se ignoran: no rompen, no validan."""
    schema = {
        "type": "object",
        "properties": {"score": {"type": "integer", "minimum": 10, "format": "int32"}},
        "oneOf": [{"required": ["score"]}],
    }
    assert validate({"score": 3}, schema) == []


def test_propiedad_extra_se_permite():
    schema = {"type": "object", "properties": {"score": {"type": "integer"}}}
    assert validate({"score": 8, "extra": "libre"}, schema) == []


def test_varios_errores_a_la_vez():
    schema = {
        "type": "object",
        "properties": {"a": {"type": "integer"}, "b": {"type": "string"}},
        "required": ["a", "b", "c"],
    }
    errores = validate({"a": "no", "b": 3}, schema)
    assert len(errores) == 3  # a mal tipo, b mal tipo, c faltante


def test_sin_schema_no_valida_nada():
    assert validate({"lo": "que sea"}, None) == []
    assert validate({"lo": "que sea"}, {}) == []
