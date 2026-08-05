# Benchmark Glyph vs ReAct

## autolink-parts/cotizar-pastillas

| Métrica | ReAct | Glyph | Δ |
|---|---:|---:|---:|
| Tokens de entrada | 559 | 1620 | +190% |
| Tokens de salida | 615 | 4362 | +609% |
| Tokens totales | 1174 | 5982 | +410% |
| Llamadas al modelo | 2 | 2 | +0% |
| Llamadas a tools | 1 | 5 | +400% |
| Latencia (ms) | 20728 | 114064 | +450% |
| Respuesta correcta | sí | sí | |
| Programas inválidos | — | 0 | |

## support-agent/devolucion

| Métrica | ReAct | Glyph | Δ |
|---|---:|---:|---:|
| Tokens de entrada | 580 | 1479 | +155% |
| Tokens de salida | 455 | 2000 | +340% |
| Tokens totales | 1035 | 3479 | +236% |
| Llamadas al modelo | 2 | 3 | +50% |
| Llamadas a tools | 2 | 2 | +0% |
| Latencia (ms) | 15519 | 62408 | +302% |
| Respuesta correcta | sí | sí | |
| Programas inválidos | — | 0 | |

## service-agent/agendar-reparacion

| Métrica | ReAct | Glyph | Δ |
|---|---:|---:|---:|
| Tokens de entrada | 2744 | 4992 | +82% |
| Tokens de salida | 1150 | 10243 | +791% |
| Tokens totales | 3894 | 15235 | +291% |
| Llamadas al modelo | 4 | 4 | +0% |
| Llamadas a tools | 5 | 3 | -40% |
| Latencia (ms) | 38062 | 320484 | +742% |
| Respuesta correcta | **no** | **no** | |
| Programas inválidos | — | 2 | |

---

No hay umbral automático de aprobación: estos números se leen y se decide.
La tasa de programas inválidos es la que valida o refuta la apuesta de que
una sintaxis familiar se escribe bien sin entrenamiento previo.
