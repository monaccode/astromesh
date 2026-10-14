# Guardrails que se aplican — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que `spec.guardrails` se aplique en cada corrida de agente: entrada filtrada antes del modelo, salida filtrada (también en el stream), bloqueos como respuesta de rechazo y `cost_limit` como presupuesto real de tokens.

**Architecture:** `core/guardrails.py` se reescribe como motor sincrónico que normaliza/valida reglas al construirse y expone `check_input`, `check_output`, `filter_stream`, `check_budget`, `tokens_of`; bloquear es levantar `GuardrailBlocked`. `Agent.run` (`runtime/engine.py`) lo construye una vez por agente y lo llama en cuatro puntos; un `except GuardrailBlocked` arma el resultado de rechazo. La API y el WebSocket exponen `blocked` y `guardrail`.

**Tech Stack:** Python 3.12, pytest (asyncio auto), FastAPI, extensión nativa opcional `astromesh._native` (`RustPiiRedactor`, `RustTopicFilter`).

**Spec:** `docs/superpowers/specs/2026-10-13-guardrails-enforced-design.md`

## Global Constraints

- Mensaje de rechazo por default: `"I can't help with that request."` (exacto).
- Etiquetas PII: `[REDACTED_EMAIL]`, `[REDACTED_PHONE]`, `[REDACTED_SSN]`, `[REDACTED_CC]`; reemplazo de `content_filter`: `[FILTERED]`.
- Ningún manifiesto deja de cargar por sus guardrails: lo inválido se descarta con `logger.warning`.
- `cost_limit` se chequea **antes** de cada llamada al modelo; la llamada que cruza el límite se completa.
- Resultado de toda corrida: `blocked: bool` y `guardrail: dict | None`; bloqueada → `guardrail = {"direction": "input"|"output"|"run", "rule": <type>, "reason": <texto sin el contenido bloqueado>}`.
- Nunca poner texto del usuario o del modelo en atributos de span de guardrails.
- Release: core 0.70.0 (lo hace el controlador al final, no una tarea).
- Antes de cada commit: `uv run ruff check astromesh/ tests/` **y** `uv run ruff format --check astromesh/ tests/` (CI corre ambos).
- Commits `feat:`/`fix:`/`refactor:` llevan su entrada en `CHANGELOG.md` `## [Unreleased]` en el mismo commit (regla del repo). Trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Query multimodal (lista de partes) con un email en una parte `text` → el modelo recibe la parte redactada y la parte imagen intacta (test en Task 2).
2. Salida bloqueada en una corrida que registró una confirmación pendiente → la propuesta se descarta; un "si" posterior no la autoriza (test en Task 2).
3. Patrón que se traga o envuelve `GuardrailBlocked` (Glyph reintenta ante `GlyphExecutionError`) → la corrida devuelve igual el rechazo de `cost_limit` (test en Task 3).
4. Agente sin guardrails → resultado idéntico al previo salvo `blocked: False`, `guardrail: None`, y sin spans `guardrails.*` (test en Task 2).
5. `content_filter` con `action: block` → el evento `token` no se emite y `answer` es el mensaje (test en Task 3).

---

### Task 1: Motor de guardrails

**Files:**
- Modify (reescritura completa): `astromesh/core/guardrails.py`
- Test (reescritura completa): `tests/test_guardrails.py`
- Modify: `CHANGELOG.md` (`## [Unreleased]`)

**Interfaces:**
- Produces:
  - `DEFAULT_MESSAGE: str`
  - `class GuardrailBlocked(Exception)` con atributos `direction, rule, reason, message` y `as_dict() -> dict` (`{"direction","rule","reason"}`)
  - `@dataclass GuardrailReport(text: str, rules: list[str], redactions: int, warnings: int)`
  - `class GuardrailsEngine(config: dict | None = None, agent_name: str = "agent")` con:
    - `has_input: bool`, `has_output: bool` (properties; `cost_limit` no cuenta)
    - `cost_limit: dict | None` (`{"type","action","message","max_tokens","count"}`)
    - `check_input(text: str) -> GuardrailReport` / `check_output(text: str) -> GuardrailReport` (levantan `GuardrailBlocked`)
    - `filter_stream(text: str) -> str | None` (None = no emitir)
    - `check_budget(counted: int) -> None` (levanta `GuardrailBlocked(direction="run", rule="cost_limit")`)
    - `tokens_of(usage: dict | None) -> int`
  - Se eliminan `apply_input`, `apply_output`, `_redact_pii` y `GuardrailResult` (no tienen llamadores fuera de los tests viejos; verificar con `grep -rn "apply_input\|apply_output\|GuardrailResult" astromesh astromesh-adk tests` antes de borrar — si aparece algún llamador, parar y reportarlo).

- [ ] **Step 1: Reescribir el test**

`tests/test_guardrails.py`:

