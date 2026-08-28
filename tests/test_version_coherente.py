"""El paquete declara su versión en dos lugares, y tienen que coincidir.

`pyproject.toml` los declara juntos a propósito, en `[tool.commitizen]`::

    version_files = [
        "pyproject.toml:version",
        "astromesh/__init__.py:__version__",
    ]

O sea que la herramienta de release ya sabe que son dos.

**Y el gate ya existía, en el lugar equivocado.** `release-pypi.yml:51-54` compara
las dos versiones y aborta con *"Version mismatch between pyproject and
__init__.py"*. Cuando se empujó el tag `v0.44.0`, ese gate **hizo su trabajo**: el
tag apunta a un commit con `pyproject.toml` en `0.44.0` y `__init__.py` en
`0.43.0`, así que el release abortó. **astromesh 0.44.0 no está publicada en
PyPI** — la última que sí está es la 0.43.0.

Lo que falló no fue la verificación: fue que **nadie miró que había fallado**, y
que el camino de la imagen es otro workflow, sin ese chequeo. Así quedó una
imagen `fulfarodev/astromesh:0.44.0` corriendo en producción cuyo paquete
equivalente no existe, y diciendo dos versiones distintas de sí misma según a
quién se le pregunte::

    $ kubectl -n nexus-dev exec <pod> -- python -c "..."
    metadata:    0.44.0
    __version__: 0.43.0

Este test no agrega una garantía que no existía: **mueve la que existía a un lugar
donde no se puede ignorar.** Un gate que sólo corre al empujar un tag falla en un
log que nadie abre; uno que corre con la suite falla en la cara del que rompió la
coherencia, antes de que haya tag, imagen ni deploy.

Por qué importa además de la higiene: `GET /v1/system/status` reporta
`__version__` (`astromesh/api/routes/system.py:50`), así que quien verifique la
versión del runtime por HTTP —en vez de por `importlib.metadata`— obtiene la
vieja y concluye que el pod está por debajo del piso que necesita. Es exactamente
el modo de falla que el propio runtime persigue: una fuente que responde con
seguridad algo que no es cierto.
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


def test_version_de_commitizen_coincide_con_la_del_paquete() -> None:
    """`[tool.commitizen] version` es la tercera copia, y la que nadie mira.

    No está en `version_files`, así que `cz bump` la escribe pero nada la
    verifica. Ya se atrasó dos veces (0.44.0 y 0.44.2). Importa porque `cz bump`
    la lee como versión ACTUAL: atrasada, calcula la próxima desde el número
    viejo y trata de emitir un tag que ya existe.
    """
    import tomllib
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    datos = tomllib.loads((raiz / "pyproject.toml").read_text())
    cz = datos["tool"]["commitizen"]["version"]

    assert cz == astromesh.__version__, (
        f"[tool.commitizen] version dice {cz!r} y astromesh.__version__ dice "
        f"{astromesh.__version__!r}. `cz bump` toma la de commitizen como la "
        f"versión actual: atrasada, el próximo bump re-emite un tag existente."
    )
