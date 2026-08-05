# Benchmark Glyph vs ReAct

## autolink-parts/cotizar-pastillas

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 483 | 951 (+97%) | 740 (+53%) |
| Tokens de salida | 591 | 2808 (+375%) | 3264 (+452%) |
| Tokens totales | 1074 | 3759 (+250%) | 4004 (+273%) |
|   de los cuales cacheados | 131 | 740 (+465%) | 740 (+465%) |
| Llamadas al modelo | 2 | 2 (+0%) | 1 (-50%) |
| Llamadas a tools | 1 | 1 (+0%) | 3 (+200%) |
| Latencia (ms) | 4168 | 15606 (+274%) | 17432 (+318%) |
| Respuesta correcta | sí | sí | sí |
| Programas inválidos | — | 0 | 0 |

## support-agent/devolucion

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 999 | 1276 (+28%) | 803 (-20%) |
| Tokens de salida | 381 | 16522 (+4236%) | 1396 (+266%) |
| Tokens totales | 1380 | 17798 (+1190%) | 2199 (+59%) |
|   de los cuales cacheados | 256 | 704 (+175%) | 704 (+175%) |
| Llamadas al modelo | 3 | 3 (+0%) | 2 (-33%) |
| Llamadas a tools | 3 | 3 (+0%) | 2 (-33%) |
| Latencia (ms) | 4505 | 89197 (+1880%) | 9036 (+101%) |
| Respuesta correcta | sí | sí | sí |
| Programas inválidos | — | 0 | 0 |

## support-agent-rag/devolucion

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 3650 | 5765 (+58%) | 3889 (+7%) |
| Tokens de salida | 575 | 2441 (+325%) | 2411 (+319%) |
| Tokens totales | 4225 | 8206 (+94%) | 6300 (+49%) |
|   de los cuales cacheados | 1536 | 4096 (+167%) | 3509 (+128%) |
| Knowledge reenviado (est.) | 2678 | 4017 (+50%) | 2678 (+0%) |
| Llamadas al modelo | 2 | 3 (+50%) | 2 (+0%) |
| Llamadas a tools | 2 | 2 (+0%) | 2 (+0%) |
| Latencia (ms) | 4352 | 12720 (+192%) | 15154 (+248%) |
| Respuesta correcta | sí | sí | sí |
| Programas inválidos | — | 0 | 0 |

## service-agent/agendar-reparacion

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 4344 | 1312 (-70%) | 841 (-81%) |
| Tokens de salida | 1023 | 7920 (+674%) | 10324 (+909%) |
| Tokens totales | 5367 | 9232 (+72%) | 11165 (+108%) |
|   de los cuales cacheados | 2517 | 841 (-67%) | 841 (-67%) |
| Llamadas al modelo | 5 | 2 (-60%) | 1 (-80%) |
| Llamadas a tools | 6 | 6 (+0%) | 6 (+0%) |
| Latencia (ms) | 9109 | 44502 (+389%) | 55267 (+507%) |
| Respuesta correcta | sí | sí | sí |
| Programas inválidos | — | 0 | 0 |

---

No hay umbral automático de aprobación: estos números se leen y se decide.
La tasa de programas inválidos es la que valida o refuta la apuesta de que
una sintaxis familiar se escribe bien sin entrenamiento previo.
