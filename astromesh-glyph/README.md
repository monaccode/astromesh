# Glyph

Un lenguaje de acción para agentes LLM: el modelo emite **un programa** en vez de
N llamadas a tools, y el runtime lo ejecuta encadenando capacidades localmente.

El ahorro viene de eliminar round-trips, no de acortar sintaxis. Un loop ReAct de
seis iteraciones reenvía el system prompt, los schemas y el historial seis veces,
y ejecuta una tool por vuelta. Un programa Glyph hace todo eso en una, y las
sentencias independientes corren en paralelo.

## Ejemplo

```glyph
v = search_parts(make="Toyota", model="Corolla", year=2019, part="pastillas")

oem = v | where(kind == "oem") | top(3, by=rating)
alt = v | where(kind == "aftermarket", stock > 0) | top(3, by=price)

if oem.empty:
    eta = check_restock(sku=v.first.sku)

return {oem, alt, eta}
```

`oem` y `alt` no dependen entre sí, así que se ejecutan concurrentes.

## Instalación

**Todavía no está publicado en PyPI.** Por ahora se usa desde el monorepo de
Astromesh, donde el core lo declara como extra:

```bash
uv sync --extra glyph
```

El estado de la publicación y los pasos para cerrarla están en `docs/DEBT.md` del
repositorio.

## Uso

```python
from astromesh_glyph import build_system_block, compile_program, execute, extract_program, parse

block = build_system_block(provider.list_capabilities())   # va al prompt
program = parse(extract_program(model_response))
graph = compile_program(program, provider.list_capabilities())
result = await execute(graph, provider)
```

`provider` es cualquier objeto con estos dos métodos:

```python
def list_capabilities(self) -> list[CapabilitySpec]: ...
async def invoke(self, name: str, args: dict) -> Any: ...
```

Glyph no depende de ningún framework de agentes. Astromesh lo consume por
`pattern: glyph`, pero cualquier host puede implementar el protocolo.

## ¿Le conviene a tu agente?

No siempre. Glyph paga un costo fijo (el bloque de gramática en el prompt) y cobra
un beneficio que crece con el largo de la cadena: por debajo de ~5 tools sale más
caro que un loop ReAct, y con modelos de razonamiento explícito sale mucho más
caro. La decisión y cómo medirla están en
[`docs/GLYPH_GUIDE.md`](../docs/GLYPH_GUIDE.md) del repo de Astromesh.

## Alcance de v0.1.0

Cinco construcciones: asignación, llamada con argumentos por nombre, pipe
(`where` / `top` / `map`), `if/else`, `return`.

Deliberadamente afuera: bucles, funciones de usuario, imports, recursión,
aritmética. La ausencia de bucles se revisa cuando el benchmark muestre que hacen
falta.

## Errores y reparación

Un programa que no compila nunca llega a ejecutarse: el compilador valida las
capacidades y sus argumentos contra el catálogo, y devuelve el error con la línea.

Si una capacidad falla a mitad de la ejecución, el runtime corta y serializa el
estado parcial — variables ligadas, nodos ejecutados, el error — con
`PartialState.to_prompt()`, que le dice explícitamente al modelo qué efectos ya
ocurrieron para que no los repita.

## Licencia

Apache-2.0