```python
import logging

import pytest

from astromesh.core import guardrails as g
from astromesh.core.guardrails import DEFAULT_MESSAGE, GuardrailBlocked, GuardrailsEngine


@pytest.fixture(params=["python", "native"])
def ruta(request, monkeypatch):
    """Cada test corre por la ruta Python y, si está compilada, por la nativa."""
    if request.param == "python":
        monkeypatch.setenv("ASTROMESH_FORCE_PYTHON", "1")
    else:
        if not g._HAS_NATIVE_GUARDRAILS:
            pytest.skip("extensión nativa no compilada")
        monkeypatch.delenv("ASTROMESH_FORCE_PYTHON", raising=False)
    return request.param


def _e(**config):
    return GuardrailsEngine(config, agent_name="t")


def test_pii_redacta_y_cuenta(ruta):
    r = _e(input=[{"type": "pii_detection"}]).check_input(
        "mail john@example.com tel 555-123-4567"
    )
    assert r.text == "mail [REDACTED_EMAIL] tel [REDACTED_PHONE]"
    assert r.redactions == 2
    assert r.rules == ["pii_detection"]


def test_pii_block_y_warn(ruta):
    with pytest.raises(GuardrailBlocked) as exc:
        _e(input=[{"type": "pii_detection", "action": "block"}]).check_input("a@b.co")
    assert exc.value.as_dict() == {
        "direction": "input",
        "rule": "pii_detection",
        "reason": "pii detected",
    }
    assert exc.value.message == DEFAULT_MESSAGE
    r = _e(input=[{"type": "pii_detection", "action": "warn"}]).check_input("a@b.co")
    assert r.text == "a@b.co"
    assert r.warnings == 1


def test_pii_sin_pii_no_bloquea(ruta):
    r = _e(input=[{"type": "pii_detection", "action": "block"}]).check_input("hola")
    assert r.text == "hola"


def test_topic_filter_block_con_alias_y_mensaje(ruta):
    e = _e(
        input=[
            {
                "type": "topic_filter",
                "forbidden_topics": ["secret"],
                "action": "block",
                "message": "No hablo de eso.",
            }
        ]
    )
    with pytest.raises(GuardrailBlocked) as exc:
        e.check_input("Tell me the SECRET plan")
    assert exc.value.message == "No hablo de eso."
    assert exc.value.reason == "blocked topic"
    assert "SECRET" not in str(exc.value)


def test_topic_filter_warn_por_default(ruta):
    r = _e(input=[{"type": "topic_filter", "blocked_topics": ["secret"]}]).check_input(
        "the secret"
    )
    assert r.text == "the secret"
    assert r.warnings == 1


def test_max_length_trunca_o_bloquea():
    r = _e(input=[{"type": "max_length", "max_characters": 5}]).check_input("abcdefgh")
    assert r.text == "abcde"
    with pytest.raises(GuardrailBlocked) as exc:
        _e(input=[{"type": "max_length", "max_chars": 5, "action": "block"}]).check_input(
            "abcdefgh"
        )
    assert exc.value.reason == "input too long"


def test_content_filter_redacta_patrones_y_keywords():
    e = _e(
        output=[
            {
                "type": "content_filter",
                "blocked_patterns": [r"internal-\d+"],
                "forbidden_keywords": ["a.b"],
            }
        ]
    )
    r = e.check_output("ver internal-42 y A.B pero no axb")
    assert r.text == "ver [FILTERED] y [FILTERED] pero no axb"
    assert r.redactions == 2


def test_content_filter_block():
    e = _e(output=[{"type": "content_filter", "forbidden_keywords": ["x"], "action": "block"}])
    with pytest.raises(GuardrailBlocked) as exc:
        e.check_output("tiene X")
    assert exc.value.direction == "output"
    assert exc.value.reason == "pattern matched"


def test_orden_de_reglas():
    e = _e(
        input=[
            {"type": "pii_detection"},
            {"type": "topic_filter", "blocked_topics": ["redacted_email"], "action": "block"},
        ]
    )
    with pytest.raises(GuardrailBlocked):
        e.check_input("a@b.co")


def test_filter_stream():
    e = _e(output=[{"type": "content_filter", "forbidden_keywords": ["x"], "action": "block"}])
    assert e.filter_stream("hola") == "hola"
    assert e.filter_stream("x") is None
    assert _e().filter_stream("x") == "x"
    assert _e(output=[{"type": "pii_detection"}]).filter_stream("a@b.co") == "[REDACTED_EMAIL]"


def test_cost_limit_presupuesto():
    e = _e(output=[{"type": "cost_limit", "max_tokens_per_turn": 100}])
    assert e.cost_limit["max_tokens"] == 100
    assert not e.has_output
    assert e.tokens_of({"input_tokens": 50, "output_tokens": 7}) == 7
    assert e.tokens_of(None) == 0
    e.check_budget(99)
    with pytest.raises(GuardrailBlocked) as exc:
        e.check_budget(100)
    assert exc.value.as_dict() == {
        "direction": "run",
        "rule": "cost_limit",
        "reason": "token budget 100 exceeded (100)",
    }
    total = _e(input=[{"type": "cost_limit", "max_tokens_per_turn": 9, "count": "total"}])
    assert total.tokens_of({"input_tokens": 50, "output_tokens": 7}) == 57


def test_dos_cost_limit_gana_el_menor():
    e = _e(
        input=[{"type": "cost_limit", "max_tokens_per_turn": 50}],
        output=[{"type": "cost_limit", "max_tokens_per_turn": 20}],
    )
    assert e.cost_limit["max_tokens"] == 20


def test_sin_config():
    e = GuardrailsEngine()
    assert not e.has_input and not e.has_output and e.cost_limit is None
    assert e.check_input("hola").text == "hola"
    e.check_budget(10**9)
    assert e.tokens_of({"output_tokens": 5}) == 0


@pytest.mark.parametrize(
    ("config", "fragmento"),
    [
        ({"input": [{"type": "nope"}]}, "unknown type"),
        ({"input": ["pii_detection"]}, "not a mapping"),
        ({"output": [{"type": "topic_filter", "blocked_topics": ["a"]}]}, "does not apply"),
        ({"input": [{"type": "pii_detection", "action": "explode"}]}, "action 'explode'"),
        ({"output": [{"type": "content_filter", "blocked_patterns": ["("]}]}, "invalid regex"),
        ({"output": [{"type": "cost_limit"}]}, "positive integer"),
        ({"output": [{"type": "cost_limit", "max_tokens_per_turn": 5, "count": "x"}]}, "count"),
        ({"input": [{"type": "max_length", "max_chars": 0}]}, "positive integer"),
        ({"input": [{"type": "topic_filter"}]}, "no topics"),
        ({"input": "pii"}, "must be a list"),
    ],
)
def test_validacion_descarta_con_warning(config, fragmento, caplog):
    with caplog.at_level(logging.WARNING, logger="astromesh.core.guardrails"):
        e = GuardrailsEngine(config, agent_name="ag")
    assert not e.has_input and not e.has_output and e.cost_limit is None
    assert any(fragmento in r.getMessage() and "ag" in r.getMessage() for r in caplog.records)


def test_claves_de_clasificador_avisan_y_la_regla_sigue(caplog):
    with caplog.at_level(logging.WARNING, logger="astromesh.core.guardrails"):
        e = _e(
            output=[
                {
                    "type": "content_filter",
                    "blocked_categories": ["harassment"],
                    "forbidden_keywords": ["idiota"],
                }
            ]
        )
    assert e.has_output
    assert any("needs a classifier" in r.getMessage() for r in caplog.records)


def test_string_en_lugar_de_lista():
    e = _e(input=[{"type": "topic_filter", "blocked_topics": "secret", "action": "block"}])
    with pytest.raises(GuardrailBlocked):
        e.check_input("a secret")
    assert e.check_input("s e c r e t").text == "s e c r e t"
```

- [ ] **Step 2: Correr y ver que falla**

Run: `uv run pytest tests/test_guardrails.py -q`
Expected: FAIL — `ImportError: cannot import name 'DEFAULT_MESSAGE'`.

- [ ] **Step 3: Reescribir el motor**

`astromesh/core/guardrails.py`:

