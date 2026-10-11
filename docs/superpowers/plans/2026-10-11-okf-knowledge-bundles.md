# Knowledge bundles OKF — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un agente con `spec.knowledge.bundle: <ruta>` recibe tres tools (`kb_index`, `kb_read`, `kb_find`) y la variable de template `bundle_index` para navegar un bundle Open Knowledge Format v0.2.

**Architecture:** `astromesh/knowledge/okf.py` parsea conceptos (frontmatter YAML + markdown) y expone `Bundle` con `read`/`index`/`find` confinados a la raíz. `astromesh/knowledge/tools.py` envuelve eso en tres tools internas. El engine resuelve `knowledge.bundle`, registra las tools y pasa el `Bundle` al `Agent`, que agrega `bundle_index` a las variables del template.

**Tech Stack:** Python 3.12, `pyyaml` (ya está), pytest con `asyncio_mode = "auto"`, `jsonschema` (dev).

**Spec:** `docs/superpowers/specs/2026-10-11-okf-knowledge-bundles-design.md`

## Global Constraints

- Sin dependencias nuevas: sólo stdlib y `pyyaml`. `astromesh.api.main` tiene que seguir importando sin extras (lo exige astromesh-os).
- Las tools nunca levantan: devuelven `ToolResult(success=False, error=...)`.
- Mensajes de error exactos: `concept not found: <id>` (con ` (did you mean: a, b?)` si hay parecidos), `outside bundle: <entrada>`, `invalid concept <id>: <motivo>`, `not a concept: <id>`, `not a directory: <entrada>`.
- Avisos exactos: `"DEPRECATED: kept for history; do not use for new work."`, `"STALE since <stale_after ISO>: may no longer be accurate."`, `"DRAFT: not reviewed; may be incomplete."`, en ese orden.
- Niveles de confianza exactos: `unverified`, `machine-confirmed`, `human-reviewed`.
- `kb_find`: `limit` default 20, máximo 100; excluye `status: deprecated` salvo `include_deprecated=true`.
- Descripciones de tools en inglés; comentarios y mensajes de log en español, como el resto del core.
- Antes de cada commit: `uv run ruff check astromesh/ tests/` y `uv run ruff format --check astromesh/ tests/` limpios (el gate de CI corre los dos).
- Excepciones con sufijo `Error` (ruff N818). Un `raise` no-TypeError dentro de un `if not isinstance` lleva `# noqa: TRY004`, como en `astromesh/rag/loader.py`.
- Commits convencionales en español con la línea `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. La entrada de `CHANGELOG.md` entra en el primer commit `feat:` (Task 1) y cubre los siguientes.
- Trabajo en el worktree `/Users/fulfaro/monaccode/astromesh-okf`, rama `feat/okf-knowledge`. Nunca `git stash`. No pushear.

## Review Focus

1. Archivos con fin de línea CRLF o BOM UTF-8 (bundles editados en Windows): el frontmatter tiene que parsear igual. → test en Task 1.
2. Frontmatter que es YAML válido pero no un mapping (una lista, un escalar) o con `tags` como string: inválido o tolerado, nunca una excepción no controlada. → tests en Task 1.
3. Argumentos sueltos del modelo: `limit` como string, `tags` como string, claves que la tool no declara. La llamada no puede romperse. → test en Task 4.
4. Un bundle que es un clon de git (`.git/` adentro) o con directorios ocultos: no se recorren. → test en Task 3.
5. Un bundle que deja de existir después de construir el agente: la corrida sigue con `bundle_index = ""`. → test en Task 4.

---

### Task 1: Bundle de prueba y parseo de conceptos

**Files:**
- Create: `astromesh/knowledge/__init__.py` (vacío)
- Create: `astromesh/knowledge/okf.py`
- Create: `tests/knowledge/__init__.py` (vacío)
- Create: `tests/knowledge/test_okf_concept.py`
- Create: fixtures en `tests/fixtures/okf/` (contenido abajo)
- Modify: `CHANGELOG.md` (`[Unreleased]`)

**Interfaces:**
- Produces: `BundleError(ValueError)`, `InvalidConceptError(BundleError)`, `Concept` (dataclass con `id, type, title, description, tags, status, trust, stale, stale_after, generated_at, body, extra`, property `warnings -> list[str]`, método `summary() -> dict`), `parse_concept(root: Path, path: Path, now: datetime | None = None) -> Concept`, `split_frontmatter(text: str) -> tuple[dict, str]`, `_id_of(root: Path, path: Path) -> str`, constante `RESERVED = frozenset({"index.md", "log.md"})`.

- [ ] **Step 1: Crear el bundle de prueba**

`tests/fixtures/okf/index.md`:
```markdown
---
okf_version: "0.2"
---
# Subdirectories

* [metrics](metrics/) - Business metric definitions.
* [tables](tables/index.md) - Source tables.
* [attesters](attesters/) - Verification code (not concepts).
```

`tests/fixtures/okf/tables/index.md`:
```markdown
# Tables

* [Orders](orders.md) - One row per completed order.
```

`tests/fixtures/okf/tables/orders.md`:
```markdown
---
type: BigQuery Table
title: Orders
description: One row per completed order.
resource: https://console.cloud.google.com/bigquery?p=acme&d=sales&t=orders
tags: [sales, orders]
verified: { by: human:ana, at: 2026-06-25T09:00:00Z }
---

# Schema

| Column | Description |
|---|---|
| `total_usd` | Feeds [revenue](/metrics/revenue.md). |

# Notes

