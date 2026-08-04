# Benchmark Glyph vs ReAct

## autolink-parts/cotizar-pastillas

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 1328 | 2898 (+118%) | 2894 (+118%) |
| Tokens de salida | 289 | 608 (+110%) | 608 (+110%) |
| Tokens totales | 1617 | 3506 (+117%) | 3502 (+117%) |
| Llamadas al modelo | 4 | 3 (-25%) | 3 (-25%) |
| Llamadas a tools | 5 | 0 (-100%) | 6 (+20%) |
| Latencia (ms) | 8329 | 12339 (+48%) | 12350 (+48%) |
| Respuesta correcta | sí | **no** | sí |
| Programas inválidos | — | 2 | 2 |

**REGRESIÓN** en glyph: responde mal donde ReAct acierta.

## support-agent/devolucion

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 790 | 841 (+6%) | 654 (-17%) |
| Tokens de salida | 132 | 170 (+29%) | 109 (-17%) |
| Tokens totales | 922 | 1011 (+10%) | 763 (-17%) |
| Llamadas al modelo | 4 | 2 (-50%) | 1 (-75%) |
| Llamadas a tools | 3 | 2 (-33%) | 2 (-33%) |
| Latencia (ms) | 5317 | 4192 (-21%) | 2282 (-57%) |
| Respuesta correcta | sí | **no** | **no** |
| Programas inválidos | — | 0 | 0 |

**REGRESIÓN** en glyph, glyph-datos: responde mal donde ReAct acierta.

## service-agent/agendar-reparacion

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 2767 | 3249 (+17%) | 3284 (+19%) |
| Tokens de salida | 231 | 1055 (+357%) | 358 (+55%) |
| Tokens totales | 2998 | 4304 (+44%) | 3642 (+21%) |
| Llamadas al modelo | 6 | 3 (-50%) | 3 (-50%) |
| Llamadas a tools | 6 | 0 (-100%) | 3 (-50%) |
| Latencia (ms) | 8539 | 18084 (+112%) | 8470 (-1%) |
| Respuesta correcta | **no** | **no** | **no** |
| Programas inválidos | — | 2 | 2 |

---

No hay umbral automático de aprobación: estos números se leen y se decide.
La tasa de programas inválidos es la que valida o refuta la apuesta de que
una sintaxis familiar se escribe bien sin entrenamiento previo.