```python
"""Guardrails de entrada y salida de un agente (`spec.guardrails`).

`GuardrailsEngine(config, agent_name)` se construye una vez por agente y
normaliza las reglas: lo que no entiende lo descarta con un warning, nunca
impide que el agente cargue. `Agent.run` llama `check_input` antes de memoria y
modelo, `check_output` sobre la respuesta, `filter_stream` sobre cada evento
`token` y `check_budget` antes de cada llamada al modelo.

Bloquear es levantar `GuardrailBlocked`; `Agent.run` la convierte en una
respuesta de rechazo (`blocked: True`), no en un error.
"""

import logging
import os
import re
from dataclasses import dataclass, field

try:
    from astromesh._native import RustPiiRedactor, RustTopicFilter

    _NATIVE_PII = RustPiiRedactor()
    _HAS_NATIVE_GUARDRAILS = True
except ImportError:
    _NATIVE_PII = None
    _HAS_NATIVE_GUARDRAILS = False

logger = logging.getLogger(__name__)

DEFAULT_MESSAGE = "I can't help with that request."

# Mismos patrones y etiquetas que `native/src/guardrails.rs`. Formato de EE. UU.:
# un teléfono argentino no se detecta (límite documentado).
_PII_PATTERNS = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[REDACTED_CC]"),
)

# tipo -> (direcciones, acciones con la default primero, claves propias)
_RULES = {
    "pii_detection": (("input", "output"), ("redact", "block", "warn"), set()),
    "topic_filter": (("input",), ("warn", "block"), {"blocked_topics", "forbidden_topics"}),
    "max_length": (("input",), ("truncate", "block"), {"max_chars", "max_characters"}),
    "content_filter": (
        ("output",),
        ("redact", "block"),
        {"blocked_patterns", "forbidden_keywords"},
    ),
    # Es de la corrida, no de una dirección: se acepta en cualquiera de las dos.
    "cost_limit": (("input", "output"), ("block",), {"max_tokens_per_turn", "count"}),
}
_COMMON_KEYS = {"type", "action", "message"}
_NEEDS_CLASSIFIER = {"blocked_categories", "allowed_topics"}


class GuardrailBlocked(Exception):
    """Una regla bloqueó la corrida. `reason` nunca repite el contenido bloqueado."""

    def __init__(self, direction: str, rule: str, reason: str, message: str):
        super().__init__(f"{direction} guardrail {rule}: {reason}")
        self.direction = direction
        self.rule = rule
        self.reason = reason
        self.message = message

    def as_dict(self) -> dict:
        return {"direction": self.direction, "rule": self.rule, "reason": self.reason}


@dataclass
class GuardrailReport:
    text: str
    rules: list[str] = field(default_factory=list)
    redactions: int = 0
    warnings: int = 0


def _native() -> bool:
    return _HAS_NATIVE_GUARDRAILS and not os.environ.get("ASTROMESH_FORCE_PYTHON")


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value) if isinstance(value, list | tuple) else []


def _positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _redact_pii(text: str) -> tuple[str, int]:
    if _native():
        redacted = _NATIVE_PII.redact(text)
        return redacted, redacted.count("[REDACTED_") - text.count("[REDACTED_")
    total = 0
    for pattern, tag in _PII_PATTERNS:
        text, n = pattern.subn(tag, text)
        total += n
    return text, total


def _find_topic(text: str, topics: list[str]) -> str | None:
    if _native():
        return RustTopicFilter(topics).contains_blocked(text)
    folded = text.casefold()
    return next((t for t in topics if t.casefold() in folded), None)


class GuardrailsEngine:
    def __init__(self, config: dict | None = None, agent_name: str = "agent"):
        self._agent = agent_name
        self._input: list[dict] = []
        self._output: list[dict] = []
        budgets: list[dict] = []
        if not isinstance(config, dict):
            logger.warning("agent %s: guardrails must be a mapping, ignored", agent_name)
            config = {}
        for direction in ("input", "output"):
            rules = config.get(direction) or []
            if not isinstance(rules, list):
                logger.warning(
                    "agent %s: guardrails.%s must be a list, ignored", agent_name, direction
                )
                continue
            for index, raw in enumerate(rules):
                rule = self._normalize(direction, index, raw)
                if rule is None:
                    continue
                if rule["type"] == "cost_limit":
                    budgets.append(rule)
                else:
                    (self._input if direction == "input" else self._output).append(rule)
        self.cost_limit = min(budgets, key=lambda r: r["max_tokens"]) if budgets else None

    @property
    def has_input(self) -> bool:
        return bool(self._input)

    @property
    def has_output(self) -> bool:
        return bool(self._output)

    def _warn(self, direction: str, index: int, msg: str) -> None:
        logger.warning("agent %s: guardrails.%s[%d]: %s", self._agent, direction, index, msg)

    def _normalize(self, direction: str, index: int, raw) -> dict | None:
        if not isinstance(raw, dict):
            self._warn(direction, index, "not a mapping, discarded")
            return None
        kind = raw.get("type")
        if kind not in _RULES:
            self._warn(direction, index, f"unknown type {kind!r}, discarded")
            return None
        directions, actions, keys = _RULES[kind]
        if direction not in directions:
            self._warn(direction, index, f"{kind} does not apply to {direction}, discarded")
            return None
        for key in sorted(raw.keys() - _COMMON_KEYS - keys):
            if key in _NEEDS_CLASSIFIER:
                self._warn(
                    direction,
                    index,
                    f"{key} needs a classifier; not supported, use blocked_patterns "
                    "or the system prompt",
                )
            else:
                self._warn(direction, index, f"unknown key {key!r} ignored")
        action = raw.get("action", actions[0])
        if action not in actions:
            self._warn(
                direction,
                index,
                f"action {action!r} not valid for {kind} ({', '.join(actions)}), discarded",
            )
            return None
        message = raw.get("message")
        if not isinstance(message, str) or not message.strip():
            message = DEFAULT_MESSAGE
        rule = {"type": kind, "action": action, "message": message}

        if kind == "topic_filter":
            topics = _as_list(raw.get("blocked_topics")) + _as_list(raw.get("forbidden_topics"))
            rule["topics"] = [str(t) for t in topics if str(t).strip()]
            if not rule["topics"]:
                self._warn(direction, index, "topic_filter with no topics, discarded")
                return None
        elif kind == "max_length":
            limit = raw.get("max_chars", raw.get("max_characters", 10000))
            if not _positive_int(limit):
                self._warn(direction, index, "max_chars must be a positive integer, discarded")
                return None
            rule["max_chars"] = limit
        elif kind == "content_filter":
            patterns = []
            for p in _as_list(raw.get("blocked_patterns")):
                try:
                    patterns.append(re.compile(str(p), re.IGNORECASE))
                except re.error as exc:
                    self._warn(direction, index, f"invalid regex {p!r} discarded: {exc}")
            for k in _as_list(raw.get("forbidden_keywords")):
                if str(k).strip():
                    patterns.append(re.compile(re.escape(str(k)), re.IGNORECASE))
            if not patterns:
                self._warn(direction, index, "content_filter with no valid patterns, discarded")
                return None
            rule["patterns"] = patterns
        elif kind == "cost_limit":
            limit = raw.get("max_tokens_per_turn")
            if not _positive_int(limit):
                self._warn(
                    direction,
                    index,
                    "cost_limit needs max_tokens_per_turn as a positive integer, discarded",
                )
                return None
            count = raw.get("count", "output")
            if count not in ("output", "total"):
                self._warn(direction, index, f"count {count!r} not valid (output, total), discarded")
                return None
            rule["max_tokens"] = limit
            rule["count"] = count
        return rule

    def check_input(self, text: str) -> GuardrailReport:
        return self._apply("input", self._input, text)

    def check_output(self, text: str) -> GuardrailReport:
        return self._apply("output", self._output, text)

    def filter_stream(self, text: str) -> str | None:
        """El `content` de un evento `token` filtrado; None si una regla lo bloquea."""
        if not self._output:
            return text
        try:
            return self.check_output(text).text
        except GuardrailBlocked:
            return None

    def check_budget(self, counted: int) -> None:
        rule = self.cost_limit
        if rule is not None and counted >= rule["max_tokens"]:
            raise GuardrailBlocked(
                "run",
                "cost_limit",
                f"token budget {rule['max_tokens']} exceeded ({counted})",
                rule["message"],
            )

    def tokens_of(self, usage: dict | None) -> int:
        if self.cost_limit is None or not usage:
            return 0
        counted = usage.get("output_tokens", 0) or 0
        if self.cost_limit["count"] == "total":
            counted += usage.get("input_tokens", 0) or 0
        return int(counted)

    def _apply(self, direction: str, rules: list[dict], text: str) -> GuardrailReport:
        report = GuardrailReport(text=text)
        for rule in rules:
            kind, action = rule["type"], rule["action"]
            report.rules.append(kind)
            if kind == "pii_detection":
                redacted, found = _redact_pii(report.text)
                if found:
                    if action == "block":
                        raise GuardrailBlocked(direction, kind, "pii detected", rule["message"])
                    if action == "warn":
                        report.warnings += 1
                    else:
                        report.text = redacted
                        report.redactions += found
            elif kind == "topic_filter":
                if _find_topic(report.text, rule["topics"]) is not None:
                    if action == "block":
                        raise GuardrailBlocked(direction, kind, "blocked topic", rule["message"])
                    report.warnings += 1
            elif kind == "max_length":
                if len(report.text) > rule["max_chars"]:
                    if action == "block":
                        raise GuardrailBlocked(direction, kind, "input too long", rule["message"])
                    report.text = report.text[: rule["max_chars"]]
            elif kind == "content_filter":
                if action == "block":
                    if any(p.search(report.text) for p in rule["patterns"]):
                        raise GuardrailBlocked(
                            direction, kind, "pattern matched", rule["message"]
                        )
                else:
                    for p in rule["patterns"]:
                        report.text, n = p.subn("[FILTERED]", report.text)
                        report.redactions += n
        return report
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `uv run pytest tests/test_guardrails.py tests/test_native_guardrails.py -q`
Expected: PASS (los parametrizados `native` se saltean si la extensión no está compilada). Si `test_native_guardrails.py` importaba algo eliminado (`_redact_pii`, `apply_input`), adaptarlo a `check_input` sin cambiar lo que verifica.

- [ ] **Step 5: CHANGELOG y commit**

En `CHANGELOG.md`, bajo `## [Unreleased]` → `### Changed`:

