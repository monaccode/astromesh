# Benchmark Glyph vs ReAct

## autolink-parts/cotizar-pastillas

| Métrica | ReAct | Glyph | Δ |
|---|---:|---:|---:|
| Tokens de entrada | 1328 | 2800 | +111% |
| Tokens de salida | 246 | 751 | +205% |
| Tokens totales | 1574 | 3551 | +126% |
| Llamadas al modelo | 4 | 3 | -25% |
| Llamadas a tools | 5 | 2 | -60% |
| Latencia (ms) | 7528 | 14301 | +90% |
| Respuesta correcta | sí | **no** | |
| Programas inválidos | — | 2 | |

**REGRESIÓN**: Glyph responde mal donde ReAct responde bien.

## support-agent/devolucion

| Métrica | ReAct | Glyph | Δ |
|---|---:|---:|---:|
| Tokens de entrada | 790 | 2112 | +167% |
| Tokens de salida | 134 | 514 | +284% |
| Tokens totales | 924 | 2626 | +184% |
| Llamadas al modelo | 4 | 3 | -25% |
| Llamadas a tools | 3 | 0 | -100% |
| Latencia (ms) | 5732 | 10338 | +80% |
| Respuesta correcta | sí | **no** | |
| Programas inválidos | — | 2 | |

**REGRESIÓN**: Glyph responde mal donde ReAct responde bien.

## service-agent/agendar-reparacion

| Métrica | ReAct | Glyph | Δ |
|---|---:|---:|---:|
| Tokens de entrada | 2767 | 3062 | +11% |
| Tokens de salida | 234 | 1039 | +344% |
| Tokens totales | 3001 | 4101 | +37% |
| Llamadas al modelo | 6 | 3 | -50% |
| Llamadas a tools | 6 | 0 | -100% |
| Latencia (ms) | 8739 | 18010 | +106% |
| Respuesta correcta | **no** | **no** | |
| Programas inválidos | — | 2 | |

---

No hay umbral automático de aprobación: estos números se leen y se decide.
La tasa de programas inválidos es la que valida o refuta la apuesta de que
una sintaxis familiar se escribe bien sin entrenamiento previo.
