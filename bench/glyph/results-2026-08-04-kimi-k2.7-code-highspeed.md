# Benchmark Glyph vs ReAct

## autolink-parts/cotizar-pastillas

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 1821 | 966 (-47%) | 991 (-46%) |
| Tokens de salida | 862 | 2091 (+143%) | 11329 (+1214%) |
| Tokens totales | 2683 | 3057 (+14%) | 12320 (+359%) |
| Llamadas al modelo | 3 | 2 (-33%) | 2 (-33%) |
| Llamadas a tools | 4 | 1 (-75%) | 5 (+25%) |
| Latencia (ms) | 6932 | 11773 (+70%) | 50756 (+632%) |
| Respuesta correcta | sí | sí | sí |
| Programas inválidos | — | 0 | 0 |

## support-agent/devolucion

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 496 | 1310 (+164%) | 835 (+68%) |
| Tokens de salida | 295 | 2504 (+749%) | 5332 (+1707%) |
| Tokens totales | 791 | 3814 (+382%) | 6167 (+680%) |
| Llamadas al modelo | 2 | 3 (+50%) | 2 (+0%) |
| Llamadas a tools | 2 | 2 (+0%) | 2 (+0%) |
| Latencia (ms) | 3030 | 15641 (+416%) | 29643 (+878%) |
| Respuesta correcta | sí | sí | sí |
| Programas inválidos | — | 0 | 0 |

## service-agent/agendar-reparacion

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 3648 | 1246 (-66%) | 841 (-77%) |
| Tokens de salida | 919 | 2455 (+167%) | 4094 (+345%) |
| Tokens totales | 4567 | 3701 (-19%) | 4935 (+8%) |
| Llamadas al modelo | 4 | 2 (-50%) | 1 (-75%) |
| Llamadas a tools | 6 | 6 (+0%) | 6 (+0%) |
| Latencia (ms) | 8663 | 15002 (+73%) | 22184 (+156%) |
| Respuesta correcta | **no** | sí | sí |
| Programas inválidos | — | 0 | 0 |

---

No hay umbral automático de aprobación: estos números se leen y se decide.
La tasa de programas inválidos es la que valida o refuta la apuesta de que
una sintaxis familiar se escribe bien sin entrenamiento previo.