```markdown
- **Guardrails reescritos** (`core/guardrails.py`): las reglas se normalizan y validan al
  cargar el agente (lo inválido se descarta con warning, nunca impide cargar); se aceptan
  los nombres de los docs como alias (`forbidden_topics`, `max_characters`,
  `forbidden_keywords`); bloquear levanta `GuardrailBlocked` en lugar de `ValueError`;
  `pii_detection` admite `block` y `warn`; `max_length` admite `block`; `content_filter`
  admite `block`; `cost_limit` deja de truncar el texto y pasa a ser un presupuesto de
  tokens de la corrida. `blocked_categories` y `allowed_topics` no se soportan (requieren
  un clasificador) y avisan al cargar.
```

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add astromesh/core/guardrails.py tests/test_guardrails.py tests/test_native_guardrails.py CHANGELOG.md
git commit -m "refactor(guardrails): motor que valida al cargar y bloquea con GuardrailBlocked

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Guardrails de entrada y salida en `Agent.run`

**Files:**
- Modify: `astromesh/runtime/engine.py` (`_build_agent` ~línea 1263, `Agent.__init__` ~1540-1590, `Agent.run` ~1613-2190)
- Create: `tests/test_guardrails_run.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `GuardrailsEngine`, `GuardrailBlocked` de Task 1.
- Produces:
  - `Agent._guardrails: GuardrailsEngine` (siempre una instancia; `Agent.__init__` acepta dict o motor).
  - Resultado de `Agent.run` siempre con `blocked: bool` y `guardrail: dict | None`.
  - `Agent._aplicar_guardrails(direction, text, tracing, root_span) -> str`
  - `Agent._persistir_turno(session_id, query, answer, tracing, root_span) -> None`
  - `Agent._guardar_query(query, tracing, root_span) -> str | list[dict]`
  - Variables locales de `run` que Task 3 usa: `contados: int` (inicializada en 0 al tope del `try`), `corte: GuardrailBlocked | None` (inicializada en None al tope del `try`).
  - Helper de módulo `_texto_de(query) -> str`.

- [ ] **Step 1: Escribir los tests**

`tests/test_guardrails_run.py`:

```python
"""Los guardrails aplicados en una corrida real de `Agent.run` (proveedor falso)."""

import json
from datetime import UTC, datetime

import pytest
import yaml

from astromesh.core import tokens
from astromesh.core.memory import ConversationBackend
from astromesh.providers.base import CompletionResponse
from astromesh.runtime.engine import AgentRuntime

EMAIL = "john@example.com"


@pytest.fixture(autouse=True)
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


class Fake(ConversationBackend):
    def __init__(self):
        self.turns = []

    async def save_turn(self, session_id, turn):
        self.turns.append(turn)

    async def get_history(self, session_id, limit=50):
        return list(self.turns[-limit:])

    async def clear(self, session_id):
        self.turns = []

    async def get_summary(self, session_id):
        return None

    async def save_summary(self, session_id, summary):
        pass


def _resp(content="ok", output_tokens=0):
    return CompletionResponse(
        content=content,
        model="m",
        provider="p",
        usage={"input_tokens": 3, "output_tokens": output_tokens},
        latency_ms=1.0,
        cost=0.0,
    )


def _manifest(guardrails=None, **extra):
    spec = {
        "identity": {"description": "demo"},
        "model": {"primary": {"provider": "ollama", "model": "llama3"}},
        "prompts": {"system": "sos un agente"},
        "memory": {
            "conversational": {
                "backend": "redis",
                "connection": {"url": "redis://localhost:1"},
                "strategy": "sliding_window",
            }
        },
        **extra,
    }
    if guardrails is not None:
        spec["guardrails"] = guardrails
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "g-agent", "version": "0.1.0"},
        "spec": spec,
    }


async def _agente(tmp_path, manifest, respuestas=("ok",)):
    """Agente real con memoria falsa; devuelve (agente, llamadas al modelo)."""
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "g-agent.agent.yaml").write_text(yaml.safe_dump(manifest))
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    assert "g-agent" in runtime._agents, runtime._agent_errors
    agente = runtime._agents["g-agent"]
    agente._memory._conversation = Fake()
    llamadas = []
    cola = list(respuestas)

    async def route(messages, requirements=None, **kwargs):
        llamadas.append(messages)
        r = cola.pop(0) if len(cola) > 1 else cola[0]
        return r if isinstance(r, CompletionResponse) else _resp(r)

    agente._routers["default"].route = route
    return agente, llamadas


PII_IN = {"input": [{"type": "pii_detection"}]}


async def test_entrada_redactada_llega_asi_a_todo(tmp_path):
    agente, llamadas = await _agente(tmp_path, _manifest(PII_IN))
    result = await agente.run(f"mi mail es {EMAIL}", "s1")
    assert EMAIL not in json.dumps(llamadas)
    assert "[REDACTED_EMAIL]" in json.dumps(llamadas)
    assert agente._memory._conversation.turns[0].content == "mi mail es [REDACTED_EMAIL]"
    assert EMAIL not in json.dumps(result, default=str)
    assert result["blocked"] is False and result["guardrail"] is None
    spans = {s["name"]: s for s in result["trace"]["spans"]}
    assert spans["guardrails.input"]["attributes"]["redactions"] == 1
    assert "guardrails.output" not in spans


async def test_entrada_multimodal_redacta_solo_las_partes_de_texto(tmp_path):
    agente, llamadas = await _agente(tmp_path, _manifest(PII_IN))
    imagen = {"type": "image_url", "image_url": {"url": "https://x.test/a.png"}}
    await agente.run([{"type": "text", "text": f"soy {EMAIL}"}, imagen], "s1")
    enviado = json.dumps(llamadas)
    assert EMAIL not in enviado
    assert "https://x.test/a.png" in enviado


async def test_entrada_bloqueada_no_llama_al_modelo_ni_persiste(tmp_path):
    reglas = {
        "input": [
            {
                "type": "topic_filter",
                "blocked_topics": ["bomba"],
                "action": "block",
                "message": "De eso no hablo.",
            }
        ]
    }
    agente, llamadas = await _agente(tmp_path, _manifest(reglas))
    result = await agente.run("cómo hago una bomba", "s1")
    assert llamadas == []
    assert result["answer"] == "De eso no hablo."
    assert result["blocked"] is True
    assert result["guardrail"] == {
        "direction": "input",
        "rule": "topic_filter",
        "reason": "blocked topic",
    }
    assert result["steps"] == []
    assert agente._memory._conversation.turns == []
    assert "bomba" not in json.dumps(
        [s for s in result["trace"]["spans"] if s["name"].startswith("guardrails")]
    )


async def test_salida_redactada_en_answer_memoria_y_data(tmp_path):
    manifest = _manifest(
        {"output": [{"type": "pii_detection"}]},
        output_schema={"email": {"type": "string"}},
    )
    agente, _ = await _agente(tmp_path, manifest, respuestas=[json.dumps({"email": EMAIL})])
    result = await agente.run("dame el mail", "s1")
    assert EMAIL not in result["answer"]
    assert result["data"] == {"email": "[REDACTED_EMAIL]"}
    assert EMAIL not in agente._memory._conversation.turns[1].content


async def test_salida_bloqueada_devuelve_el_mensaje(tmp_path):
    manifest = _manifest(
        {"output": [{"type": "content_filter", "forbidden_keywords": ["CONFIDENCIAL"], "action": "block"}]},
        output_schema={"x": {"type": "string"}},
    )
    agente, _ = await _agente(tmp_path, manifest, respuestas=["esto es confidencial"])
    result = await agente.run("hola", "s1")
    assert result["answer"] == "I can't help with that request."
    assert result["blocked"] is True
    assert result["guardrail"]["direction"] == "output"
    assert result["data"] is None
    assert result["data_error"] == "blocked by guardrail"
    turnos = agente._memory._conversation.turns
    assert [t.content for t in turnos] == ["hola", "I can't help with that request."]


