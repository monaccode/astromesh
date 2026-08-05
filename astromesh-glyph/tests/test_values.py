import pytest

from astromesh_glyph.runtime.values import Collection, Record, unwrap, wrap


def test_wrap_turns_a_dict_into_a_record_with_dot_access():
    rec = wrap({"sku": "A1", "price": 10})
    assert isinstance(rec, Record)
    assert rec.sku == "A1"


def test_wrap_turns_a_list_into_a_collection():
    coll = wrap([{"a": 1}, {"a": 2}])
    assert isinstance(coll, Collection)
    assert coll.count == 2


def test_wrap_is_recursive():
    rec = wrap({"inner": {"deep": [1, 2]}})
    assert rec.inner.deep.count == 2


def test_scalars_pass_through_untouched():
    assert wrap(7) == 7
    assert wrap("x") == "x"
    assert wrap(None) is None


def test_missing_attribute_raises_attribute_error_naming_the_field():
    rec = wrap({"sku": "A1"})
    with pytest.raises(AttributeError, match="price"):
        _ = rec.price


def test_collection_empty_and_first():
    coll = wrap([{"a": 1}, {"a": 2}])
    assert coll.empty is False
    assert coll.first.a == 1
    assert wrap([]).empty is True


def test_first_of_an_empty_collection_is_none():
    assert wrap([]).first is None


def test_unwrap_returns_plain_python():
    coll = wrap([{"a": 1}])
    plain = unwrap(coll)
    assert plain == [{"a": 1}]
    assert type(plain) is list
    assert type(plain[0]) is dict
