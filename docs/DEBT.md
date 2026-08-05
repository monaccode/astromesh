# Deuda técnica conocida

Cosas que sabemos que hay que hacer, con el contexto para tomarlas sin
re-investigar. Cada entrada dice qué pasa, por qué se postergó y qué hay que
hacer para cerrarla.

---

## `astromesh-glyph` no se publica todavía — ABIERTA desde el 2026-08-04

**Qué pasa:** el paquete está listo y tageado (`glyph-v0.1.0`), pero el workflow
`release-glyph.yml` falla al publicar:

```
invalid-publisher: valid token, but no corresponding publisher
```

PyPI y TestPyPI configuran el *trusted publisher* **por proyecto**, y
`astromesh-glyph` es un paquete nuevo que nunca se registró. Que el core tenga el
suyo no se hereda.

**Por qué se postergó:** registrar el publisher es un paso manual en la web de las
dos cuentas, y crear un paquete público bajo la organización es una decisión que no
corresponde tomar de apuro.

**Consecuencia mientras esté abierta:** el extra `glyph` del core **no resuelve
fuera del monorepo**. `pip install astromesh[glyph]` falla, porque pip ignora
`[tool.uv.sources]`. Dentro del monorepo funciona con `uv sync --extra glyph`.

**Consecuencia asumida en v0.39.0:** se decidió publicar el core igual, así que
desde v0.39.0 **`pip install astromesh[all]` no resuelve** — `all` incluye `glyph`,
y `glyph` apunta a un paquete que no existe en el índice. No es sólo que el extra
nuevo no ande: rompe una instalación que antes funcionaba, para usuarios que no
tienen nada que ver con Glyph. Mientras tanto hay que instalar los extras por
nombre.

Se evaluó sacar `glyph` de `all` para evitarlo y se descartó a propósito; queda
anotado acá porque quien encuentre el fallo merece saber que fue una decisión y no
un descuido.

**Qué hay que hacer para cerrarla:**

1. En https://test.pypi.org/manage/account/publishing/ y en
   https://pypi.org/manage/account/publishing/, agregar un *pending publisher*:

   | Campo | Valor |
   |---|---|
   | PyPI Project Name | `astromesh-glyph` |
   | Owner | `monaccode` |
   | Repository name | `astromesh` |
   | Workflow name | `release-glyph.yml` |
   | Environment name | `testpypi` en TestPyPI, `pypi` en PyPI |

   Son los mismos valores que ya tiene `astromesh-orbit`, cambiando el nombre del
   proyecto y del workflow.

2. `gh run rerun <id>` del workflow fallido — el tag ya está pusheado, no hace
   falta retagear.

3. Verificar que quede en PyPI, y recién ahí tagear `v0.39.0` para el core.

4. Revertir las notas de "todavía no publicado" en `docs/GLYPH_GUIDE.md`,
   `docs-site/src/content/docs/configuration/glyph.md`,
   `astromesh-glyph/README.md` y los dos warnings de
   `astromesh/runtime/engine.py`.

---

## ~~Adoptar ruff 0.16~~ — CERRADA el 2026-07-25

Se adoptó 0.16 y se quitó el techo `<0.16` de los dos `pyproject.toml`.

**Cómo quedó:** el ruleset ya no se hereda del default de ruff. Los dos paquetes
declaran `[tool.ruff.lint] select` explícito, así que una versión nueva del
linter no puede ampliar el gate sola — que es lo que había roto CI. Para
endurecerlo hay que editar esa lista a propósito.

Qué se saneó: 259 hallazgos en el core y 13 en Orbit bajo el default de 0.16;
con el `select` declarado el total real fue de 437 en el core (las categorías
que se sumaron a mano: `B`, `RET`, `N`, `PLW`, `ASYNC` completo).

Lo que **no** entró al gate, y por qué está escrito al lado de cada exclusión en
`pyproject.toml`: `PLW0603` (el singleton de módulo con `set_runtime()` es la
arquitectura documentada en CLAUDE.md), `N818` (renombrar `CredentialMissing` y
`InvalidToolParameters` toca 45 referencias, entre ellas una spec aprobada — es
un cambio de nombres públicos y se decide aparte), `E501` (lo cubre el
formateador), y `D`/`S` completo/`PLC`/`PLR`/`COM`/`ARG`/`SLF`/`TRY` completo
(churn alto sin señal: `S` completo son 2097 hallazgos, `D` son 1990).

Los `except Exception` deliberados llevan `# noqa: BLE001` con la razón al lado.
No son descuidos: en el ejecutor de integraciones, en las tools, en los health
checks y en el gossip del mesh, atrapar todo **es** el contrato.

---

## ~~Versionar `uv.lock`~~ — CERRADA el 2026-07-25

`uv.lock` salió de `.gitignore` y se versionan los cuatro: la raíz,
`astromesh-node/`, `astromesh-cli/` y `astromesh-orbit/`. Cada uno es un
proyecto uv independiente con su propia resolución.

CI pasó a `uv sync --locked` en los seis sitios que instalaban dependencias
(`ci.yml` ×4, `centinela-endpoints.yml`, `centinela-sync.yml`). `--locked`, no
`--frozen`: `--frozen` usaría el lock a ciegas, mientras que `--locked` **falla**
si alguien editó un `pyproject.toml` sin re-lockear, con un mensaje que dice qué
correr. Verificado plantando una dependencia extra sin re-lockear: el sync corta
con "The lockfile at `uv.lock` needs to be updated".

Los locks son universales (cubren win32/no-win32 y Python 3.12/3.13/3.14), así
que el mismo archivo sirve para la matriz ubuntu/macos/windows.

**Cómo se actualiza una dependencia ahora:** `uv lock` en el directorio del
proyecto que cambió, y el lock va commiteado junto al cambio de `pyproject.toml`.
Para subir una en particular: `uv lock --upgrade-package <nombre>`.

**Lo que esto cambia de fondo:** el gate de CI ya no puede romperse por
calendario. Una dependencia nueva entra sólo cuando alguien la mete en un commit,
y ese commit se puede revisar y revertir. El precio es que las actualizaciones
son ahora un acto explícito — si nadie corre `uv lock`, el repo se queda quieto.
Conviene revisar los locks cada tanto, o poner un bot que abra el PR.

**No afecta a `astromesh-os`:** su `build-deb.sh` instala con pip, que ignora
`uv.lock` por completo. Las dos restricciones de esa integración siguen igual
(ver la nota de `runtime.pin`).