Margin is defined in [gross margin](../metrics/gross-margin.md); all metrics live in
[the metrics folder](/metrics/). Customers are described in
[customers](/tables/customers.md), which is not written yet. Upstream docs:
[export](https://example.com/orders). Back to the [table list](index.md).
See also [revenue again](/metrics/revenue.md), [this section](#schema),
[a secret](../../outside.md) and ![diagram](diagram.png).
```

`tests/fixtures/okf/metrics/revenue.md`:
```markdown
---
type: Metric
title: Revenue
description: Recognized revenue for a fiscal year.
tags: [finance, revenue]
owner: finance
resource: https://wiki.acme/finance/revenue
generated: { by: reference_agent/gemini-2.5-pro, at: 2026-06-20T22:53:05Z }
verified:
  - { by: process:finance-nightly, at: 2026-06-26T02:00:00Z }
stale_after: 2099-01-01T00:00:00Z
sources:
  - id: rev-policy
    resource: https://wiki.acme/finance/revenue-recognition
    title: Revenue recognition policy
---

# Definition

Sum of `amount` over [orders](/tables/orders.md) booked to the fiscal year.[^rev-policy]

[^rev-policy]: Revenue recognition policy
```

`tests/fixtures/okf/metrics/gross-margin.md`:
```markdown
---
type: Metric
title: Gross Margin
description: Revenue minus cost of goods.
tags: [finance, margin]
verified: { by: human:ana, at: 2026-02-01T00:00:00Z }
stale_after: 2020-01-01T00:00:00Z
---

# Definition

Gross margin for a period.
```

`tests/fixtures/okf/metrics/gross-margin-legacy.md`:
```markdown
---
type: Metric
title: Gross Margin (legacy)
description: Retired definition.
tags: [finance, margin]
status: deprecated
---

Superseded by [gross margin](./gross-margin.md).
```

`tests/fixtures/okf/metrics/churn.md`:
```markdown
---
type: metric
title: Churn
description: Share of customers lost in a period.
tags: [customers]
status: draft
---

Lost customers reduce recurring revenue.
```

`tests/fixtures/okf/metrics/legacy-v01.md`:
```markdown
---
type: Reference
timestamp: '2026-05-28T22:53:05+00:00'
---

# Citations

- https://example.com/old-wiki
```

`tests/fixtures/okf/metrics/broken.md`:
```markdown
---
type: [unclosed
---

Broken frontmatter.
```

`tests/fixtures/okf/metrics/no-type.md`:
```markdown
---
title: Missing type
---

No type here.
```

`tests/fixtures/okf/metrics/log.md`:
```markdown
# Directory Update Log

## 2026-06-20
* **Creation**: Added [Revenue](/metrics/revenue.md).
```

`tests/fixtures/okf/attesters/check.py`:
```python
def check(receipt):
    return bool(receipt)
```

- [ ] **Step 2: Escribir los tests que fallan**

`tests/knowledge/test_okf_concept.py`:
```python
"""Parseo de conceptos OKF v0.2: campos, señales de confianza y tolerancia (§11)."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from astromesh.knowledge.okf import InvalidConceptError, parse_concept

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "okf"
NOW = datetime(2026, 10, 11, tzinfo=UTC)


def _c(rel):
    return parse_concept(FIX, FIX / rel, now=NOW)


def _tmp(tmp_path, text, name="x.md"):
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
    return parse_concept(tmp_path, path, now=NOW)


def test_basic_fields():
    c = _c("tables/orders.md")
    assert c.id == "tables/orders"
    assert c.type == "BigQuery Table"
    assert c.title == "Orders"
    assert c.description == "One row per completed order."
    assert c.tags == ["sales", "orders"]
    assert c.status == "stable"
    assert c.body.startswith("# Schema")


def test_verified_as_bare_mapping_with_human_is_human_reviewed():
    assert _c("tables/orders.md").trust == "human-reviewed"


def test_verified_by_process_only_is_machine_confirmed():
    assert _c("metrics/revenue.md").trust == "machine-confirmed"


def test_no_verified_is_unverified():
    assert _c("metrics/churn.md").trust == "unverified"


def test_past_stale_after_is_stale_and_warns():
    c = _c("metrics/gross-margin.md")
    assert c.stale is True
    assert c.warnings == ["STALE since 2020-01-01T00:00:00+00:00: may no longer be accurate."]


def test_future_stale_after_is_not_stale():
    c = _c("metrics/revenue.md")
    assert c.stale is False
    assert c.warnings == []


def test_deprecated_warns():
    c = _c("metrics/gross-margin-legacy.md")
    assert c.status == "deprecated"
    assert c.warnings == ["DEPRECATED: kept for history; do not use for new work."]


def test_draft_warns():
    assert _c("metrics/churn.md").warnings == ["DRAFT: not reviewed; may be incomplete."]


def test_warnings_order_deprecated_stale_draft(tmp_path):
    c = _tmp(tmp_path, "---\ntype: X\nstatus: deprecated\nstale_after: 2020-01-01\n---\nb")
    assert [w.split(":")[0] for w in c.warnings] == ["DEPRECATED", "STALE since 2020-01-01T00"]


def test_unknown_keys_are_preserved_in_extra():
    c = _c("metrics/revenue.md")
    assert c.extra["owner"] == "finance"
    assert c.extra["resource"] == "https://wiki.acme/finance/revenue"
    assert c.extra["sources"][0]["id"] == "rev-policy"
    assert "type" not in c.extra
    assert "title" not in c.extra


def test_extra_is_json_serializable():
    c = _c("metrics/revenue.md")
    assert json.loads(json.dumps(c.extra))["generated"]["at"] == "2026-06-20T22:53:05+00:00"


def test_generated_at_comes_from_generated():
    assert _c("metrics/revenue.md").generated_at == "2026-06-20T22:53:05+00:00"


def test_v01_timestamp_fallback_and_title_from_filename():
    c = _c("metrics/legacy-v01.md")
    assert c.generated_at == "2026-05-28T22:53:05+00:00"
    assert c.title == "legacy-v01"


def test_summary_keys():
    assert set(_c("metrics/revenue.md").summary()) == {
        "id",
        "type",
        "title",
        "description",
        "status",
        "trust",
        "stale",
    }


def test_unparseable_frontmatter_is_invalid():
    with pytest.raises(InvalidConceptError, match=r"^invalid concept metrics/broken: "):
        _c("metrics/broken.md")


def test_missing_type_is_invalid():
    with pytest.raises(InvalidConceptError, match=r"^invalid concept metrics/no-type: missing type$"):
        _c("metrics/no-type.md")


def test_no_frontmatter_is_invalid(tmp_path):
    with pytest.raises(InvalidConceptError, match="missing frontmatter"):
        _tmp(tmp_path, "# Just markdown\n")


def test_frontmatter_that_is_not_a_mapping_is_invalid(tmp_path):
    with pytest.raises(InvalidConceptError, match="not a mapping"):
        _tmp(tmp_path, "---\n- a\n- b\n---\nbody")


def test_unterminated_frontmatter_is_invalid(tmp_path):
    with pytest.raises(InvalidConceptError, match="unterminated"):
        _tmp(tmp_path, "---\ntype: X\n")


def test_non_utf8_is_invalid(tmp_path):
    with pytest.raises(InvalidConceptError, match="not UTF-8"):
        _tmp(tmp_path, b"---\ntype: X\n---\n\xff\xfe")


def test_crlf_and_bom_parse(tmp_path):
    c = _tmp(tmp_path, "﻿---\r\ntype: X\r\ntitle: T\r\n---\r\nbody\r\n")
    assert (c.type, c.title, c.body) == ("X", "T", "body")


def test_tags_as_string_become_a_list(tmp_path):
    assert _tmp(tmp_path, "---\ntype: X\ntags: finance\n---\n").tags == ["finance"]


def test_non_string_title_is_stringified(tmp_path):
    assert _tmp(tmp_path, "---\ntype: X\ntitle: 2026\n---\n").title == "2026"


def test_stale_after_as_quoted_string(tmp_path):
    assert _tmp(tmp_path, '---\ntype: X\nstale_after: "2020-01-01T00:00:00Z"\n---\n').stale


def test_stale_after_as_date_only(tmp_path):
    assert _tmp(tmp_path, "---\ntype: X\nstale_after: 2020-01-01\n---\n").stale


def test_unreadable_stale_after_is_ignored_and_logged(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="astromesh.knowledge.okf"):
        c = _tmp(tmp_path, "---\ntype: X\nstale_after: next tuesday\n---\n")
    assert c.stale is False
    assert c.warnings == []
    assert "stale_after" in caplog.text
```

- [ ] **Step 3: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/knowledge/test_okf_concept.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'astromesh.knowledge'`

- [ ] **Step 4: Implementar**

`astromesh/knowledge/__init__.py`: archivo vacío. `tests/knowledge/__init__.py`: archivo vacío.

`astromesh/knowledge/okf.py`:
```python
"""Open Knowledge Format (OKF) v0.2: lectura de bundles para que un agente los navegue.

Spec: https://github.com/GoogleCloudPlatform/open-knowledge-format (SPEC.md). Sólo se
consume: nada del bundle se escribe ni se ejecuta (tampoco las Attested Computations).
Tolerante como pide la §11: un concepto es inválido sólo sin frontmatter parseable o sin
`type`. Campos opcionales faltantes, tipos y claves desconocidas y links rotos nunca lo
invalidan.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

RESERVED = frozenset({"index.md", "log.md"})

# Campos que `Concept` expone con nombre propio; el resto del frontmatter va a `extra`.
_MAPPED = frozenset({"type", "title", "description", "tags", "status", "stale_after"})

_DEPRECATED = "DEPRECATED: kept for history; do not use for new work."
_DRAFT = "DRAFT: not reviewed; may be incomplete."


class BundleError(ValueError):
    """Falla de una operación sobre el bundle. El mensaje llega tal cual al modelo."""


class InvalidConceptError(BundleError):
    """El archivo no tiene frontmatter parseable o le falta `type` (§11)."""


@dataclass
class Concept:
    id: str
    type: str
    title: str
    description: str
    tags: list[str]
    status: str
    trust: str
    stale: bool
    stale_after: datetime | None
    generated_at: str | None
    body: str
    extra: dict = field(default_factory=dict)

    @property
    def warnings(self) -> list[str]:
        out = []
        if self.status == "deprecated":
            out.append(_DEPRECATED)
        if self.stale:
            out.append(f"STALE since {self.stale_after.isoformat()}: may no longer be accurate.")
        if self.status == "draft":
            out.append(_DRAFT)
        return out

    def summary(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "trust": self.trust,
            "stale": self.stale,
        }


def _id_of(root: Path, path: Path) -> str:
    """ID de concepto (§2): la ruta dentro del bundle sin `.md`. La raíz es `/`."""
    rel = path.relative_to(root).as_posix()
    return "/" if rel == "." else rel.removesuffix(".md")


def split_frontmatter(text: str) -> tuple[dict, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise InvalidConceptError("missing frontmatter")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                meta = yaml.safe_load("\n".join(lines[1:i]))
            except yaml.YAMLError as exc:
                raise InvalidConceptError(
                    f"unparseable frontmatter ({exc.__class__.__name__})"
                ) from None
            if not isinstance(meta, dict):
                # ValueError y no TypeError: es el contrato que atrapan las tools.
                raise InvalidConceptError("frontmatter is not a mapping")  # noqa: TRY004
            return meta, "\n".join(lines[i + 1 :]).lstrip("\n")
    raise InvalidConceptError("unterminated frontmatter")


def _tags(value) -> list[str]:
    if isinstance(value, list):
        return [str(t) for t in value if t is not None]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _trust(verified) -> str:
    """Nivel de confianza (§5.3). Un mapping suelto cuenta como lista de uno (§5.2)."""
    events = [verified] if isinstance(verified, dict) else verified
    if not isinstance(events, list):
        return "unverified"
    actors = [str(e["by"]) for e in events if isinstance(e, dict) and e.get("by")]
    if not actors:
        return "unverified"
    if any(a.startswith("human:") for a in actors):
        return "human-reviewed"
    return "machine-confirmed"


def _instant(value, cid: str) -> datetime | None:
    """`stale_after` como instante UTC. YAML lo entrega como datetime, date o string."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date):
        moment = datetime(value.year, value.month, value.day, tzinfo=UTC)
    else:
        try:
            moment = datetime.fromisoformat(str(value))
        except ValueError:
            logger.warning("okf: %s tiene stale_after ilegible (%r); se ignora", cid, value)
            return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _stamp(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, date) else str(value)


def _generated_at(meta: dict) -> str | None:
    gen = meta.get("generated")
    if isinstance(gen, dict) and gen.get("at") is not None:
        return _stamp(gen["at"])
    return _stamp(meta.get("timestamp"))  # v0.1 (§13.1)


def _jsonable(meta: dict) -> dict:
    """`extra` viaja en un resultado de tool: las fechas de YAML pasan a ISO 8601."""
    return json.loads(json.dumps(meta, default=_stamp))


def parse_concept(root: Path, path: Path, now: datetime | None = None) -> Concept:
    cid = _id_of(root, path)
    try:
        meta, body = split_frontmatter(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError:
        raise InvalidConceptError(f"invalid concept {cid}: not UTF-8") from None
    except InvalidConceptError as exc:
        raise InvalidConceptError(f"invalid concept {cid}: {exc}") from None
    ctype = str(meta.get("type") or "").strip()
    if not ctype:
        raise InvalidConceptError(f"invalid concept {cid}: missing type")
    stale_after = _instant(meta.get("stale_after"), cid)
    now = now or datetime.now(UTC)
    return Concept(
        id=cid,
        type=ctype,
        title=str(meta.get("title") or path.stem),
        description=str(meta.get("description") or ""),
        tags=_tags(meta.get("tags")),
        status=str(meta.get("status") or "stable").strip().lower(),
        trust=_trust(meta.get("verified")),
        stale=stale_after is not None and now >= stale_after,
        stale_after=stale_after,
        generated_at=_generated_at(meta),
        body=body,
        extra=_jsonable({k: v for k, v in meta.items() if k not in _MAPPED}),
    )
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/knowledge/test_okf_concept.py -v`
Expected: todos PASS.

- [ ] **Step 6: CHANGELOG**

En `CHANGELOG.md`, debajo de `## [Unreleased]`, agregar:
```markdown

### Added

- Knowledge bundles OKF: `spec.knowledge.bundle` apunta a un directorio
  [Open Knowledge Format](https://github.com/GoogleCloudPlatform/open-knowledge-format)
  v0.2 (también lee v0.1). El agente recibe `kb_index`, `kb_read` y `kb_find` para
  navegarlo y la variable de template `bundle_index` con el índice raíz, estable para el
  caché de prompts. Las señales de la spec llegan al modelo sin filtrar: nivel de
  confianza (`verified`), `stale_after`, y avisos para deprecated y draft; `kb_find`
  excluye los deprecated por defecto. Sólo lectura, confinado a la raíz del bundle
  (symlinks incluidos); nada del bundle se ejecuta. Ejemplo en
  `config/agents/okf-demo.agent.yaml`.
```

- [ ] **Step 7: Lint y commit**

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add astromesh/knowledge tests/knowledge tests/fixtures/okf CHANGELOG.md
git commit -m "feat(knowledge): parseo de conceptos OKF v0.2 y bundle de prueba

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `Bundle.read`: confinamiento, IDs y links

**Files:**
- Modify: `astromesh/knowledge/okf.py` (agregar al final)
- Create: `tests/knowledge/test_okf_read.py`

**Interfaces:**
- Consumes: `parse_concept`, `_id_of`, `RESERVED`, `BundleError`, `InvalidConceptError` (Task 1).
- Produces: `OutsideBundleError`, `ConceptNotFoundError`, `NotAConceptError` (subclases de `BundleError`); `Bundle(root: Path)` con atributo `root` (resuelto), `read(concept_id: str, now: datetime | None = None) -> dict`, `_inside(rel: str, raw: str) -> Path`, `_concept_files() -> list[Path]`; función `_clean(raw: str) -> str`.

- [ ] **Step 1: Escribir los tests que fallan**

`tests/knowledge/test_okf_read.py`:
```python
"""Bundle.read: payload, normalización de IDs, links resueltos y confinamiento."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from astromesh.knowledge.okf import (
    Bundle,
    BundleError,
    ConceptNotFoundError,
    InvalidConceptError,
    NotAConceptError,
    OutsideBundleError,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "okf"
NOW = datetime(2026, 10, 11, tzinfo=UTC)
B = Bundle(FIX)


def test_read_payload():
    r = B.read("tables/orders", now=NOW)
    assert set(r) == {
        "id",
        "type",
        "title",
        "description",
        "tags",
        "status",
        "trust",
        "stale",
        "warnings",
        "extra",
        "body",
        "links",
    }
    assert r["id"] == "tables/orders"
    assert r["trust"] == "human-reviewed"
    assert r["warnings"] == []
    assert r["extra"]["resource"].startswith("https://console.cloud.google.com/")
    assert r["body"].startswith("# Schema")


@pytest.mark.parametrize(
    "raw",
    ["tables/orders", "/tables/orders.md", "./tables/orders.md", "tables/orders.md#schema"],
)
def test_ids_are_normalized(raw):
    assert B.read(raw)["id"] == "tables/orders"


def test_links_are_resolved_to_concept_ids():
    assert B.read("tables/orders")["links"] == [
        {"id": "metrics/revenue", "exists": True},
        {"id": "metrics/gross-margin", "exists": True},
        {"id": "metrics", "dir": True, "exists": True},
        {"id": "tables/customers", "exists": False},
        {"url": "https://example.com/orders", "external": True},
        {"id": "tables", "dir": True, "exists": True},
    ]


def test_relative_link_with_dot():
    assert B.read("metrics/gross-margin-legacy")["links"] == [
        {"id": "metrics/gross-margin", "exists": True}
    ]


def test_missing_concept_suggests_close_ids():
    with pytest.raises(ConceptNotFoundError) as exc:
        B.read("metrics/revenu")
    assert str(exc.value).startswith("concept not found: metrics/revenu (did you mean: ")
    assert "metrics/revenue" in str(exc.value)


def test_missing_concept_without_suggestions():
    with pytest.raises(ConceptNotFoundError, match=r"^concept not found: zzz/qqq$"):
        B.read("zzz/qqq")


def test_python_file_is_not_a_concept():
    with pytest.raises(NotAConceptError, match=r"^not a concept: attesters/check.py$"):
        B.read("attesters/check.py")


def test_reserved_file_is_not_a_concept():
    with pytest.raises(NotAConceptError, match=r"^not a concept: metrics/log$"):
        B.read("metrics/log")


def test_directory_is_not_a_concept():
    with pytest.raises(NotAConceptError, match=r"^not a concept: metrics$"):
        B.read("metrics")


def test_invalid_concept_is_reported():
    with pytest.raises(InvalidConceptError, match=r"^invalid concept metrics/broken: "):
        B.read("metrics/broken")


@pytest.mark.parametrize("raw", ["../outside", "/../../etc/passwd", "metrics/../../x"])
def test_traversal_is_blocked(raw):
    with pytest.raises(OutsideBundleError, match=r"^outside bundle: "):
        B.read(raw)


def test_absolute_path_never_reads_outside(tmp_path):
    secret = tmp_path / "secret.md"
    secret.write_text("---\ntype: X\n---\nSECRET")
    with pytest.raises(BundleError):
        B.read(str(secret))


def test_symlink_escaping_the_bundle_is_blocked(tmp_path):
    root = tmp_path / "b"
    root.mkdir()
    (root / "ok.md").write_text("---\ntype: X\n---\nok")
    secret = tmp_path / "secret.md"
    secret.write_text("---\ntype: X\n---\nSECRET")
    (root / "leak.md").symlink_to(secret)
    b = Bundle(root)
    assert b.read("ok")["body"] == "ok"
    with pytest.raises(OutsideBundleError):
        b.read("leak")
    with pytest.raises(OutsideBundleError):
        b.read("leak.md")
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/knowledge/test_okf_read.py -v`
Expected: FAIL con `ImportError: cannot import name 'Bundle'`

- [ ] **Step 3: Implementar**

Agregar a los imports de `astromesh/knowledge/okf.py`: `import difflib` y `import re`. Agregar al final del archivo:

```python
class OutsideBundleError(BundleError):
    """La ruta pedida resuelve fuera de la raíz del bundle."""


class ConceptNotFoundError(BundleError):
    """No hay concepto con ese ID."""


class NotAConceptError(BundleError):
    """La ruta existe pero no es un concepto (directorio, reservado o no-markdown)."""


# Links markdown (§6.1). Excluye imágenes (`![...]`); las notas al pie (`[^id]`) no
# llevan paréntesis y no matchean.
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(\s*([^)\s]+)[^)]*\)")
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _clean(raw: str) -> str:
    """Normaliza lo que manda el modelo: sin fragmento `#...` ni `/` inicial."""
    return str(raw or "").split("#", 1)[0].strip().lstrip("/")


class Bundle:
    """Un bundle OKF en disco, de sólo lectura. Lee en cada llamada: sin caché."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def _inside(self, rel: str, raw: str) -> Path:
        # `resolve` sigue symlinks ANTES del chequeo: un link que apunta afuera no pasa.
        path = (self.root / rel).resolve()
        if not path.is_relative_to(self.root):
            raise OutsideBundleError(f"outside bundle: {raw}")
        return path

    def _concept_path(self, raw: str) -> Path:
        rel = _clean(raw)
        base = self.root / rel
        # El `.md` se agrega antes de resolver: si no, un symlink `x.md` se chequearía
        # como `x` (que no existe) y se leería igual.
        if rel and not rel.endswith(".md") and not base.exists():
            rel += ".md"
        return self._inside(rel, raw)

    def _concept_files(self) -> list[Path]:
        out = []
        for path in self.root.rglob("*.md"):
            rel_parts = path.relative_to(self.root).parts
            if path.name in RESERVED or any(p.startswith(".") for p in rel_parts):
                continue
            if path.is_file() and path.resolve().is_relative_to(self.root):
                out.append(path)
        return sorted(out, key=lambda p: _id_of(self.root, p))

    def _not_found(self, cid: str) -> str:
        ids = [_id_of(self.root, p) for p in self._concept_files()]
        close = difflib.get_close_matches(cid, ids, n=3)
        msg = f"concept not found: {cid}"
        return f"{msg} (did you mean: {', '.join(close)}?)" if close else msg

    def read(self, concept_id: str, now: datetime | None = None) -> dict:
        path = self._concept_path(concept_id)
        cid = _id_of(self.root, path)
        if not path.exists():
            raise ConceptNotFoundError(self._not_found(cid))
        if path.is_dir() or path.suffix != ".md" or path.name in RESERVED:
            raise NotAConceptError(f"not a concept: {cid}")
        concept = parse_concept(self.root, path, now)
        return {
            **concept.summary(),
            "tags": concept.tags,
            "warnings": concept.warnings,
            "extra": concept.extra,
            "body": concept.body,
            "links": self._links(path, concept.body),
        }

    def _links(self, path: Path, body: str) -> list[dict]:
        """Links del cuerpo resueltos a IDs, para que el modelo no calcule rutas relativas."""
        out, seen = [], set()
        for target in _LINK.findall(body):
            if _SCHEME.match(target):
                item, key = {"url": target, "external": True}, target
            else:
                raw = target.split("#", 1)[0]
                if not raw:
                    continue  # ancla dentro del mismo concepto
                base = self.root if raw.startswith("/") else path.parent
                dest = (base / raw.lstrip("/")).resolve()
                if not dest.is_relative_to(self.root):
                    continue
                if raw.endswith("/") or dest.is_dir() or dest.name == "index.md":
                    folder = dest.parent if dest.name == "index.md" else dest
                    item = {"id": _id_of(self.root, folder), "dir": True, "exists": folder.is_dir()}
                else:
                    item = {"id": _id_of(self.root, dest), "exists": dest.is_file()}
                key = item["id"]
            if key not in seen:
                seen.add(key)
                out.append(item)
        return out
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/knowledge/ -v`
Expected: todos PASS.

- [ ] **Step 5: Lint y commit**

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add astromesh/knowledge/okf.py tests/knowledge/test_okf_read.py
git commit -m "feat(knowledge): Bundle.read con confinamiento y links resueltos

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `Bundle.index` y `Bundle.find`

**Files:**
- Modify: `astromesh/knowledge/okf.py` (métodos nuevos de `Bundle` y helpers)
- Create: `tests/knowledge/test_okf_index_find.py`

**Interfaces:**
- Consumes: `Bundle`, `_inside`, `_clean`, `_concept_files`, `parse_concept`, `split_frontmatter`, `InvalidConceptError`, `BundleError` (Tasks 1-2).
- Produces: `Bundle.index(path: str = "/", now: datetime | None = None) -> str`; `Bundle.find(text: str | None = None, type_: str | None = None, tags: list[str] | None = None, include_deprecated: bool = False, limit: int = 20, now: datetime | None = None) -> dict` que devuelve `{"results": [summary...], "skipped_invalid": int}`; constante `MAX_FIND_LIMIT = 100`.

- [ ] **Step 1: Escribir los tests que fallan**

`tests/knowledge/test_okf_index_find.py`:
```python
"""Bundle.index (existente y sintetizado, §8) y Bundle.find."""

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from astromesh.knowledge.okf import Bundle, BundleError, OutsideBundleError

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "okf"
NOW = datetime(2026, 10, 11, tzinfo=UTC)
B = Bundle(FIX)


def _ids(result):
    return [row["id"] for row in result["results"]]


def test_root_index_is_returned_without_frontmatter():
    out = B.index("/")
    assert out.startswith("# Subdirectories")
    assert "okf_version" not in out


def test_existing_subdirectory_index_is_returned_as_is():
    assert B.index("tables") == "# Tables\n\n* [Orders](orders.md) - One row per completed order.\n"


def test_missing_index_is_synthesized():
    assert B.index("metrics", now=NOW) == (
        "# Concepts\n"
        "\n"
        "* [Churn](metrics/churn) - Share of customers lost in a period. [metric, draft]\n"
        "* [Gross Margin](metrics/gross-margin) - Revenue minus cost of goods. [Metric, stale]\n"
        "* [Gross Margin (legacy)](metrics/gross-margin-legacy) - Retired definition."
        " [Metric, deprecated]\n"
        "* [legacy-v01](metrics/legacy-v01) [Reference]\n"
        "* [Revenue](metrics/revenue) - Recognized revenue for a fiscal year. [Metric]\n"
        "\n"
        "(2 concept(s) skipped: invalid frontmatter)\n"
    )


def test_synthesized_index_lists_subdirectories(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.md").write_text("---\ntype: X\n---\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / "top.md").write_text("---\ntype: X\ntitle: Top\n---\n")
    assert Bundle(tmp_path).index("/") == (
        "# Subdirectories\n\n* [a](a/)\n\n# Concepts\n\n* [Top](top) [X]\n"
    )


def test_empty_directory(tmp_path):
    (tmp_path / "empty").mkdir()
    assert Bundle(tmp_path).index("empty") == "(empty directory)\n"


def test_index_of_a_file_is_an_error():
    with pytest.raises(BundleError, match=r"^not a directory: metrics/revenue$"):
        B.index("metrics/revenue")


def test_index_outside_bundle_is_blocked():
    with pytest.raises(OutsideBundleError):
        B.index("../")


def test_synthesized_index_logs_skipped(caplog):
    with caplog.at_level(logging.WARNING, logger="astromesh.knowledge.okf"):
        B.index("metrics")
    assert "omitido" in caplog.text


def test_find_without_filters_excludes_deprecated_and_counts_invalid():
    r = B.find(now=NOW)
    assert _ids(r) == [
        "metrics/churn",
        "metrics/gross-margin",
        "metrics/legacy-v01",
        "metrics/revenue",
        "tables/orders",
    ]
    assert r["skipped_invalid"] == 2


def test_find_include_deprecated():
    assert "metrics/gross-margin-legacy" in _ids(B.find(include_deprecated=True))


def test_find_by_type_is_case_insensitive():
    assert _ids(B.find(type_="Metric")) == [
        "metrics/churn",
        "metrics/gross-margin",
        "metrics/revenue",
    ]


def test_find_by_tags_requires_all_case_insensitive():
    assert _ids(B.find(tags=["finance"])) == ["metrics/gross-margin", "metrics/revenue"]
    assert _ids(B.find(tags=["FINANCE", "margin"])) == ["metrics/gross-margin"]


def test_find_text_ranks_header_matches_before_body_matches():
    assert _ids(B.find(text="REVENUE")) == [
        "metrics/gross-margin",
        "metrics/revenue",
        "metrics/churn",
        "tables/orders",
    ]


def test_find_rows_have_summary_keys_only():
    row = B.find(text="orders")["results"][0]
    assert set(row) == {"id", "type", "title", "description", "status", "trust", "stale"}


def test_find_limit_is_clamped():
    assert len(B.find(limit=2)["results"]) == 2
    assert len(B.find(limit=0)["results"]) == 1
    assert len(B.find(limit=10_000)["results"]) == 5


def test_find_skips_hidden_dirs_and_escaping_symlinks(tmp_path):
    root = tmp_path / "b"
    root.mkdir()
    (root / "ok.md").write_text("---\ntype: X\n---\n")
    (root / ".git").mkdir()
    (root / ".git" / "hidden.md").write_text("---\ntype: X\n---\n")
    outside = tmp_path / "outdir"
    outside.mkdir()
    (outside / "leak.md").write_text("---\ntype: X\n---\nSECRET")
    (root / "linked").symlink_to(outside, target_is_directory=True)
    (root / "leak.md").symlink_to(outside / "leak.md")
    assert _ids(Bundle(root).find()) == ["ok"]
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/knowledge/test_okf_index_find.py -v`
Expected: FAIL con `AttributeError: 'Bundle' object has no attribute 'index'`

- [ ] **Step 3: Implementar**

Agregar en `astromesh/knowledge/okf.py`, junto a `RESERVED`:
```python
MAX_FIND_LIMIT = 100
```

Agregar como funciones de módulo (antes de `class Bundle`):
```python
def _strip_frontmatter(text: str) -> str:
    """Un `index.md` sólo lleva frontmatter en la raíz (`okf_version`, §12); se omite."""
    try:
        return split_frontmatter(text)[1]
    except InvalidConceptError:
        return text


def _index_line(c: Concept) -> str:
    flags = [c.type]
    if c.status != "stable":
        flags.append(c.status)
    if c.stale:
        flags.append("stale")
    desc = f" - {c.description}" if c.description else ""
    return f"* [{c.title}]({c.id}){desc} [{', '.join(flags)}]"


def _log_skipped(count: int, where: str) -> None:
    logger.warning("okf: %d concepto(s) inválido(s) omitido(s) en %s", count, where)
```

Agregar como métodos de `Bundle`:
```python
    def index(self, path: str = "/", now: datetime | None = None) -> str:
        folder = self._inside(_clean(path), path)
        if not folder.is_dir():
            raise BundleError(f"not a directory: {path}")
        existing = folder / "index.md"
        if existing.is_file() and existing.resolve().is_relative_to(self.root):
            return _strip_frontmatter(existing.read_text(encoding="utf-8-sig"))
        return self._synth_index(folder, now)

    def _synth_index(self, folder: Path, now: datetime | None) -> str:
        """Índice en el formato de la §8 cuando el directorio no trae `index.md`."""
        lines: list[str] = []
        subdirs = sorted(
            p
            for p in folder.iterdir()
            if p.is_dir() and not p.name.startswith(".") and p.resolve().is_relative_to(self.root)
        )
        if subdirs:
            lines += ["# Subdirectories", ""]
            lines += [f"* [{p.name}]({_id_of(self.root, p)}/)" for p in subdirs]
        concepts, skipped = [], 0
        for path in folder.glob("*.md"):
            if path.name in RESERVED or not path.resolve().is_relative_to(self.root):
                continue
            try:
                concepts.append(parse_concept(self.root, path, now))
            except InvalidConceptError:
                skipped += 1
        if concepts:
            if lines:
                lines.append("")
            lines += ["# Concepts", ""]
            lines += [_index_line(c) for c in sorted(concepts, key=lambda c: c.id)]
        if skipped:
            _log_skipped(skipped, _id_of(self.root, folder))
            lines += ["", f"({skipped} concept(s) skipped: invalid frontmatter)"]
        return "\n".join(lines) + "\n" if lines else "(empty directory)\n"

    def find(
        self,
        text: str | None = None,
        type_: str | None = None,
        tags: list[str] | None = None,
        include_deprecated: bool = False,
        limit: int = 20,
        now: datetime | None = None,
    ) -> dict:
        # ponytail: recorre y parsea todos los archivos en cada llamada; anda con cientos
        # o pocos miles de conceptos. Más grande que eso, ingesta a RAGPipeline.
        limit = max(1, min(int(limit), MAX_FIND_LIMIT))
        want_tags = {t.lower() for t in tags or []}
        needle = text.lower() if text else None
        header_hits, body_hits, skipped = [], [], 0
        for path in self._concept_files():
            try:
                c = parse_concept(self.root, path, now)
            except InvalidConceptError:
                skipped += 1
                continue
            if c.status == "deprecated" and not include_deprecated:
                continue
            if type_ and c.type.lower() != type_.lower():
                continue
            if not want_tags <= {t.lower() for t in c.tags}:
                continue
            if needle is None or needle in " ".join([c.title, c.description, *c.tags]).lower():
                header_hits.append(c)
            elif needle in c.body.lower():
                body_hits.append(c)
        if skipped:
            _log_skipped(skipped, "/")
        hits = (header_hits + body_hits)[:limit]
        return {"results": [c.summary() for c in hits], "skipped_invalid": skipped}
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/knowledge/ -v`
Expected: todos PASS.

- [ ] **Step 5: Lint y commit**

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add astromesh/knowledge/okf.py tests/knowledge/test_okf_index_find.py
git commit -m "feat(knowledge): índice sintetizado y búsqueda sobre el bundle OKF

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Tools, conexión en el engine y schema

**Files:**
- Create: `astromesh/knowledge/tools.py`
- Modify: `astromesh/runtime/engine.py` (import `asyncio`; `_resolve_bundle` junto a `_resolve_rag`; `_build_agent`; `Agent.__init__` y `Agent.run`)
- Modify: `vscode-extension/schemas/agent.schema.json` (bloque `knowledge`)
- Create: `tests/knowledge/test_okf_tools.py`
- Create: `tests/knowledge/test_okf_engine.py`
- Modify: `tests/test_agent_knowledge_schema.py`

**Interfaces:**
- Consumes: `Bundle` (`index`, `read`, `find(..., type_=...)`), `BundleError` (Tasks 1-3).
- Produces: `TOOL_NAMES = ("kb_index", "kb_read", "kb_find")`, `register_bundle_tools(registry: ToolRegistry, bundle: Bundle) -> None` (levanta `ValueError` si alguno de los nombres ya está); `AgentRuntime._resolve_bundle(spec: dict, agent_name: str) -> Bundle | None`; `Agent(..., bundle=None)`; variable de template `bundle_index`.

- [ ] **Step 1: Escribir los tests que fallan**

`tests/knowledge/test_okf_tools.py`:
```python
"""Las tres tools sobre un ToolRegistry real: resultados, errores y argumentos sueltos."""

import json
from pathlib import Path

import pytest

from astromesh.core.tools import ToolRegistry
from astromesh.knowledge.okf import Bundle
from astromesh.knowledge.tools import TOOL_NAMES, register_bundle_tools

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "okf"


def _registry():
    registry = ToolRegistry()
    register_bundle_tools(registry, Bundle(FIX))
    return registry


def test_registers_the_three_tools():
    names = [s["function"]["name"] for s in _registry().get_tool_schemas()]
    assert sorted(names) == sorted(TOOL_NAMES)


async def test_kb_read_returns_the_concept_and_is_json_serializable():
    out = await _registry().execute("kb_read", {"concept_id": "metrics/revenue"})
    assert out["success"] is True
    assert out["data"]["title"] == "Revenue"
    json.dumps(out)


async def test_errors_come_back_as_results():
    out = await _registry().execute("kb_read", {"concept_id": "../outside"})
    assert out["success"] is False
    assert out["error"].startswith("outside bundle: ")


async def test_kb_index_defaults_to_root():
    out = await _registry().execute("kb_index", {})
    assert out["success"] is True
    assert out["data"].startswith("# Subdirectories")


async def test_kb_find_maps_type_and_tolerates_loose_arguments():
    out = await _registry().execute(
        "kb_find", {"type": "Metric", "tags": "finance", "limit": "2", "query": "ignored"}
    )
    assert out["success"] is True
    assert [r["id"] for r in out["data"]["results"]] == ["metrics/gross-margin", "metrics/revenue"]


async def test_kb_find_bad_limit_falls_back_to_default():
    out = await _registry().execute("kb_find", {"limit": "many"})
    assert out["success"] is True
    assert len(out["data"]["results"]) == 5


def test_collision_with_an_existing_tool_raises():
    registry = ToolRegistry()

    async def _h(**_):
        return {}

    registry.register_internal(name="kb_read", handler=_h, description="x", parameters={})
    with pytest.raises(ValueError, match="kb_read"):
        register_bundle_tools(registry, Bundle(FIX))
```

`tests/knowledge/test_okf_engine.py`:
```python
"""`spec.knowledge.bundle` en el engine: tools registradas y `bundle_index` en el template."""

import logging
from pathlib import Path

import pytest

from astromesh.knowledge.okf import Bundle
from astromesh.knowledge.tools import TOOL_NAMES
from astromesh.runtime.engine import Agent, AgentRuntime

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "okf"


def _config(knowledge, tools=None):
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "kb-agent", "version": "1.0.0"},
        "spec": {
            "model": {"primary": {"provider": "ollama", "model": "llama3.1:8b"}},
            "orchestration": {"pattern": "react"},
            "knowledge": knowledge,
            "tools": tools or [],
        },
    }


def _names(agent):
    return {s["function"]["name"] for s in agent._tools.get_tool_schemas()}


def test_relative_bundle_resolves_against_config_dir():
    agent = AgentRuntime(config_dir=str(FIX.parent))._build_agent(_config({"bundle": "okf"}))
    assert set(TOOL_NAMES) <= _names(agent)


def test_absolute_bundle_path():
    agent = AgentRuntime(config_dir="./config")._build_agent(_config({"bundle": str(FIX)}))
    assert set(TOOL_NAMES) <= _names(agent)


def test_missing_bundle_warns_and_registers_nothing(caplog):
    with caplog.at_level(logging.WARNING):
        agent = AgentRuntime(config_dir=str(FIX.parent))._build_agent(
            _config({"bundle": "nope"})
        )
    assert not set(TOOL_NAMES) & _names(agent)
    assert "knowledge.bundle" in caplog.text


def test_declared_tool_with_a_kb_name_collides():
    with pytest.raises(ValueError, match="kb_read"):
        AgentRuntime(config_dir=str(FIX.parent))._build_agent(
            _config({"bundle": "okf"}, tools=[{"name": "kb_read", "type": "agent", "agent": "x"}])
        )


def test_bundle_and_pipeline_coexist():
    agent = AgentRuntime(config_dir=str(FIX.parent))._build_agent(
        _config({"bundle": "okf", "pipeline": "unknown-pipeline"})
    )
    assert set(TOOL_NAMES) <= _names(agent)


class _RecordingPromptEngine:
    def __init__(self):
        self.context = None

    def render(self, template, context):
        self.context = context
        return "SYSTEM"


class _StubPattern:
    async def execute(self, *a, **k):
        return {"answer": "ok"}


class _StubMemory:
    async def build_context(self, *a, **k):
        return {}

    def fit_history(self, context, budget):
        return {"turns_kept": 0, "turns_dropped": 0, "tokens": 0, "summary_used": False}

    async def persist_turn(self, *a, **k):
        return None


class _StubTools:
    def get_tool_schemas(self, *a, **k):
        return []


def _runner(bundle):
    pe = _RecordingPromptEngine()
    runner = Agent(
        name="a1",
        version="1",
        namespace="default",
        description="",
        routers={"default": None},
        memory=_StubMemory(),
        tools=_StubTools(),
        pattern=_StubPattern(),
        system_prompt="hola",
        prompt_engine=pe,
        guardrails={},
        permissions={},
        orchestration_config={},
        bundle=bundle,
    )
    return runner, pe


async def test_bundle_index_reaches_the_template():
    runner, pe = _runner(Bundle(FIX))
    await runner.run("hola", session_id="s1")
    assert pe.context["bundle_index"].startswith("# Subdirectories")


async def test_no_bundle_gives_empty_bundle_index():
    runner, pe = _runner(None)
    await runner.run("hola", session_id="s1")
    assert pe.context["bundle_index"] == ""


async def test_bundle_that_disappears_does_not_break_the_run(tmp_path):
    root = tmp_path / "gone"
    root.mkdir()
    bundle = Bundle(root)
    root.rmdir()
    runner, pe = _runner(bundle)
    await runner.run("hola", session_id="s1")
    assert pe.context["bundle_index"] == ""
```

Agregar al final de `tests/test_agent_knowledge_schema.py`:
```python
def test_agent_with_knowledge_bundle_validates():
    validate(instance=_agent({"bundle": "knowledge/acme_retail"}), schema=_schema())


def test_agent_with_bundle_and_pipeline_validates():
    validate(instance=_agent({"bundle": "kb", "pipeline": "pk", "top_k": 3}), schema=_schema())


def test_agent_knowledge_bundle_must_be_a_string():
    with pytest.raises(ValidationError):
        validate(instance=_agent({"bundle": 3}), schema=_schema())
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/knowledge/test_okf_tools.py tests/knowledge/test_okf_engine.py tests/test_agent_knowledge_schema.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'astromesh.knowledge.tools'` (y los de schema con `ValidationError`).

- [ ] **Step 3: Implementar las tools**

`astromesh/knowledge/tools.py`:
```python
"""Las tres tools con que un agente navega su knowledge bundle OKF.

Las registra el engine cuando el agente declara `spec.knowledge.bundle`; el agente no las
declara en `spec.tools`. Como `rag_query`, nunca levantan: un error vuelve como resultado.
"""

from __future__ import annotations

import asyncio

from astromesh.core.tools import ToolRegistry
from astromesh.knowledge.okf import Bundle, BundleError
from astromesh.tools.base import ToolResult

TOOL_NAMES = ("kb_index", "kb_read", "kb_find")

_INDEX = (
    "List a directory of the knowledge bundle. Start here with path '/'. Links inside an "
    "existing index are relative to the listed directory."
)
_READ = (
    "Read one concept of the knowledge bundle: metadata, trust warnings, body, and its "
    "links already resolved to concept ids you can pass back to kb_read."
)
_FIND = (
    "Search concepts of the knowledge bundle by type, tags (all must match) and text. "
    "Deprecated concepts are excluded unless include_deprecated is true."
)


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


async def _call(fn, *args, **kwargs) -> dict:
    try:
        data = await asyncio.to_thread(fn, *args, **kwargs)
    except BundleError as exc:
        return ToolResult(success=False, data=None, error=str(exc)).to_dict()
    except OSError as exc:  # permisos, o un archivo que desaparece entre listar y leer
        return ToolResult(success=False, data=None, error=f"bundle read failed: {exc}").to_dict()
    return ToolResult(success=True, data=data).to_dict()


def register_bundle_tools(registry: ToolRegistry, bundle: Bundle) -> None:
    taken = [name for name in TOOL_NAMES if name in registry._tools]
    if taken:
        raise ValueError(
            f"knowledge.bundle registraría {', '.join(taken)}, que el agente ya tiene"
        )

    # `**_ignored`: una clave inventada por el modelo no puede tirar la llamada con TypeError.
    async def kb_index(path: str = "/", **_ignored) -> dict:
        return await _call(bundle.index, path)

    async def kb_read(concept_id: str = "", **_ignored) -> dict:
        return await _call(bundle.read, concept_id)

    async def kb_find(
        text=None, type=None, tags=None, include_deprecated=False, limit=20, **_ignored
    ) -> dict:
        return await _call(
            bundle.find,
            text=text,
            type_=type,
            tags=[tags] if isinstance(tags, str) else tags,
            include_deprecated=bool(include_deprecated),
            limit=_int(limit, 20),
        )

    registry.register_internal(
        name="kb_index",
        handler=kb_index,
        description=_INDEX,
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "default": "/"}},
        },
    )
    registry.register_internal(
        name="kb_read",
        handler=kb_read,
        description=_READ,
        parameters={
            "type": "object",
            "properties": {"concept_id": {"type": "string"}},
            "required": ["concept_id"],
        },
    )
    registry.register_internal(
        name="kb_find",
        handler=kb_find,
        description=_FIND,
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "type": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "include_deprecated": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 20, "maximum": 100},
            },
        },
    )
```

- [ ] **Step 4: Conectar el engine**

En `astromesh/runtime/engine.py`:

1. Imports: agregar `import asyncio` al bloque de stdlib (orden alfabético, antes de `import contextlib`).

2. Agregar el método justo después de `_resolve_rag` (dentro de `AgentRuntime`):
```python
    def _resolve_bundle(self, spec: dict, agent_name: str):
        """`spec.knowledge.bundle`: un directorio OKF. Sin él, el agente sigue sin bundle."""
        from astromesh.knowledge.okf import Bundle

        raw = (spec.get("knowledge") or {}).get("bundle")
        if not raw:
            return None
        path = Path(raw)
        if not path.is_absolute():
            path = self._config_dir / path
        if not path.is_dir():
            logger.warning(
                "agent %r: knowledge.bundle %s no es un directorio; sigue sin bundle",
                agent_name,
                path,
            )
            return None
        return Bundle(path)
```

3. En `_build_agent`, justo después de `rag = self._resolve_rag(spec)`:
```python
        bundle = self._resolve_bundle(spec, metadata["name"])
```

4. En `_build_agent`, después del loop `for tool_def in spec.get("tools", []):` y antes del bloque de comentario que precede a `for nombre, (quien, definicion) in vigiladas.items():` (empieza con `# El chequeo de adentro sólo ve lo registrado ANTES de la ...`):
```python
        if bundle is not None:
            from astromesh.knowledge.tools import register_bundle_tools

            register_bundle_tools(tools, bundle)
```

5. En el `return Agent(...)` de `_build_agent`, agregar `bundle=bundle,` después de `rag=rag,`.

6. En `class Agent`: agregar el default de clase debajo de `_presupuesto_tools` (hay tests que arman un `Agent` sin `__init__`):
```python
    _bundle = None
```
agregar el parámetro `bundle=None,` al final de la firma de `__init__` (después de `presupuesto_tools=None,`), y debajo de `self._rag = rag`:
```python
        self._bundle = bundle
```

7. En `class Agent`, agregar el método (por ejemplo después de `__init__`):
```python
    async def _bundle_index(self) -> str:
        """El mapa del bundle para el template. Como el RAG, nunca rompe una corrida."""
        if self._bundle is None:
            return ""
        from astromesh.knowledge.okf import BundleError

        try:
            return await asyncio.to_thread(self._bundle.index, "/")
        except (BundleError, OSError):
            logger.warning(
                "agent %r: no se pudo leer el índice del bundle", self.name, exc_info=True
            )
            return ""
```

8. En `Agent.run`, en el bloque `variables = { ... }` (después de `prompt_span = tracing.start_span("prompt_render")`), agregar la clave:
```python
                "bundle_index": await self._bundle_index(),
```
debajo de `"prefetch": prefetch_resultados,`. No tocar `_per_query_vars_in`: `bundle_index` es estable entre queries y puede ir en `prompts.system`.

- [ ] **Step 5: Schema**

En `vscode-extension/schemas/agent.schema.json`, reemplazar el bloque `"knowledge"` completo por:
```json
        "knowledge": {
          "type": "object",
          "description": "Knowledge configuration: a RAGPipeline retrieved at run time, an OKF knowledge bundle the agent navigates with kb_index/kb_read/kb_find, or both.",
          "additionalProperties": false,
          "anyOf": [
            { "required": ["pipeline"] },
            { "required": ["bundle"] }
          ],
          "properties": {
            "pipeline": {
              "type": "string",
              "description": "metadata.name of a RAGPipeline resource to retrieve from."
            },
            "top_k": {
              "type": "integer",
              "description": "Number of chunks to retrieve per run (defaults to the pipeline's retrieval.top_k). Applies to pipeline only."
            },
            "bundle": {
              "type": "string",
              "description": "Directory of an Open Knowledge Format (OKF) bundle, relative to the config directory or absolute. Registers kb_index, kb_read and kb_find, and exposes bundle_index to the prompt templates."
            }
          }
        },
```

- [ ] **Step 6: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/knowledge/ tests/test_agent_knowledge_schema.py tests/test_rag_injection.py tests/test_engine_builtin.py -v`
Expected: todos PASS.

Run: `uv run pytest -q -x` (la suite completa, sola; no correrla en paralelo con otra corrida de pytest)
Expected: PASS.

- [ ] **Step 7: Lint y commit**

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add astromesh/knowledge/tools.py astromesh/runtime/engine.py vscode-extension/schemas/agent.schema.json tests/knowledge tests/test_agent_knowledge_schema.py
git commit -m "feat(knowledge): tools kb_* y spec.knowledge.bundle en el engine

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Ejemplo, documentación y verificación contra los bundles de Google

**Files:**
- Create: `config/knowledge/okf-demo/index.md`
- Create: `config/knowledge/okf-demo/policies/refunds.md`
- Create: `config/knowledge/okf-demo/policies/refunds-2024.md`
- Create: `config/knowledge/okf-demo/products/plans.md`
- Create: `config/agents/okf-demo.agent.yaml`
- Create: `tests/knowledge/test_okf_demo.py`
- Create: `docs-site/src/content/docs/advanced/knowledge-bundles.md`
- Modify: `docs-site/astro.config.mjs` (sidebar `Advanced`)
- Modify: `docs-site/src/content/docs/configuration/agent-yaml.md` (sección nueva `spec.knowledge`)

**Interfaces:**
- Consumes: `Bundle`, `TOOL_NAMES`, `AgentRuntime._build_agent` (Tasks 1-4).

- [ ] **Step 1: Escribir el test que falla**

`tests/knowledge/test_okf_demo.py`:
```python
"""El ejemplo de config/ construye y su bundle es conformante."""

from pathlib import Path

import yaml

from astromesh.knowledge.okf import Bundle
from astromesh.knowledge.tools import TOOL_NAMES
from astromesh.runtime.engine import AgentRuntime


def test_demo_agent_builds_with_the_bundle_tools():
    cfg = yaml.safe_load(Path("config/agents/okf-demo.agent.yaml").read_text())
    agent = AgentRuntime(config_dir="./config")._build_agent(cfg)
    names = {s["function"]["name"] for s in agent._tools.get_tool_schemas()}
    assert set(TOOL_NAMES) <= names


def test_demo_bundle_has_no_invalid_concepts():
    result = Bundle(Path("config/knowledge/okf-demo")).find(include_deprecated=True)
    assert result["skipped_invalid"] == 0
    assert len(result["results"]) == 3
```

Run: `uv run pytest tests/knowledge/test_okf_demo.py -v`
Expected: FAIL con `FileNotFoundError` (`config/agents/okf-demo.agent.yaml`).

- [ ] **Step 2: Bundle y agente de ejemplo**

`config/knowledge/okf-demo/index.md`:
```markdown
---
okf_version: "0.2"
---
# Subdirectories

* [policies](policies/) - Customer-facing policies.
* [products](products/) - What we sell.
```

`config/knowledge/okf-demo/policies/refunds.md`:
```markdown
---
type: Policy
title: Refund policy
description: Customers can ask for a full refund within 30 days of purchase.
tags: [support, refunds]
status: stable
generated: { by: human:support-lead, at: 2026-09-01T12:00:00Z }
verified: { by: human:support-lead, at: 2026-09-01T12:00:00Z }
stale_after: 2027-09-01T00:00:00Z
---

# Rule

A full refund is available within 30 days of purchase for every plan in
[plans](/products/plans.md). After 30 days, refunds are prorated for annual plans only.

# Replaces

This policy replaces the [2024 refund policy](./refunds-2024.md).
```

`config/knowledge/okf-demo/policies/refunds-2024.md`:
```markdown
---
type: Policy
title: Refund policy (2024)
description: Retired 14-day refund window.
tags: [support, refunds]
status: deprecated
generated: { by: human:support-lead, at: 2024-01-10T12:00:00Z }
---

Refunds were accepted within 14 days. Superseded by the [current policy](./refunds.md).
```

`config/knowledge/okf-demo/products/plans.md`:
```markdown
---
type: Reference
title: Plans
description: The three subscription plans and their prices.
tags: [products, pricing]
generated: { by: process:catalog-export, at: 2026-09-15T00:00:00Z }
verified: { by: process:catalog-export, at: 2026-09-15T00:00:00Z }
---

# Plans

| Plan | Monthly | Annual |
|---|---|---|
| Starter | USD 19 | USD 190 |
| Team | USD 49 | USD 490 |
| Business | USD 99 | USD 990 |

Refund rules are in the [refund policy](/policies/refunds.md).
```

`config/agents/okf-demo.agent.yaml`:
```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: okf-demo
  version: "1.0.0"
  namespace: examples

spec:
  identity:
    display_name: "OKF Demo"
    description: "Responde navegando un knowledge bundle Open Knowledge Format"

  model:
    primary:
      provider: ollama
      model: "llama3.1:8b"
      endpoint: "http://localhost:11434"
      parameters:
        temperature: 0.1
        max_tokens: 1024

  knowledge:
    bundle: knowledge/okf-demo

  prompts:
    system: |
      You answer customer questions using only the knowledge bundle.
      Use kb_find or kb_index to locate concepts and kb_read to open them;
      follow their links when you need more context.
      Never rely on a concept whose warnings say DEPRECATED, and say so when
      the only source you found is STALE or DRAFT.

      Bundle map:
      {{ bundle_index }}

  orchestration:
    pattern: react
    max_iterations: 6
```

- [ ] **Step 3: Correr el test y verificar que pasa**

Run: `uv run pytest tests/knowledge/test_okf_demo.py -v`
Expected: PASS.

- [ ] **Step 4: Documentación**

`docs-site/src/content/docs/advanced/knowledge-bundles.md`:
````markdown
---
title: Knowledge Bundles (OKF)
description: Give an agent an Open Knowledge Format bundle and let it navigate the concepts it needs, with trust and freshness signals intact
---

[Open Knowledge Format](https://github.com/GoogleCloudPlatform/open-knowledge-format) (OKF) is an open spec for knowledge as a directory of markdown files with YAML frontmatter, cross-linked like a wiki. Astromesh reads OKF v0.2 bundles (and v0.1 ones) as they are: no conversion, no embeddings, no vector store. The agent navigates the bundle with three tools and opens only what it needs.

## Configuration

```yaml
spec:
  knowledge:
    bundle: knowledge/acme_retail   # relative to the config directory, or absolute
```

`bundle` can sit next to `pipeline`; they are independent. If the directory does not exist the agent logs a warning and runs without it.

## What the agent gets

| Tool | Arguments | Returns |
|------|-----------|---------|
| `kb_index` | `path` (default `/`) | The directory's `index.md`, or one synthesized from the concepts' frontmatter when it is missing. |
| `kb_read` | `concept_id` | `type`, `title`, `trust`, `stale`, `warnings`, the body, unknown frontmatter under `extra`, and the body's `links` already resolved to concept ids. |
| `kb_find` | `text`, `type`, `tags`, `include_deprecated`, `limit` | Matching concepts (no body). Title, description and tag matches come before body matches. Deprecated concepts are left out unless asked for. |

The template variable `bundle_index` holds the root index. It does not change between queries, so it can go in `prompts.system` without breaking the prompt cache, and it saves the agent its first `kb_index` call.

If the agent sets `permissions.allowed_actions`, add `kb_index`, `kb_read` and `kb_find` to it.

## Trust and freshness

Signals are reported, never used to hide a concept:

- `trust`: `human-reviewed` when any `verified` entry is by `human:…`, `machine-confirmed` when only agents or processes verified it, `unverified` otherwise.
- `stale`: true once `stale_after` has passed.
- `warnings`: plain sentences for the model, e.g. `DEPRECATED: kept for history; do not use for new work.`

Tell the agent what to do with them in its prompt. The example below refuses deprecated sources and flags stale or draft ones.

## Tolerance

A concept is skipped only when its frontmatter cannot be parsed or has no `type`. Unknown types, unknown keys, missing optional fields and broken links are fine. `kb_index` and `kb_find` report how many concepts they skipped.

## Example

`config/agents/okf-demo.agent.yaml` answers support questions from `config/knowledge/okf-demo/`, a four-file bundle with a current policy, a deprecated one and a product reference.

## Security and limits

- The tools are read-only and never leave the bundle's root, symlinks included. Only `.md` concepts are read; nothing in the bundle is executed, including `Attested Computation` concepts.
- A concept's body reaches the model like any tool result. Mount bundles only from sources you trust.
- `kb_find` scans the whole bundle on each call. That is fine for hundreds to a few thousand concepts.
- Not supported yet: running Attested Computations, writing bundles, remote bundles (git or tarball), ingesting a bundle into a `RAGPipeline`.
````

`docs-site/astro.config.mjs`: en el grupo `Advanced`, debajo de `{ label: 'Agent Evals', slug: 'advanced/evals' },` agregar:
```js
            { label: 'Knowledge Bundles (OKF)', slug: 'advanced/knowledge-bundles' },
```

`docs-site/src/content/docs/configuration/agent-yaml.md`: agregar una sección nueva justo antes de `### \`spec.guardrails\``:
````markdown
### `spec.knowledge`

| Field | Required | Description |
|-------|----------|-------------|
| `pipeline` | One of `pipeline`/`bundle` | `metadata.name` of a `RAGPipeline`. Retrieved chunks reach the templates as `knowledge`. |
| `top_k` | No | Chunks per run for `pipeline`. Defaults to the pipeline's `retrieval.top_k`. |
| `bundle` | One of `pipeline`/`bundle` | Directory of an [OKF knowledge bundle](/astromesh/advanced/knowledge-bundles/), relative to the config directory or absolute. Registers `kb_index`, `kb_read` and `kb_find`, and exposes `bundle_index` to the templates. |

```yaml
knowledge:
  pipeline: product-knowledge
  bundle: knowledge/acme_retail
```

````

- [ ] **Step 5: Verificar contra los bundles de muestra de Google**

```bash
mkdir -p "$CLAUDE_JOB_DIR/tmp/okf-samples" && cd "$CLAUDE_JOB_DIR/tmp/okf-samples" \
  && (test -d open-knowledge-format || git clone --depth 1 -q https://github.com/GoogleCloudPlatform/open-knowledge-format) \
  && cd /Users/fulfaro/monaccode/astromesh-okf \
  && uv run python - "$CLAUDE_JOB_DIR/tmp/okf-samples/open-knowledge-format" <<'EOF'
import sys
from pathlib import Path
from astromesh.knowledge.okf import Bundle

repo = Path(sys.argv[1])
roots = sorted(d for b in repo.rglob("bundles") if b.is_dir() for d in b.iterdir() if d.is_dir())
assert roots, f"no bundles under {repo}"
for root in roots:
    b = Bundle(root)
    found = b.find(include_deprecated=True, limit=100)
    assert found["skipped_invalid"] == 0, (root, found["skipped_invalid"])
    b.index("/")
    for row in found["results"]:
        b.read(row["id"])
    print(f"{root.name}: {len(found['results'])} concepts OK")
EOF
```
Expected: una línea `<bundle>: N concepts OK` por bundle (`acme_retail`, `crypto_bitcoin`, `ga4`, `stackoverflow` o los que traiga el repo canónico) y ningún `AssertionError`. Si el repo canónico no tiene `bundles/`, usar `https://github.com/GoogleCloudPlatform/knowledge-catalog` (subdirectorio `okf/bundles`, snapshot congelado). Si un concepto queda omitido, mirar el archivo: si es conformante según la §11 de la spec (frontmatter YAML con `type` no vacío), es un bug del parser y se arregla con su test antes de seguir; si no lo es, anotarlo en el reporte como hallazgo del bundle.

- [ ] **Step 6: Suite completa, lint y commit**

```bash
uv run pytest -q
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add config/knowledge/okf-demo config/agents/okf-demo.agent.yaml tests/knowledge/test_okf_demo.py docs-site/src/content/docs/advanced/knowledge-bundles.md docs-site/astro.config.mjs docs-site/src/content/docs/configuration/agent-yaml.md
git commit -m "feat(knowledge): agente okf-demo y documentación de knowledge bundles

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
Expected: la suite PASS, el lint limpio.