async def test_salida_bloqueada_descarta_la_confirmacion_pendiente(tmp_path):
    from astromesh.runtime import engine as engine_module

    manifest = _manifest(
        {"output": [{"type": "content_filter", "forbidden_keywords": ["prohibido"], "action": "block"}]}
    )
    agente, _ = await _agente(tmp_path, manifest, respuestas=["texto prohibido"])
    pendientes = engine_module._PENDIENTES
    original = agente._pattern.execute

    async def execute(*args, **kwargs):
        # Simula una tool `needs_confirmation` que registró su propuesta en esta corrida.
        pendientes.registrar("s1", "borrar_todo", "huella", {"id": 1})
        return await original(*args, **kwargs)

    agente._pattern.execute = execute
    result = await agente.run("hola", "s1")
    assert result["blocked"] is True
    assert pendientes.pendiente("s1") is None


async def test_corrida_reentrante_tambien_aplica_sus_reglas(tmp_path):
    agente, llamadas = await _agente(tmp_path, _manifest(PII_IN))
    await agente.run(f"consultá por {EMAIL}", "s1", desde_humano=False)
    assert EMAIL not in json.dumps(llamadas)


async def test_sin_guardrails_no_cambia_nada(tmp_path):
    agente, llamadas = await _agente(tmp_path, _manifest(), respuestas=[f"escribí a {EMAIL}"])
    result = await agente.run(f"soy {EMAIL}", "s1")
    assert EMAIL in json.dumps(llamadas)
    assert result["answer"] == f"escribí a {EMAIL}"
    assert result["blocked"] is False and result["guardrail"] is None
    assert not [s for s in result["trace"]["spans"] if s["name"].startswith("guardrails")]
```

Antes de correrlo, verificar dos supuestos y ajustar **el test** (no el código) si difieren:
- forma de la traza: `result["trace"]["spans"]` lista de dicts con `name` y `attributes` (leer `TracingContext.to_dict` en `astromesh/observability/tracing.py`);
- `_PENDIENTES.registrar(session_id, tool, huella, args)` y `pendiente(session_id)` (leer `astromesh/runtime/confirmacion.py`).

- [ ] **Step 2: Correr y ver que falla**

Run: `uv run pytest tests/test_guardrails_run.py -q`
Expected: FAIL — `KeyError: 'blocked'` y el email presente en las llamadas.

- [ ] **Step 3: Construir el motor por agente**

En `runtime/engine.py`, import junto a los demás de `astromesh.core`:

```python
from astromesh.core.guardrails import GuardrailBlocked, GuardrailsEngine
```

En `_build_agent`, reemplazar `guardrails=spec.get("guardrails", {}),` por:

```python
            guardrails=GuardrailsEngine(spec.get("guardrails") or {}, agent_name=metadata["name"]),
```

En `Agent.__init__`, reemplazar `self._guardrails = guardrails` por:

```python
        # Los tests que arman `Agent` a mano pasan el dict del manifiesto.
        self._guardrails = (
            guardrails
            if isinstance(guardrails, GuardrailsEngine)
            else GuardrailsEngine(guardrails or {}, agent_name=name)
        )
```

- [ ] **Step 4: Helpers de módulo y de `Agent`**

Función de módulo (junto a `_emit`):

```python
def _texto_de(query) -> str:
    """El texto de una query: tal cual si es str, las partes `text` unidas si es multimodal."""
    if isinstance(query, str):
        return query
    return " ".join(p.get("text", "") for p in query if p.get("type") == "text")
```

y en `run` reemplazar la expresión de `query_text = (...)` por `query_text = _texto_de(query)`.

Métodos de `Agent` (después de `_bundle_index`):

```python
    def _aplicar_guardrails(self, direction, text, tracing, root_span):
        """Corre las reglas de una dirección dentro de su span; levanta GuardrailBlocked.

        El span lleva qué reglas corrieron y cuántas redacciones o avisos hubo,
        nunca el texto.
        """
        span = tracing.start_span(f"guardrails.{direction}", parent_span_id=root_span.span_id)
        check = (
            self._guardrails.check_input
            if direction == "input"
            else self._guardrails.check_output
        )
        try:
            report = check(text)
        except GuardrailBlocked as bloqueo:
            span.set_attribute("blocked_by", bloqueo.rule)
            span.set_attribute("reason", bloqueo.reason)
            tracing.finish_span(span)
            raise
        span.set_attribute("rules", report.rules)
        span.set_attribute("redactions", report.redactions)
        span.set_attribute("warnings", report.warnings)
        tracing.finish_span(span)
        return report.text

    def _guardar_query(self, query, tracing, root_span):
        """La query con las reglas de entrada aplicadas; multimodal, parte `text` por parte."""
        if isinstance(query, str):
            return self._aplicar_guardrails("input", query, tracing, root_span)
        return [
            {**p, "text": self._aplicar_guardrails("input", p.get("text", ""), tracing, root_span)}
            if p.get("type") == "text"
            else p
            for p in query
        ]
```

Mover el bloque de persistencia actual de `run` (desde `# Extract text for storage; keep full multimodal content in metadata.` hasta `tracing.finish_span(persist_span)` inclusive) a un método, sin cambiar su contenido salvo que el contenido del assistant es el parámetro `answer`:

```python
    async def _persistir_turno(self, session_id, query, answer, tracing, root_span):
        from datetime import UTC, datetime

        from astromesh.core.memory import ConversationTurn

        # <bloque movido tal cual, con `content=answer` en el turno assistant>
```

y en `run`, en su lugar:

```python
            await self._persistir_turno(
                session_id, query, result.get("answer", ""), tracing, root_span
            )
```

- [ ] **Step 5: Entrada, salida y rechazo en `run`**

1. Al tope del `try` de `run` (antes de `query_text = _texto_de(query)`):

```python
            # Estado que el `except GuardrailBlocked` de abajo necesita.
            pasos: list = []
            propuestas: list[dict] | str = []
            contados = 0  # tokens contados para `cost_limit` (Task 3)
            corte: GuardrailBlocked | None = None  # el corte de `cost_limit` (Task 3)
```

2. Después del bloque `if desde_humano: _PENDIENTES.habilitar(session_id, query_text)` y **antes** de `root_span.set_attribute("query", ...)`:

```python
            # Guardrails de entrada: antes de memoria, RAG, prefetch y modelo, así
            # todo lo de abajo (y el atributo `query` del span) ve el texto ya
            # filtrado. `habilitar`, arriba, lee el crudo: es un chequeo de
            # consentimiento que no viaja al modelo.
            if self._guardrails.has_input:
                query = self._guardar_query(query, tracing, root_span)
                query_text = _texto_de(query)
```

3. Inmediatamente después de `tracing.finish_span(orch_span)`:

```python
            pasos = result.get("steps", [])
            # Guardrails de salida: antes del aviso de confirmación (texto del
            # runtime), de persistir y de `build_data`, así `data` tampoco
            # filtra lo que `answer` tapa.
            if self._guardrails.has_output:
                respuesta = result.get("answer")
                if not isinstance(respuesta, str):
                    respuesta = "" if respuesta is None else str(respuesta)
                result["answer"] = self._aplicar_guardrails(
                    "output", respuesta, tracing, root_span
                )
```

4. Justo antes de `result["trace"] = tracing.to_dict()` en el camino normal:

```python
            result["blocked"] = False
            result["guardrail"] = None
```

5. Un nuevo `except` **antes** de `except Exception as e:`:

