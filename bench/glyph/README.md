# Benchmark Glyph vs ReAct

Mide el mismo escenario con los dos patrones, mismo modelo y mismas tools
mockeadas deterministas. Aísla una sola variable: el patrón de orquestación.

## Correr

```bash
BENCH_MODEL=gpt-4o-mini \
BENCH_API_KEY_ENV=OPENAI_API_KEY \
uv run python -m bench.glyph.run
```

Cuesta dinero real: sale a un proveedor. Por eso corre nightly en CI y no en el
gate de PR.

El proveedor es del benchmark, no de un agente del repo — `autolink-parts` está
cableado a ollama en localhost, y tomar su router obligaría a editar su YAML para
medir contra otra cosa. Sirve cualquier endpoint compatible con OpenAI:

| Variable | Default | Para qué |
|---|---|---|
| `BENCH_MODEL` | — (requerida) | El modelo a medir |
| `BENCH_ENDPOINT` | `https://api.openai.com/v1` | Groq, Together, vLLM, ollama con `/v1`… |
| `BENCH_API_KEY_ENV` | `OPENAI_API_KEY` | Nombre de la variable que tiene la credencial |

Contra un ollama local, que no cuesta nada:

```bash
BENCH_MODEL=llama3.1:8b \
BENCH_ENDPOINT=http://localhost:11434/v1 \
BENCH_API_KEY_ENV=OLLAMA_KEY OLLAMA_KEY=x \
uv run python -m bench.glyph.run
```

## Qué mide y por qué

| Métrica | Por qué está |
|---|---|
| Tokens de entrada / salida | El objetivo primario |
| Llamadas al modelo | La causa del ahorro |
| Latencia wall-clock | La ganancia de concurrencia del DAG, invisible en tokens |
| Respuesta correcta | Sin esto el ahorro no significa nada |
| Programas inválidos | Valida o refuta la apuesta de la sintaxis familiar |

## Cómo se lee

No hay umbral de aprobación automático. Un ahorro grande con una regresión de
correctitud no es un éxito, y una tasa alta de programas inválidos indica que el
problema está en la gramática o en el bloque del prompt, no en el patrón.

Las tools duermen `TOOL_LATENCY_S = 0.15` para que la ejecución concurrente de
sentencias independientes sea visible en la latencia. Con tools instantáneas esa
ganancia no se mide.
