import pytest

from astromesh.integrations.handlers import HandlerError, load_handler


async def sample_handler(arguments, ctx):
    return {"ok": True}


def test_loads_callable_from_reference():
    fn = load_handler("python:tests.test_integration_handlers:sample_handler")
    assert fn is sample_handler


def test_rejects_reference_without_python_prefix():
    with pytest.raises(HandlerError, match="python:"):
        load_handler("tests.test_integration_handlers:sample_handler")


def test_rejects_malformed_reference():
    with pytest.raises(HandlerError):
        load_handler("python:no_colon_here")


def test_rejects_unknown_module():
    with pytest.raises(HandlerError, match="módulo|module"):
        load_handler("python:astromesh.nope.nope:fn")


def test_rejects_unknown_symbol():
    with pytest.raises(HandlerError, match="símbolo|symbol"):
        load_handler("python:tests.test_integration_handlers:no_existe")


def test_rejects_non_callable_symbol():
    with pytest.raises(HandlerError, match="invocable|callable"):
        load_handler("python:tests.test_integration_handlers:NOT_CALLABLE")


NOT_CALLABLE = 42
