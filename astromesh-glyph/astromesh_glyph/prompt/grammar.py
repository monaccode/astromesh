"""El texto que le enseña Glyph al modelo.

Es el único costo fijo por turno que agrega el lenguaje, y compite directamente
con el ahorro que produce. Cada línea que se agregue acá se paga en cada llamada
de cada agente: mantenerlo corto es un requisito, no una preferencia.
"""

GRAMMAR = """\
Respondé con UN programa Glyph dentro de un bloque ```glyph.
El runtime lo ejecuta entero sin volver a consultarte, así que escribí todos los
pasos de una vez en vez de pedir una acción por turno.

Sintaxis (esto es todo el lenguaje):

  nombre = capacidad(arg=valor)      # llamada; los argumentos van por nombre
  x = coleccion | where(campo == 1)  # filtra; varias condiciones se combinan con AND
  x = coleccion | top(3, by=campo)   # ordena descendente y trunca; asc=true invierte
  x = coleccion | map({a, b: otro})  # proyecta campos
  if condicion:                      # bloque indentado con 4 espacios
      y = capacidad()
  else:
      z = capacidad()
  return {x, y}                      # {x} equivale a {"x": x}

Sobre una colección podés leer .empty, .first y .count.
Sobre un registro, sus campos con punto: v.first.sku

Reglas:
- Cada nombre se asigna UNA sola vez. No reasignes.
- No hay bucles, funciones, imports ni aritmética.
- Las líneas independientes se ejecutan en paralelo: no encadenes sin necesidad.
- Sólo podés llamar a las capacidades listadas abajo.
"""
