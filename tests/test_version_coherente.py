"""El paquete declara su versión en dos lugares, y tienen que coincidir.

`pyproject.toml` los declara juntos a propósito, en `[tool.commitizen]`::

    version_files = [
        "pyproject.toml:version",
        "astromesh/__init__.py:__version__",
    ]

O sea que la herramienta de release ya sabe que son dos. Lo que faltaba era algo
que se pusiera rojo cuando no se la usa: la 0.44.0 se publicó bumpeando
`pyproject.toml` a mano, sin commit `chore(release)`, y `__init__.py` se quedó en
`0.43.0`. La imagen desplegada quedó diciendo dos versiones distintas de sí misma
según a quién se le pregunte:

    $ kubectl -n nexus-dev exec <pod> -- python -c "..."
    metadata:    0.44.0
    __version__: 0.43.0

No es cosmético. `GET /v1/system/status` reporta `__version__`
(`astromesh/api/routes/system.py:50`), así que cualquiera que verifique la
versión del runtime por HTTP —en vez de por `importlib.metadata`— obtiene la
vieja y concluye que el pod está por debajo del piso que necesita. Es
exactamente el modo de falla que el propio runtime persigue: una fuente que
responde con seguridad algo que no es cierto.
"""

import importlib.metadata

import astromesh


def test_version_del_modulo_coincide_con_la_del_paquete() -> None:
    """`__version__` y la metadata instalada son la misma versión.

    Si esto falla, alguien bumpeó una sola de las dos: correr `cz bump` en vez de
    editar `pyproject.toml` a mano, o emparejar el archivo que quedó atrás.
    """
    instalada = importlib.metadata.version("astromesh")

    assert astromesh.__version__ == instalada, (
        f"astromesh.__version__ dice {astromesh.__version__!r} y la metadata "
        f"instalada dice {instalada!r}. Los dos salen de `version_files` en "
        f"pyproject.toml y se bumpean juntos con `cz bump`."
    )
