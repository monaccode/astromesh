"""Extracción y validación de `data` desde la respuesta en prosa de un agente."""

from astromesh.chain.output import (
    build_data,
    extract_data,
    normalize_output_schema,
    schema_prompt_block,
)

SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "integer"}, "urgent": {"type": "boolean"}},
    "required": ["score"],
}


def test_normaliza_taquigrafia():
    """La misma taquigrafía que usan los `parameters` de las tools."""
    normalizado = normalize_output_schema({"score": {"type": "integer"}})
    assert normalizado == {"type": "object", "properties": {"score": {"type": "integer"}}}


def test_json_schema_completo_pasa_intacto():
    assert normalize_output_schema(SCHEMA) == SCHEMA


def test_none_pasa_como_none():
    assert normalize_output_schema(None) is None


def test_extrae_bloque_json_cercado():
    answer = (
        'Analicé el lead.\n\n```json\n{"score": 8, "urgent": true}\n```\n\nRecomiendo contactar.'
    )
    assert extract_data(answer) == {"score": 8, "urgent": True}


def test_usa_el_ultimo_bloque_json():
    """Si el modelo razonó con un borrador antes, vale el último."""
    answer = '```json\n{"score": 1}\n```\ncorrijo:\n```json\n{"score": 9}\n```'
    assert extract_data(answer) == {"score": 9}


def test_bloque_cercado_sin_etiqueta_de_lenguaje():
    answer = 'listo:\n```\n{"score": 5}\n```'
    assert extract_data(answer) == {"score": 5}


def test_respuesta_entera_es_json_pelado():
    assert extract_data('{"score": 7}') == {"score": 7}


def test_sin_json_devuelve_none():
    assert extract_data("No pude determinar el score.") is None


def test_json_invalido_devuelve_none():
    assert extract_data('```json\n{"score": no-soy-json}\n```') is None


def test_answer_vacia_devuelve_none():
    assert extract_data("") is None


def test_build_data_camino_feliz():
    answer = 'Calificado.\n```json\n{"score": 8, "urgent": true}\n```'
    data, error = build_data(answer, SCHEMA)
    assert data == {"score": 8, "urgent": True}
    assert error is None


def test_build_data_sin_schema_no_hace_nada():
    data, error = build_data('```json\n{"score": 8}\n```', None)
    assert data is None
    assert error is None


def test_build_data_sin_bloque_json():
    data, error = build_data("Prosa sin JSON.", SCHEMA)
    assert data is None
    assert "no se encontró" in error


def test_build_data_falla_validacion():
    answer = '```json\n{"urgent": true}\n```'
    data, error = build_data(answer, SCHEMA)
    assert data is None
    assert "score" in error


def test_prompt_block_menciona_los_campos():
    bloque = schema_prompt_block(SCHEMA)
    assert "score" in bloque
    assert "json" in bloque.lower()
