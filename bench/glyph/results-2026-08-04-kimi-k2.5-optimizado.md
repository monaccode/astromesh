# Benchmark Glyph vs ReAct

## autolink-parts/cotizar-pastillas

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 531 | 969 (+82%) | 611 (+15%) |
| Tokens de salida | 578 | 7028 (+1116%) | 2249 (+289%) |
| Tokens totales | 1109 | 7997 (+621%) | 2860 (+158%) |
| Llamadas al modelo | 2 | 2 (+0%) | 1 (-50%) |
| Llamadas a tools | 1 | 5 (+400%) | 1 (+0%) |
| Latencia (ms) | 14791 | 152903 (+934%) | 51103 (+246%) |
| Respuesta correcta | sí | sí | sí |
| Programas inválidos | — | 0 | 0 |

## support-agent/devolucion

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 580 | 2003 (+245%) | 1615 (+178%) |
| Tokens de salida | 423 | 9033 (+2035%) | 3672 (+768%) |
| Tokens totales | 1003 | 11036 (+1000%) | 5287 (+427%) |
| Llamadas al modelo | 2 | 4 (+100%) | 3 (+50%) |
| Llamadas a tools | 2 | 2 (+0%) | 2 (+0%) |
| Latencia (ms) | 10902 | 235410 (+2059%) | 94934 (+771%) |
| Respuesta correcta | sí | sí | sí |
| Programas inválidos | — | 1 | 1 |

## service-agent/agendar-reparacion

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 3641 | 4172 (+15%) | 4368 (+20%) |
| Tokens de salida | 1086 | 30608 (+2718%) | 19402 (+1687%) |
| Tokens totales | 4727 | 34780 (+636%) | 23770 (+403%) |
| Llamadas al modelo | 5 | 3 (-40%) | 4 (-20%) |
| Llamadas a tools | 5 | 0 (-100%) | 3 (-40%) |
| Latencia (ms) | 33422 | 792264 (+2270%) | 449400 (+1245%) |
| Respuesta correcta | **no** | **no** | **no** |
| Programas inválidos | — | 2 | 2 |

---

No hay umbral automático de aprobación: estos números se leen y se decide.
La tasa de programas inválidos es la que valida o refuta la apuesta de que
una sintaxis familiar se escribe bien sin entrenamiento previo.
