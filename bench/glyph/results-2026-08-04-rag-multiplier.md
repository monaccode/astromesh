# Benchmark Glyph vs ReAct

## autolink-parts/cotizar-pastillas

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 472 | 1093 (+132%) | 740 (+57%) |
| Tokens de salida | 380 | 4571 (+1103%) | 2142 (+464%) |
| Tokens totales | 852 | 5664 (+565%) | 2882 (+238%) |
| Llamadas al modelo | 2 | 2 (+0%) | 1 (-50%) |
| Llamadas a tools | 1 | 3 (+200%) | 5 (+400%) |
| Latencia (ms) | 3265 | 24790 (+659%) | 11716 (+259%) |
| Respuesta correcta | sí | sí | sí |
| Programas inválidos | — | 0 | 0 |

## support-agent/devolucion

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 482 | 977 (+103%) | 704 (+46%) |
| Tokens de salida | 277 | 2002 (+623%) | 7623 (+2652%) |
| Tokens totales | 759 | 2979 (+292%) | 8327 (+997%) |
| Llamadas al modelo | 2 | 3 (+50%) | 1 (-50%) |
| Llamadas a tools | 2 | 2 (+0%) | 3 (+50%) |
| Latencia (ms) | 2939 | 13019 (+343%) | 40824 (+1289%) |
| Respuesta correcta | sí | sí | sí |
| Programas inválidos | — | 0 | 0 |

## support-agent-rag/devolucion

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 3449 | 6021 (+75%) | 2229 (-35%) |
| Tokens de salida | 288 | 2098 (+628%) | 3239 (+1025%) |
| Tokens totales | 3737 | 8119 (+117%) | 5468 (+46%) |
| Knowledge reenviado (est.) | 2678 | 4017 (+50%) | 1339 (-50%) |
| Llamadas al modelo | 2 | 3 (+50%) | 1 (-50%) |
| Llamadas a tools | 1 | 3 (+200%) | 2 (+100%) |
| Latencia (ms) | 3084 | 11762 (+281%) | 18899 (+513%) |
| Respuesta correcta | sí | sí | sí |
| Programas inválidos | — | 0 | 0 |

## service-agent/agendar-reparacion

| Métrica | ReAct | glyph | glyph-datos |
|---|---|---|---|
| Tokens de entrada | 2720 | 1174 (-57%) | 841 (-69%) |
| Tokens de salida | 861 | 3779 (+339%) | 12050 (+1300%) |
| Tokens totales | 3581 | 4953 (+38%) | 12891 (+260%) |
| Llamadas al modelo | 3 | 2 (-33%) | 1 (-67%) |
| Llamadas a tools | 6 | 6 (+0%) | 6 (+0%) |
| Latencia (ms) | 6787 | 25408 (+274%) | 61803 (+811%) |
| Respuesta correcta | **no** | sí | sí |
| Programas inválidos | — | 0 | 0 |

---

No hay umbral automático de aprobación: estos números se leen y se decide.
La tasa de programas inválidos es la que valida o refuta la apuesta de que
una sintaxis familiar se escribe bien sin entrenamiento previo.
