# Deuda técnica conocida

Cosas que sabemos que hay que hacer, con el contexto para tomarlas sin
re-investigar. Cada entrada dice qué pasa, por qué se postergó y qué hay que
hacer para cerrarla.

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

## Versionar `uv.lock` (o `uv sync --frozen` en CI)

**Estado:** pendiente. Es una decisión de política de dependencias.

### Qué pasa

`uv.lock` está en `.gitignore` (línea 25) y CI corre `uv sync --extra all` sin
lock, así que **resuelve dependencias frescas en cada corrida**. El gate de CI
puede ponerse rojo por calendario, no por commits.

Ya pasó una vez: ruff saltó de 0.15 a 0.16 solo, amplió su ruleset por defecto y
dejó rojo cualquier PR abierto después del 2026-07-21, con el código intacto.
Ese caso puntual está cerrado (ahora el ruleset es explícito), pero **la clase
entera del problema sigue abierta** para todas las demás dependencias: pytest,
httpx, pydantic, fastapi. Cualquiera puede cambiar un default, endurecer una
validación o deprecar algo, y romper CI sin que nadie haya tocado nada.

### Qué hay que decidir

Versionar `uv.lock` da builds reproducibles y actualizaciones deliberadas (un PR
que dice "subo httpx"), a cambio de mantener el lock. La alternativa es seguir
resolviendo fresco y aceptar que CI es también un canario de upstream — que es
útil, pero entonces el fallo hay que poder distinguirlo del fallo propio.

No lo decidimos acá porque afecta a todo el repo y a cómo se releasea, no sólo
al linter.
