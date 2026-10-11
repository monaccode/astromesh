# Knowledge bundles OKF: el agente navega un bundle Open Knowledge Format

**Fecha:** 2026-10-11
**Estado:** diseño aprobado en conversación; pendiente de revisión del spec escrito.
**Alcance:** core `astromesh` (`astromesh/knowledge/` nuevo, `astromesh/runtime/engine.py`,
`vscode-extension/schemas/agent.schema.json`, `config/`, `docs-site/`, `CHANGELOG.md`)

[Open Knowledge Format](https://github.com/GoogleCloudPlatform/open-knowledge-format) (OKF) es
una spec abierta de Google Cloud (v0.1 el 2026-06-12, hoy v0.2) para representar conocimiento
como un directorio de markdown con frontmatter YAML, enlazado como una wiki. Está pensada para
que un agente la **navegue**: lee el índice, sigue links y abre sólo lo que necesita. No define
SDK, ni almacenamiento, ni runtime.

El objetivo es de interoperabilidad y posicionamiento: que astromesh "hable OKF". Éxito para la
v1 es que cualquier bundle OKF v0.2 conformante (por ejemplo los de muestra de Google: `ga4`,
`stackoverflow`, `crypto_bitcoin`, `acme_retail`) se conecte a un agente con una línea de YAML
y el agente lo use, respetando las señales de confianza y frescura de la spec.

## Decisiones tomadas

1. **Sólo consumir.** Producir o escribir bundles (exportar, o que un agente mantenga
   conceptos) queda fuera hasta que haya un caso real.
2. **Navegación, no ingesta a RAG.** El agente recibe tools para recorrer el bundle. No hay
   embeddings ni vector store. Se descartan la ingesta a `RAGPipeline` (pierde el grafo y
   exige infraestructura para la demo) y el híbrido (más caro). La ingesta se puede sumar
   después reusando el mismo parser.
3. **Una clave en `spec.knowledge`, no un `kind` nuevo.** Un bundle es un directorio, no una
   configuración con parámetros. Un `kind` arrastraría loader, registry, recursos de API y el
   esquema de Cortex sin aportar nada.
4. **Señales anotadas, no filtradas.** Las de la spec son orientativas (§5.3) y un concepto
   deprecated se conserva para los links. La única excepción es `kb_find`, que excluye los
   deprecated por defecto.
5. **Lectura en vivo, sin caché.** Cada llamada lee del disco: un `git pull` del bundle se ve
   al instante y no hay que tocar el hot-reload del engine.
6. **Sin dependencias nuevas.** Sólo `pyyaml`, que ya está.
7. **Attested Computation no se ejecuta.** Se lee como cualquier concepto. Ejecutar executors
   y attesters es correr código del bundle, y la propia spec difiere ese protocolo (§12).

## Configuración

```yaml
spec:
  knowledge:
    bundle: knowledge/acme_retail     # relativo a ASTROMESH_CONFIG_DIR, o absoluto
    # pipeline: product-knowledge     # opcional; independiente de bundle
```

- `bundle` y `pipeline` conviven y son independientes. `top_k` sigue aplicando sólo a
  `pipeline`.
- La ruta relativa se resuelve contra el directorio de configuración del runtime.
- `vscode-extension/schemas/agent.schema.json` hoy exige `pipeline` en `knowledge`. Pasa a
  exigir al menos uno de `pipeline` o `bundle` (`anyOf` de dos `required`).

## Componentes

Un módulo nuevo, `astromesh/knowledge/okf.py`, más la conexión en el engine.

### `Concept` y `parse_concept`

`parse_concept(root: Path, path: Path) -> Concept` separa frontmatter (`---` en la primera
línea y otro `---` que cierra) y cuerpo. Campos de `Concept`:

| Campo | Origen |
|---|---|
| `id` | ruta relativa a `root`, con `/` como separador y sin `.md` |
| `type` | `type`, obligatorio y no vacío |
| `title` | `title`; si falta, el nombre del archivo sin `.md` |
| `description` | `description` o `""` |
| `tags` | `tags` o `[]` |
| `status` | `status`; si falta, `stable` |
| `trust` | derivado de `verified` (abajo) |
| `stale` | `now >= stale_after` |
| `generated_at` | `generated.at`; si falta, `timestamp` (compatibilidad v0.1) |
| `body` | todo lo que sigue al frontmatter |
| `extra` | el resto del frontmatter, sin tocar (`sources`, `resource`, campos del productor) |

Tolerancia según la §11 de la spec: un concepto es **inválido** sólo si no tiene frontmatter
parseable como mapping YAML o si `type` falta o está vacío. Entonces levanta
`InvalidConcept(motivo)`. Nunca se rechaza por campos opcionales faltantes, `type`
desconocido, claves desconocidas ni links rotos.

**Señales:**

- `trust`: sin `verified` es `unverified`. Si algún `by` empieza con `human:` es
  `human-reviewed`. Si no, `machine-confirmed`. Un mapping suelto en `verified` cuenta como
  lista de un elemento (§5.2).
- `stale`: `stale_after` se compara como instante UTC. YAML puede entregarlo como `datetime`
  o como string. Un valor que no se puede interpretar se trata como ausente (no vencido) y se
  loguea un warning.
- `warnings`: lista de textos para el modelo, en este orden:
  - `deprecated`: `"DEPRECATED: kept for history; do not use for new work."`
  - `stale`: `"STALE since <stale_after ISO>: may no longer be accurate."`
  - `draft`: `"DRAFT: not reviewed; may be incomplete."`

### `Bundle`

`Bundle(root: Path)`, con tres operaciones. Las tres resuelven toda ruta con
`(root / x).resolve()` y exigen `is_relative_to(root.resolve())`. Eso bloquea `../`, rutas
absolutas fuera del bundle y symlinks que apuntan afuera, porque `resolve` los sigue antes de
chequear.

**Normalización de IDs.** Acepta `metrics/gross-margin`, `/metrics/gross-margin.md`,
`./metrics/gross-margin.md`, y quita los fragmentos `#...`. Devuelve el ID canónico.

**`index(path="/") -> str`**

- `path` es un directorio del bundle. Si no lo es, error.
- Si existe `<path>/index.md`, devuelve su contenido. El frontmatter de un `index.md` de la
  raíz (`okf_version`) se omite.
- Si no existe, lo sintetiza en el formato de la §8: una sección `# Subdirectories` con
  `* [nombre](nombre/) - <description del index.md del subdirectorio, si hay>` y una sección
  `# Concepts` con `* [title](id) - description [type, status, stale]`. En `[...]` sólo se
  agregan `status` si no es `stable` y `stale` si está vencido. Orden alfabético.
  Los conceptos inválidos se omiten y se agrega una línea final
  `(N concept(s) skipped: invalid frontmatter)`.

**`read(concept_id) -> dict`**

Devuelve `{id, type, title, description, tags, status, trust, stale, warnings, extra, body,
links}`.

- Sólo archivos `.md` que no sean `index.md` ni `log.md`. Cualquier otro archivo devuelve
  `not a concept: <id>`.
- `links`: los links markdown del cuerpo (`[texto](destino)`), en orden de aparición y sin
  repetir.
  - Los que apuntan a `http(s)://`, `mailto:` u otro esquema van como
    `{"url": destino, "external": true}`.
  - Los internos se resuelven contra el directorio del concepto, o contra la raíz si empiezan
    con `/`, y van como `{"id": <id canónico>, "exists": bool}`. Un link a un directorio
    (`tables/`) resuelve a su ID de directorio con `"dir": true`.
  - Los que caen fuera del bundle se descartan.
- El cuerpo va entero. El tope lo pone el presupuesto de resultados de tools que ya existe.

**`find(text=None, type=None, tags=None, include_deprecated=False, limit=20) -> dict`**

- Recorre todos los `.md` de concepto del bundle (`rglob`, salteando reservados).
- `type`: igualdad sin distinguir mayúsculas.
- `tags`: el concepto tiene que tener todos, sin distinguir mayúsculas.
- `text`: subcadena sin distinguir mayúsculas. Los que coinciden en título, descripción o tags
  van antes que los que sólo coinciden en el cuerpo. Dentro de cada grupo, por ID.
- Sin `text`, orden por ID.
- `include_deprecated=False` excluye `status: deprecated`.
- Devuelve `{"results": [{id, type, title, description, status, trust, stale}],
  "skipped_invalid": N}`, cortado a `limit` (máximo 100).
- Lleva un comentario `ponytail:` con el límite: recorre todos los archivos en cada llamada;
  anda con cientos o pocos miles de conceptos. Más grande que eso, ingesta a RAG.

### Las tools

Tres tools internas, registradas por el engine (no se declaran en `spec.tools`). Envoltorios
finos sobre un `Bundle`, con el patrón de `rag_query`: nunca levantan, devuelven
`ToolResult(success=False, error=...)`.

| Tool | Parámetros | Descripción para el modelo |
|---|---|---|
| `kb_index` | `path` (string, default `"/"`) | Lista un directorio del knowledge bundle. Empezá por acá. |
| `kb_read` | `concept_id` (string, obligatorio) | Lee un concepto: metadatos, avisos de confianza, cuerpo y links ya resueltos a IDs. |
| `kb_find` | `text`, `type`, `tags` (array), `include_deprecated` (bool), `limit` (int) | Busca conceptos por frontmatter y texto. |

Las descripciones van en inglés, como el resto de las tools builtin.

**Errores:**

| Caso | Resultado |
|---|---|
| ID inexistente | `concept not found: <id>`, con hasta 3 IDs parecidos (`difflib.get_close_matches`) |
| Ruta fuera del bundle | `outside bundle: <entrada>` |
| Concepto inválido | `invalid concept <id>: <motivo>` |
| Archivo que no es concepto | `not a concept: <id>` |

### Conexión en el engine

En `_build_agent`, junto a `_resolve_rag`:

1. Si `spec.knowledge.bundle` está presente, se resuelve la ruta. Si no existe o no es un
   directorio: `logger.warning` y el agente sigue sin bundle. Mismo trato que un `pipeline`
   desconocido.
2. Se registran `kb_index`, `kb_read` y `kb_find` con `register_internal`. Si el agente ya
   declara una tool con alguno de esos nombres, `ValueError` como en las demás colisiones.
3. En cada corrida se agrega la variable de template `bundle_index`: el resultado de
   `Bundle.index("/")`. Sin bundle vale `""`. Es estable entre queries mientras el bundle no
   cambie, así que puede ir en `prompts.system` sin romper el caché; no se suma a
   `_per_query_vars_in`. Si el template no la usa, el agente empieza llamando a `kb_index`.

## Seguridad

- Confinamiento de rutas como se describe en `Bundle`, incluidos symlinks.
- Sólo lectura, y sólo `.md`. Ningún archivo de `references/`, attester o script se lee como
  concepto ni se ejecuta.
- El cuerpo de un concepto llega al modelo como resultado de tool, igual que `read_file` o
  `rag_query`. Un bundle de terceros es una vía de inyección de prompt. La v1 no agrega
  defensa; la documentación dice que se monten sólo bundles de fuentes confiables.

## Tests

TDD, en `tests/knowledge/`. Bundle de prueba escrito a mano en `tests/fixtures/okf/`:

- `index.md` en la raíz con frontmatter `okf_version: "0.2"`;
- `metrics/` con conceptos y sin `index.md` (para el índice sintetizado);
- un concepto human-reviewed con `verified` como mapping suelto;
- uno machine-confirmed con `verified` como lista de `process:`;
- uno `status: deprecated`, uno `status: draft` y uno con `stale_after` pasado;
- uno v0.1 con `timestamp` y sin `generated`;
- uno con frontmatter roto y uno sin `type`;
- links: absoluto, relativo, a directorio, roto, externo y uno que sale del bundle;
- un archivo `.py` dentro del bundle.

El symlink que escapa se crea en el test con `tmp_path`; no se versiona.

Cobertura:

- **Parser:** cada señal; claves desconocidas preservadas en `extra`; compatibilidad v0.1;
  inválidos con su motivo; `stale_after` como `datetime` y como string, e inválido.
- **`Bundle`:** índice existente y sintetizado (con la línea de omitidos); normalización de
  IDs; links resueltos; `find` con cada filtro, orden, `include_deprecated`, `limit`;
  confinamiento por `../`, ruta absoluta y symlink; `.py` como "not a concept"; sugerencias
  de `difflib`.
- **Engine:** un agente con `knowledge.bundle` tiene las tres tools y `bundle_index` llega al
  template; ruta inexistente → warning y sin tools; una tool declarada `kb_read` → error de
  colisión; `bundle` y `pipeline` juntos funcionan.

**Verificación manual antes de cerrar:** correr las tres operaciones contra los cuatro bundles
de muestra de Google, clonados en un temporal sin versionar. Ningún concepto puede quedar
omitido por inválido.

## Documentación y entregables

- Página nueva `docs-site/src/content/docs/advanced/knowledge-bundles.md`: qué es OKF, el
  YAML, las tres tools, las señales de confianza, `bundle_index`, la advertencia de seguridad
  y qué queda fuera.
- `docs-site/src/content/docs/configuration/agent-yaml.md`: `bundle` en la tabla de
  `spec.knowledge`.
- Ejemplo: `config/knowledge/okf-demo/` (bundle mínimo de 3 o 4 conceptos) y
  `config/agents/okf-demo.agent.yaml` que lo usa con `bundle_index` en el system prompt.
- `vscode-extension/schemas/agent.schema.json`: `knowledge.bundle` y el `anyOf`.
- `CHANGELOG.md` bajo `[Unreleased]`.

## Fuera de alcance

- Ejecutar Attested Computations (executor y attester).
- Producir, exportar o editar bundles.
- Ingesta de bundles a `RAGPipeline`.
- Bundles remotos (git, tarball). La v1 lee un directorio local.
- Montar bundles en los pods de Nexus.
- Soporte en Cortex para `knowledge.bundle` (su esquema se mantiene a mano).
- El release (core 0.68.0 y propagación a Nexus, OS y docs de versiones). Va a pedido.