```python
        except GuardrailBlocked as bloqueo:
            # Un bloqueo es una respuesta, no un error: la corrida termina bien.
            if desde_humano:
                pendiente = _PENDIENTES.pendiente(session_id)
                if pendiente is not None and not pendiente["ok"]:
                    # La respuesta que explicaba la propuesta fue reemplazada
                    # por el rechazo: un "sí" en el próximo turno no puede
                    # autorizar algo que la persona no vio.
                    _PENDIENTES.cerrar(session_id)
            if bloqueo.direction != "input":
                # El texto bloqueado de entrada no entra al historial; el resto
                # guarda la pregunta (ya filtrada) y el rechazo.
                await self._persistir_turno(
                    session_id, query, bloqueo.message, tracing, root_span
                )
            root_span.set_attribute("guardrail.blocked", True)
            root_span.set_attribute("guardrail.rule", bloqueo.rule)
            if self._guardrails.cost_limit is not None:
                root_span.set_attribute("guardrail.tokens_counted", contados)
            tracing.finish_span(root_span)
            rechazo = {
                "answer": bloqueo.message,
                "steps": pasos if bloqueo.direction == "output" else [],
                "blocked": True,
                "guardrail": bloqueo.as_dict(),
                "propuestas": (
                    propuestas
                    if isinstance(propuestas, list) and propuestas_padre is None
                    else []
                ),
            }
            if self._output_schema:
                rechazo["data"] = None
                rechazo["data_error"] = "blocked by guardrail"
            rechazo["trace"] = tracing.to_dict()
            return rechazo
```

Nota: la asignación existente `propuestas: list[dict] | str` más abajo en `run` queda como asignación simple (`propuestas = ...`, sin anotación) para no anotar dos veces.

- [ ] **Step 6: Correr los tests nuevos y toda la suite**

Run: `uv run pytest tests/test_guardrails_run.py -q && uv run pytest -q -x`
Expected: PASS. Si algún test existente arma `Agent(...)` con `guardrails=` dict, sigue pasando por la conversión del Step 3.

- [ ] **Step 7: CHANGELOG y commit**

`## [Unreleased]` → `### Fixed`:

```markdown
- **`spec.guardrails` se aplica.** Hasta ahora se parseaba y nada lo leía: un agente con
  `pii_detection: redact` mandaba los emails al modelo. Las reglas de entrada corren antes
  de memoria, RAG y modelo (en una query multimodal, sobre cada parte de texto); las de
  salida, sobre la respuesta antes de persistirla y de armar `data`. Un bloqueo devuelve
  una respuesta de rechazo (`answer` = `message` de la regla, `blocked: true`,
  `guardrail: {direction, rule, reason}`), no un error; un bloqueo de entrada no persiste
  el turno, y uno con una confirmación pendiente la descarta. Toda corrida devuelve
  `blocked` y `guardrail`. Spans `guardrails.input`/`guardrails.output` sin contenido.
```

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add astromesh/runtime/engine.py tests/test_guardrails_run.py CHANGELOG.md
git commit -m "fix(guardrails): Agent.run aplica las reglas de entrada y salida

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Stream filtrado y `cost_limit`

**Files:**
- Modify: `astromesh/runtime/engine.py` (`model_fn` dentro de `run`, llamada a `self._pattern.execute`, cierre del camino normal)
- Modify: `tests/test_guardrails_run.py` (agregar tests)
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `contados`, `corte` (locales de `run`, Task 2); `GuardrailsEngine.filter_stream`, `check_budget`, `tokens_of` (Task 1).
- Produces: nada nuevo hacia afuera.

- [ ] **Step 1: Agregar los tests**

Al final de `tests/test_guardrails_run.py`:

```python
async def test_stream_filtra_cada_evento_token(tmp_path):
    agente, _ = await _agente(
        tmp_path, _manifest({"output": [{"type": "pii_detection"}]}), respuestas=[f"es {EMAIL}"]
    )
    eventos = []
    await agente.run("hola", "s1", on_event=eventos.append)
    tokens_emitidos = [e["content"] for e in eventos if e["type"] == "token"]
    assert tokens_emitidos == ["es [REDACTED_EMAIL]"]


async def test_stream_no_emite_lo_que_una_regla_bloquea(tmp_path):
    reglas = {"output": [{"type": "content_filter", "forbidden_keywords": ["secreto"], "action": "block"}]}
    agente, _ = await _agente(tmp_path, _manifest(reglas), respuestas=["el secreto es 42"])
    eventos = []
    result = await agente.run("hola", "s1", on_event=eventos.append)
    assert [e for e in eventos if e["type"] == "token"] == []
    assert result["answer"] == "I can't help with that request."


async def test_cost_limit_corta_antes_de_la_llamada_siguiente(tmp_path):
    reglas = {"output": [{"type": "cost_limit", "max_tokens_per_turn": 15}]}
    manifest = _manifest(reglas, orchestration={"pattern": "plan_and_execute"})
    plan = _resp('["paso a", "paso b", "paso c"]', output_tokens=10)
    agente, llamadas = await _agente(tmp_path, manifest, respuestas=[plan])
    result = await agente.run("hacé tres cosas", "s1")
    # 1ª: 0 < 15 → corre (10). 2ª: 10 < 15 → corre (20). 3ª: 20 >= 15 → corta.
    assert len(llamadas) == 2
    assert result["blocked"] is True
    assert result["guardrail"] == {
        "direction": "run",
        "rule": "cost_limit",
        "reason": "token budget 15 exceeded (20)",
    }
    raiz = next(s for s in result["trace"]["spans"] if s["name"] == "agent.run")
    assert raiz["attributes"]["guardrail.tokens_counted"] == 20


async def test_cost_limit_count_total(tmp_path):
    reglas = {"input": [{"type": "cost_limit", "max_tokens_per_turn": 5, "count": "total"}]}
    manifest = _manifest(reglas, orchestration={"pattern": "plan_and_execute"})
    plan = _resp('["a", "b"]', output_tokens=0)  # usage.input_tokens = 3
    agente, llamadas = await _agente(tmp_path, manifest, respuestas=[plan])
    result = await agente.run("x", "s1")
    assert len(llamadas) == 2  # 0 → 3 → 6 >= 5
    assert result["guardrail"]["rule"] == "cost_limit"


@pytest.mark.parametrize("modo", ["traga", "envuelve"])
async def test_cost_limit_sobrevive_a_un_patron_que_lo_esconde(tmp_path, modo):
    reglas = {"output": [{"type": "cost_limit", "max_tokens_per_turn": 1}]}
    agente, llamadas = await _agente(
        tmp_path, _manifest(reglas), respuestas=[_resp("x", output_tokens=5)]
    )

    async def execute(query, context, model_fn, tool_fn, tools, max_iterations=10):
        await model_fn([{"role": "user", "content": "1"}], [])
        try:
            await model_fn([{"role": "user", "content": "2"}], [])
        except Exception as exc:  # como Glyph: convierte el error y sigue
            if modo == "envuelve":
                raise RuntimeError("falló la capacidad") from exc
        return {"answer": "terminé igual", "steps": []}

    agente._pattern.execute = execute
    result = await agente.run("x", "s1")
    assert len(llamadas) == 1
    assert result["blocked"] is True
    assert result["guardrail"]["rule"] == "cost_limit"
```

Si `plan_and_execute` hace menos de 3 llamadas con un plan de 3 pasos, ajustar el número de pasos del test hasta que el plan necesite al menos 3 llamadas (leer `PlanAndExecutePattern.execute` en `astromesh/orchestration/patterns.py`); lo que el test fija es "corre 2, corta en la 3ª".

- [ ] **Step 2: Correr y ver que falla**

Run: `uv run pytest tests/test_guardrails_run.py -q -k "stream or cost_limit"`
Expected: FAIL — el email aparece en el evento `token` y `cost_limit` no corta.

- [ ] **Step 3: `model_fn`**

Dentro de `async def model_fn(messages, tools, role=None):`, como primeras líneas:

```python
                nonlocal contados, corte
                # `cost_limit`: se chequea antes de gastar; la llamada que cruza
                # el límite se completa. Una vez cortado, toda llamada siguiente
                # vuelve a levantar aunque el patrón se haya tragado la primera.
                try:
                    self._guardrails.check_budget(contados)
                except GuardrailBlocked as bloqueo:
                    corte = corte or bloqueo
                    raise corte from None
```

