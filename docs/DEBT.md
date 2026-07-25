# Deuda técnica conocida

Cosas que sabemos que hay que hacer, con el contexto para tomarlas sin
re-investigar. Cada entrada dice qué pasa, por qué se postergó y qué hay que
hacer para cerrarla.

---

## Adoptar ruff 0.16 (linter pineado con techo)

**Estado:** pendiente. Pin puesto el 2026-07-25.

### Qué pasa

`pyproject.toml` y `astromesh-orbit/pyproject.toml` tienen `ruff ... ,<0.16`.
El techo es deliberado y no hay que sacarlo sin hacer el trabajo de abajo.

ruff 0.16.0 amplió su **ruleset por defecto**. Este repo no declara
`[tool.ruff.lint] select`, así que hereda ese default entero. El salto de 0.15
a 0.16 produce, sin que cambie una sola línea de código:

| Paquete | Hallazgos nuevos | De ésos, auto-fixables |
|---|---|---|
| core (`astromesh/`, `tests/`) | 259 | 106 |
| `astromesh-orbit/` | 13 | 6 |

Reglas que aparecen: `I001` (orden de imports), `BLE001` (`except Exception`
sin acotar), `DTZ003` (`datetime.utcnow()`), `SIM102` (ifs anidados),
`UP035` (`typing.Callable` → `collections.abc`).

Verificado: 0.9.0, 0.12.0, 0.14.0 y 0.15.0 pasan limpio sobre `develop`. Sólo
0.16.0 falla.

### Por qué esto rompió CI solo

Es el hallazgo que importa, más que el linter en sí:

1. `uv.lock` está en `.gitignore` (línea 25).
2. CI corre `uv sync --extra all`, **sin lock**, así que resuelve dependencias
   frescas en cada corrida.
3. `ruff` estaba sin techo (`>=0.6.0`).

Resultado: el gate de CI se puso rojo **por calendario, no por commits**. La
última corrida verde de `develop` fue el 2026-07-21; después de eso cualquier
PR salía rojo tuviera el código que tuviera. El pin corta el síntoma.

**La clase entera del problema sigue abierta:** cualquier otra dependencia sin
techo puede repetir esto — pytest, httpx, pydantic. Versionar `uv.lock` (o usar
`uv sync --frozen` en CI) es la solución de fondo y es una decisión de política
de dependencias que hay que tomar aparte.

### Qué hay que hacer para cerrarla

1. Sacar el `<0.16` de los dos `pyproject.toml`.
2. `uv run ruff check --fix astromesh/ tests/` — resuelve 106 de 259.
3. Los ~153 restantes son manuales. Ojo con dos:
   - **`BLE001`**: varios `except Exception` son deliberados y load-bearing, no
     descuidos. En `astromesh/integrations/executor.py` atrapar todo *es el
     contrato*: `tool_fn` (`runtime/engine.py`) re-lanza lo que reciba y eso
     mata la corrida entera, así que un 404 de un proveedor externo no puede
     escapar. Esos van con `# noqa: BLE001` y la razón al lado, no
     "arreglados".
   - **`DTZ003`**: cambiar `utcnow()` por `now(tz=...)` cambia el valor que se
     serializa en trazas y memoria. Revisar consumidores antes.
4. Correr la suite completa: el cambio de imports puede alterar orden de
   inicialización.
5. PR separado. **No mezclar con trabajo de features** — es un diff de medio
   repo y revisarlo junto a otra cosa esconde ambos.

### Alternativa a considerar en ese PR

En vez de perseguir el default de ruff release a release, declarar
`[tool.ruff.lint] select = [...]` explícito. El gate deja de moverse solo
cuando el linter cambia de opinión, que es lo que pasó acá.
