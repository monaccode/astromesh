"""Open Knowledge Format (OKF) v0.2: lectura de bundles para que un agente los navegue.

Spec: https://github.com/GoogleCloudPlatform/open-knowledge-format (SPEC.md). Sólo se
consume: nada del bundle se escribe ni se ejecuta (tampoco las Attested Computations).
Tolerante como pide la §11: un concepto es inválido sólo sin frontmatter parseable o sin
`type`. Campos opcionales faltantes, tipos y claves desconocidas y links rotos nunca lo
invalidan.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
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
            except (yaml.YAMLError, ValueError) as exc:
                raise InvalidConceptError(
                    f"unparseable frontmatter ({exc.__class__.__name__})"
                ) from None
            if not isinstance(meta, dict):
                # ValueError y no TypeError: es el contrato que atrapan las tools.
                raise InvalidConceptError("frontmatter is not a mapping")
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


def _stringify_keys(obj):
    """Recursively convert dict keys to strings for JSON serialization."""
    if isinstance(obj, dict):
        return {str(k): _stringify_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_stringify_keys(item) for item in obj]
    return obj


def _jsonable(meta: dict) -> dict:
    """`extra` viaja en un resultado de tool: las fechas de YAML pasan a ISO 8601."""
    stringified = _stringify_keys(meta)
    return json.loads(json.dumps(stringified, default=_stamp))


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