Inmediatamente después de `response = await router.route(full_messages, tools=tools, **route_kwargs)`:

```python
                    contados += self._guardrails.tokens_of(getattr(response, "usage", None))
```

Reemplazar:

```python
                    if response.content:
                        _emit(on_event, {"type": "token", "content": response.content})
```

por:

```python
                    if response.content:
                        # Las reglas de salida también valen para el stream: el
                        # patrón recibe la respuesta cruda, el evento la filtrada.
                        contenido = self._guardrails.filter_stream(response.content)
                        if contenido is not None:
                            _emit(on_event, {"type": "token", "content": contenido})
```

- [ ] **Step 4: Un corte escondido por el patrón igual corta**

Envolver la llamada existente `result = await self._pattern.execute(...)` (sin tocar sus argumentos):

```python
            try:
                result = await self._pattern.execute(
                    # ...argumentos actuales, sin cambios...
                )
            except GuardrailBlocked:
                raise
            except Exception:
                # Glyph convierte el error de una capacidad en el suyo y
                # reintenta; si lo que falló fue el presupuesto, es un rechazo.
                if corte is not None:
                    raise corte from None
                raise
            if corte is not None:
                raise corte
```

Y justo antes de `tracing.finish_span(root_span)` del camino normal:

```python
            if self._guardrails.cost_limit is not None:
                root_span.set_attribute("guardrail.tokens_counted", contados)
```

- [ ] **Step 5: Correr los tests y la suite**

Run: `uv run pytest tests/test_guardrails_run.py -q && uv run pytest -q -x`
Expected: PASS.

- [ ] **Step 6: CHANGELOG y commit**

`## [Unreleased]` → `### Added (Backend)`:

```markdown
- **`cost_limit` es un presupuesto real de tokens de la corrida**: suma el `usage` del
  proveedor de cada llamada al modelo (`count: output`, default, o `total`) y, si antes
  de una nueva llamada ya se pasó `max_tokens_per_turn`, la corrida termina con el
  rechazo (`guardrail.direction: run`). Funciona aunque el patrón se trague el error
  (Glyph). **El stream respeta las reglas de salida**: cada evento `token` se filtra, y
  no se emite si una regla lo bloquea.
```

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add astromesh/runtime/engine.py tests/test_guardrails_run.py CHANGELOG.md
git commit -m "feat(guardrails): cost_limit como presupuesto de tokens y stream filtrado

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `blocked` y `guardrail` en la API y el WebSocket

**Files:**
- Modify: `astromesh/api/routes/agents.py` (`AgentRunResponse` ~línea 80, construcción ~318)
- Modify: `astromesh/api/ws.py` (mensaje `done`)
- Test: `tests/test_ws_agent.py`, y el test de la ruta run (buscar con `grep -ln "AgentRunResponse\|/agents/.*/run" tests/`; agregar ahí)
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: claves `blocked`, `guardrail` del resultado de `run` (Task 2).
- Produces: `AgentRunResponse.blocked: bool = False`, `AgentRunResponse.guardrail: dict | None = None`; `done` del WS con `blocked` y `guardrail`.

- [ ] **Step 1: Tests**

En `tests/test_ws_agent.py`:

```python
def test_done_lleva_blocked_y_guardrail(client, mock_runtime):
    mock_runtime.run.return_value = {
        "answer": "No.",
        "steps": [],
        "trace": {},
        "blocked": True,
        "guardrail": {"direction": "input", "rule": "topic_filter", "reason": "blocked topic"},
    }
    with client.websocket_connect("/v1/ws/agent/demo") as ws:
        ws.send_json({"query": "x"})
        done = _drain(ws)[-1]
    assert done["blocked"] is True
    assert done["guardrail"]["rule"] == "topic_filter"


def test_done_sin_bloqueo(client, mock_runtime):
    with client.websocket_connect("/v1/ws/agent/demo") as ws:
        ws.send_json({"query": "x"})
        done = _drain(ws)[-1]
    assert done["blocked"] is False
    assert done["guardrail"] is None
```

En el archivo de tests de la ruta `POST /v1/agents/{name}/run` que ya mockea el runtime, un test equivalente siguiendo su fixture: con `run` devolviendo `blocked: True` y `guardrail` → la respuesta JSON tiene ambos; sin ellos → `blocked: false`, `guardrail: null`.

- [ ] **Step 2: Correr y ver que falla**

Run: `uv run pytest tests/test_ws_agent.py -q -k "blocked or bloqueo"`
Expected: FAIL — `KeyError: 'blocked'`.

- [ ] **Step 3: Implementar**

`AgentRunResponse`, después de `propuestas`:

```python
    #: True si un guardrail bloqueó la corrida; `answer` es entonces el mensaje
    #: de rechazo y `guardrail` dice qué regla y por qué (sin el contenido).
    blocked: bool = False
    guardrail: dict | None = None
```

En la construcción de la respuesta, después de `propuestas=...`:

```python
            blocked=bool(result.get("blocked")),
            guardrail=result.get("guardrail"),
```

En `ws.py`, en el dict del `done`, después de `"propuestas"`:

```python
            "blocked": bool(result.get("blocked")),
            "guardrail": result.get("guardrail"),
```

- [ ] **Step 4: Correr**

Run: `uv run pytest tests/test_ws_agent.py -q && uv run pytest -q -x`
Expected: PASS.

- [ ] **Step 5: CHANGELOG y commit**

`### Added (Backend)`:

```markdown
- `POST /v1/agents/{name}/run` y el `done` del WebSocket devuelven `blocked` y
  `guardrail`.
```

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add astromesh/api/routes/agents.py astromesh/api/ws.py tests/ CHANGELOG.md
git commit -m "feat(api): blocked y guardrail en la respuesta de run y en el done del WebSocket

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Manifiestos del repo y schema de VS Code

**Files:**
- Modify: `config/agents/{autolink-parts,sales-qualifier,support-agent}.agent.yaml`
- Modify: `config/templates/{brand-chef,debt-collector,nutritionist,onboarding-buddy,parts-advisor,payment-reminder,product-advisor,returns-claims,sales-qualifier,service-scheduler,support-agent,tutor-assistant}.template.yaml`
- Modify: `vscode-extension/schemas/agent.schema.json` (`$defs.guardrailRule`)
- Create: `tests/test_manifest_guardrails.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `GuardrailsEngine` (Task 1).

Decisiones ya tomadas (aplicar tal cual; editar sólo el bloque `guardrails`, preservando comentarios e indentación del archivo — editar a mano, no reescribir el YAML con un dump):

| Archivo | Cambio |
|---|---|
| todos los que tienen `cost_limit` con 500–1500 (autolink-parts, sales-qualifier ×2, support-agent ×2, brand-chef, debt-collector, nutritionist, onboarding-buddy, parts-advisor, product-advisor, service-scheduler, tutor-assistant) | `max_tokens_per_turn: 4000` |
| `campaign-bot.template.yaml` | sin cambios (ReAct sin tools: una sola llamada; el presupuesto nunca corta) |
| `brand-chef`, `nutritionist` | quitar la regla `topic_filter` con `allowed_topics` (el alcance ya está en su system prompt) |
| `debt-collector`, `tutor-assistant`, `payment-reminder` | quitar la regla `content_filter` con `blocked_categories` |
| `debt-collector`, `payment-reminder`, `returns-claims` | quitar `pii_detection` de **entrada** (sus tools reciben `customer_id` / `order_number`, que un ID numérico de 10 o 16 dígitos haría redactar como teléfono o tarjeta); asegurar `pii_detection` de **salida** (`returns-claims` ya la tiene; agregarla a `debt-collector` y `payment-reminder`) |
| resto de `pii_detection` de entrada | sin cambios (ninguna tool de esos agentes recibe email ni teléfono) |

Si una sección `output:` queda vacía, quitar la clave.

- [ ] **Step 1: Test que fija que todo manifiesto carga sin warnings de guardrails**

`tests/test_manifest_guardrails.py`:

```python
"""Ningún manifiesto del repo declara guardrails que el motor descarte o no entienda."""

