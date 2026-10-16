"""Los manifiestos del repo no declaran secciones que el motor ignore o rechace."""

import fnmatch
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1] / "config"
ARCHIVOS = sorted([*RAIZ.glob("agents/*.agent.yaml"), *RAIZ.glob("templates/*.template.yaml")])


def _spec(nodo):
    if isinstance(nodo, dict):
        if "spec" in nodo:
            return nodo["spec"]
        for v in nodo.values():
            if (r := _spec(v)) is not None:
                return r
    return None


@pytest.mark.parametrize("archivo", ARCHIVOS, ids=lambda p: p.name)
def test_secciones_del_manifiesto_tienen_efecto(archivo):
    spec = _spec(yaml.safe_load(archivo.read_text()))
    perms = spec.get("permissions") or {}
    assert set(perms) <= {"allowed_actions", "denied_actions"}
    nombres = [t["name"] for t in spec.get("tools", [])]
    for p in perms.get("allowed_actions", []):
        assert any(fnmatch.fnmatchcase(n, p) or n.startswith(p.rstrip("*")) for n in nombres), p
    sem = (spec.get("memory") or {}).get("semantic")
    assert sem is None or "embeddings" in sem
    t = (spec.get("orchestration") or {}).get("timeout_seconds")
    assert t is None or t >= 120
