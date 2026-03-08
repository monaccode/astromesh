import pytest


@pytest.fixture(params=["native", "python"])
def use_native(request, monkeypatch):
    """Parametrized fixture to test both native and Python backends."""
    if request.param == "python":
        monkeypatch.setenv("ASTROMESH_FORCE_PYTHON", "1")
    else:
        monkeypatch.delenv("ASTROMESH_FORCE_PYTHON", raising=False)
    return request.param