import logging
from pathlib import Path

import pytest
import yaml

from astromesh.core.guardrails import GuardrailsEngine

RAIZ = Path(__file__).resolve().parents[1] / "config"
ARCHIVOS = sorted(
    [*RAIZ.glob("agents/*.agent.yaml"), *RAIZ.glob("templates/*.template.yaml")]
)


def _guardrails(nodo):
    if isinstance(nodo, dict):
        if "guardrails" in nodo:
            return nodo["guardrails"]
        for v in nodo.values():
            if (r := _guardrails(v)) is not None:
                return r
    if isinstance(nodo, list):
        for v in nodo:
            if (r := _guardrails(v)) is not None:
                return r
    return None


@pytest.mark.parametrize("archivo", ARCHIVOS, ids=lambda p: p.name)
def test_guardrails_del_manifiesto_sin_warnings(archivo, caplog):
    config = _guardrails(yaml.safe_load(archivo.read_text()))
    if config is None:
        pytest.skip("sin guardrails")
    with caplog.at_level(logging.WARNING, logger="astromesh.core.guardrails"):
        GuardrailsEngine(config, agent_name=archivo.name)
    assert not caplog.records, [r.getMessage() for r in caplog.records]
```

- [ ] **Step 2: Correr y ver que falla**

Run: `uv run pytest tests/test_manifest_guardrails.py -q`
Expected: FAIL en brand-chef, nutritionist (`does not apply`), debt-collector, payment-reminder, tutor-assistant (`needs a classifier` / `no valid patterns`).

- [ ] **Step 3: Editar los manifiestos según la tabla**

- [ ] **Step 4: Schema de VS Code**

Reemplazar `$defs.guardrailRule` en `vscode-extension/schemas/agent.schema.json` por:

```json
    "guardrailRule": {
      "type": "object",
      "description": "A single guardrail rule. Unknown keys are ignored with a warning at load time.",
      "required": ["type"],
      "additionalProperties": true,
      "properties": {
        "type": {
          "type": "string",
          "description": "pii_detection (input/output), topic_filter (input), max_length (input), content_filter (output), cost_limit (run budget; either side).",
          "enum": ["pii_detection", "topic_filter", "max_length", "content_filter", "cost_limit"]
        },
        "action": {
          "type": "string",
          "description": "pii_detection: redact|block|warn (default redact). topic_filter: warn|block (default warn). max_length: truncate|block (default truncate). content_filter: redact|block (default redact). cost_limit always blocks.",
          "enum": ["redact", "block", "warn", "truncate"]
        },
        "message": {
          "type": "string",
          "description": "Answer returned when this rule blocks. Default: \"I can't help with that request.\""
        },
        "blocked_topics": {"type": "array", "items": {"type": "string"}, "description": "topic_filter: case-insensitive substrings. Alias: forbidden_topics."},
        "forbidden_topics": {"type": "array", "items": {"type": "string"}, "description": "Alias of blocked_topics."},
        "max_chars": {"type": "integer", "minimum": 1, "description": "max_length: character limit (default 10000). Alias: max_characters."},
        "max_characters": {"type": "integer", "minimum": 1, "description": "Alias of max_chars."},
        "blocked_patterns": {"type": "array", "items": {"type": "string"}, "description": "content_filter: case-insensitive regular expressions."},
        "forbidden_keywords": {"type": "array", "items": {"type": "string"}, "description": "content_filter: literal case-insensitive keywords."},
        "max_tokens_per_turn": {"type": "integer", "minimum": 1, "description": "cost_limit: token budget for the whole run, checked before each model call."},
        "count": {"type": "string", "enum": ["output", "total"], "description": "cost_limit: count output tokens (default) or input+output."}
      }
    },
```

(Mantener la indentación del archivo; validar con `uv run python -c "import json; json.load(open('vscode-extension/schemas/agent.schema.json'))"`.)

- [ ] **Step 5: Correr**

Run: `uv run pytest tests/test_manifest_guardrails.py tests/test_agent_schema.py -q && uv run pytest -q -x`
Expected: PASS.

- [ ] **Step 6: CHANGELOG y commit**

`### Changed`:

```markdown
- Manifiestos y templates de `config/` alineados con los guardrails que ahora se aplican:
  `cost_limit` a 4000 tokens de salida por corrida; fuera `allowed_topics` y
  `blocked_categories` (requieren un clasificador); `debt-collector`, `payment-reminder` y
  `returns-claims` dejan de redactar PII de entrada (sus IDs numéricos se confundían con
  teléfonos o tarjetas) y la redactan en la salida. El schema de VS Code documenta cada
  regla, acción y alias.
```

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add config/ vscode-extension/schemas/agent.schema.json tests/test_manifest_guardrails.py CHANGELOG.md
git commit -m "fix(config): manifiestos con guardrails que el motor entiende

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Documentación

**Files:**
- Modify: `docs-site/src/content/docs/architecture/agent-pipeline.md` (secciones "Step 3: Input Guardrails" y "Step 10: Output Guardrails", y la mención en "Step 11" a "Guardrail actions taken")
- Modify: `docs-site/src/content/docs/architecture/four-layer-design.md` (sección "Guardrails Engine")
- Modify: `docs-site/src/content/docs/advanced/whatsapp.md` sólo si su ejemplo usa claves que ya no existen

**Interfaces:** ninguna.

- [ ] **Step 1: Reescribir "Step 3: Input Guardrails"** con: cuándo corre (antes de memoria/RAG/prefetch/modelo; multimodal por parte de texto; todo lo de después ve el texto filtrado), la tabla de reglas de entrada con claves, alias y acciones/defaults (de la tabla del spec), el resultado de rechazo (JSON del spec con `blocked`/`guardrail`), que un bloqueo de entrada no persiste el turno, y el ejemplo YAML corregido:

```yaml
spec:
  guardrails:
    input:
      - type: pii_detection
        action: redact
      - type: topic_filter
        blocked_topics: ["violence", "weapons"]
        action: block
        message: "I can't help with that."
      - type: max_length
        max_chars: 5000
        action: block
      - type: cost_limit
        max_tokens_per_turn: 4000
```

- [ ] **Step 2: Reescribir "Step 10: Output Guardrails"** con: corre sobre `answer` antes de persistir y de `output_schema`; `pii_detection` y `content_filter` (`blocked_patterns` regex, `forbidden_keywords` literales; `redact` → `[FILTERED]`, `block` → mensaje); el stream (`token`) se filtra con las mismas reglas y no se emite si bloquea; `cost_limit` como presupuesto de la corrida chequeado antes de cada llamada (`count: output|total`); un bloqueo de salida persiste la pregunta y el rechazo; ejemplo YAML con claves reales. Un párrafo "Limits": patrones PII de EE. UU. (un teléfono argentino no se detecta), temas por subcadena, sin clasificadores (`blocked_categories`/`allowed_topics` avisan al cargar y se ignoran), reglas inválidas descartadas con warning.

- [ ] **Step 3: "Guardrails Engine" en `four-layer-design.md`**: tabla corta (regla, dirección, acciones) coherente con lo anterior y link a `agent-pipeline` para el detalle. Quitar cualquier afirmación sobre bloquear "with an error response".

- [ ] **Step 4: Build del sitio**

Run: `cd docs-site && npm run build`
Expected: build OK (si el worktree no tiene `node_modules`, symlinkear temporalmente `../../astromesh/docs-site/node_modules` y quitar el symlink después).

- [ ] **Step 5: Commit**

```bash
git add docs-site/src/content/docs/
git commit -m "docs(site): guardrails — reglas reales, rechazo estructurado, stream y cost_limit

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
