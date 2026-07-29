"""Cada entrada pública tiene que importar en un intérprete limpio.

La suite completa nunca detecta un import circular: para cuando corre el primer
test, `conftest` ya importó media docena de módulos y el orden quedó resuelto.
El ciclo que rompió la publicación de v0.38.0 —chain.compiler → workflow.models
→ workflow/__init__ → workflow.loader → chain.compiler— sólo se ve arrancando de
cero desde el módulo afectado, que es justo lo que hace el smoke test del
release contra TestPyPI.

Por eso cada caso corre en un subproceso propio: importar en el proceso del test
no probaría nada.
"""

import subprocess
import sys

import pytest

# Las mismas entradas que verifica el smoke test de .github/workflows/release-pypi.yml,
# más las que un consumidor toca primero.
ENTRADAS = [
    "import astromesh",
    "from astromesh.runtime.engine import AgentRuntime",
    "from astromesh.core.model_router import ModelRouter",
    "import astromesh.api.main",
    "from astromesh.workflow import WorkflowEngine",
    "from astromesh.workflow.loader import WorkflowLoader",
    "from astromesh.chain.compiler import compile_chain",
    "from astromesh.chain.naming import CHAIN_PREFIX",
]


@pytest.mark.parametrize("sentencia", ENTRADAS)
def test_importa_en_interprete_limpio(sentencia):
    proc = subprocess.run(
        [sys.executable, "-c", sentencia],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,  # el returncode es lo que se afirma; que no levante solo
    )
    assert proc.returncode == 0, f"`{sentencia}` falló en un intérprete limpio:\n{proc.stderr}"
