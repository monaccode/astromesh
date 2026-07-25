import pytest

from astromesh.integrations.interpolation import (
    InterpolationError,
    interpolate,
    interpolate_structure,
)


def test_substitutes_named_placeholder():
    assert interpolate("/{owner}/items", {"owner": "acme"}, position="path") == "/acme/items"


def test_url_encodes_in_path():
    assert interpolate("/{name}", {"name": "a b&c"}, position="path") == "/a%20b%26c"


def test_query_values_are_not_pre_encoded():
    """httpx codifica los params al armar la URL; hacerlo acá daría doble codificación."""
    assert interpolate("{q}", {"q": "hola mundo"}, position="raw") == "hola mundo"
    assert interpolate("{q}", {"q": "name contains 'x'"}, position="raw") == "name contains 'x'"


def test_raw_position_does_not_encode():
    assert interpolate("{q}", {"q": "hola mundo"}, position="raw") == "hola mundo"


def test_non_string_values_are_stringified():
    assert interpolate("{limit}", {"limit": 25}, position="raw") == "25"
    assert interpolate("{flag}", {"flag": True}, position="raw") == "true"


def test_multiple_placeholders():
    out = interpolate("/{a}/x/{b}", {"a": "1", "b": "2"}, position="path")
    assert out == "/1/x/2"


def test_text_without_placeholders_passes_through():
    assert interpolate("/static/path", {}, position="path") == "/static/path"


def test_missing_argument_raises():
    with pytest.raises(InterpolationError, match="owner"):
        interpolate("/{owner}/items", {}, position="path")


def test_slash_rejected_in_path_by_default():
    with pytest.raises(InterpolationError, match="barra|slash"):
        interpolate("/{owner}/items", {"owner": "a/b"}, position="path")


def test_slash_allowed_when_opted_in():
    out = interpolate("/{repo}/x", {"repo": "a/b"}, position="path", allow_slash=True)
    assert out == "/a/b/x"


def test_traversal_rejected_even_with_allow_slash():
    with pytest.raises(InterpolationError, match="\\.\\."):
        interpolate("/{repo}/x", {"repo": "../../me/accounts"}, position="path", allow_slash=True)


def test_encoded_traversal_rejected():
    with pytest.raises(InterpolationError):
        interpolate("/{p}", {"p": "%2e%2e/secrets"}, position="path")


def test_double_encoded_traversal_rejected():
    with pytest.raises(InterpolationError):
        interpolate("/{p}", {"p": "%252e%252e/secrets"}, position="path")


def test_slash_is_fine_outside_the_path():
    assert interpolate("{q}", {"q": "a/b"}, position="raw") == "a/b"


def test_interpolate_structure_walks_nested_dicts_and_lists():
    out = interpolate_structure(
        {"a": "{x}", "b": [{"c": "{y}"}], "d": 7},
        {"x": "1", "y": "2"},
        allow_slash_params=set(),
    )
    assert out == {"a": "1", "b": [{"c": "2"}], "d": 7}


def test_interpolate_structure_keeps_whole_value_type_for_lone_placeholder():
    # Un body {"limit": "{limit}"} con limit=25 debe mandar 25, no "25".
    out = interpolate_structure({"limit": "{limit}"}, {"limit": 25}, allow_slash_params=set())
    assert out == {"limit": 25}
