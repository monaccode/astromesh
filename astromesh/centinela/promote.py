"""Plan a Centinela catalog promotion: diff two locks against the operator's bindings.

Pure logic, no I/O. Given the previous (vendored) catalog lock, the newly published
lock, and `bindings.yaml`, produce a PromotionPlan describing which aliases moved, which
served aliases still need an endpoint binding, and which bound aliases are now unservable.
The CLI wrapper turns a plan into file edits + a PR body.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from astromesh.centinela.reconcile import _SERVED_KINDS

_SUPPORTED_SCHEMA = "1"


class PromoteError(ValueError):
    """The new lock cannot be planned against (e.g. unsupported schema)."""


@dataclass(frozen=True)
class AliasMove:
    model: str
    alias: str
    from_rev: str | None
    to_rev: str
    from_eval: dict | None
    to_eval: dict | None


@dataclass(frozen=True)
class MissingBinding:
    model: str
    alias: str


@dataclass(frozen=True)
class Blocked:
    model: str
    alias: str
    reason: str


@dataclass(frozen=True)
class PromotionPlan:
    alias_moves: list[AliasMove] = field(default_factory=list)
    missing_bindings: list[MissingBinding] = field(default_factory=list)
    blocked: list[Blocked] = field(default_factory=list)

    @property
    def is_noop(self) -> bool:
        return not (self.alias_moves or self.missing_bindings or self.blocked)


def _eval_of(model: dict | None, rev_key: str | None) -> dict | None:
    """Return the eval block of a revision, or None if absent."""
    if not model or rev_key is None:
        return None
    return model.get("revisions", {}).get(rev_key, {}).get("eval")


def plan_promotion(old_lock: dict, new_lock: dict, bindings: dict) -> PromotionPlan:
    """Diff old vs new lock against the bindings; classify every changed alias."""
    if str(new_lock.get("schema_version")) != _SUPPORTED_SCHEMA:
        raise PromoteError(
            f"unsupported schema_version {new_lock.get('schema_version')!r}; expected '1'"
        )

    old_models = {m["name"]: m for m in old_lock.get("models", [])}
    new_models = {m["name"]: m for m in new_lock.get("models", [])}
    bound = {(b["model"], b["alias"]) for b in bindings.get("spec", {}).get("bindings", [])}

    moves: list[AliasMove] = []
    missing: list[MissingBinding] = []
    blocked: list[Blocked] = []

    for name, model in new_models.items():
        old_model = old_models.get(name)
        old_aliases = (old_model or {}).get("aliases", {})
        served = model.get("kind") in _SERVED_KINDS
        revisions = model.get("revisions", {})

        for alias, target in model.get("aliases", {}).items():
            is_bound = (name, alias) in bound
            old_target = old_aliases.get(alias)
            rev = revisions.get(target)

            if rev is None:
                if is_bound:
                    blocked.append(
                        Blocked(
                            name,
                            alias,
                            f"alias '{alias}' points at '{target}', absent from the new lock",
                        )
                    )
                continue

            if old_target == target:
                continue  # unchanged and valid — nothing to do

            if rev.get("gate") != "passed":
                if is_bound:
                    blocked.append(
                        Blocked(
                            name,
                            alias,
                            f"{name}:{target} has gate '{rev.get('gate')}', "
                            "only 'passed' may be served",
                        )
                    )
                continue  # unbound + bad gate: not servable, no action

            moves.append(
                AliasMove(
                    name,
                    alias,
                    old_target,
                    target,
                    _eval_of(old_model, old_target),
                    _eval_of(model, target),
                )
            )
            if served and not is_bound:
                missing.append(MissingBinding(name, alias))

    for name, alias in bound:
        new_model = new_models.get(name)
        if new_model is None:
            blocked.append(Blocked(name, alias, f"model '{name}' removed from the new lock"))
        elif alias not in new_model.get("aliases", {}):
            blocked.append(
                Blocked(
                    name,
                    alias,
                    f"alias '{alias}' removed from model '{name}' in the new lock",
                )
            )

    return PromotionPlan(moves, missing, blocked)


STUB_ENDPOINT = "https://REPLACE_WITH_REAL_HF_ENDPOINT.endpoints.huggingface.cloud"
_PIN_RE = re.compile(r"astromesh-nebula>=[^\"']*")


def pr_labels(plan: PromotionPlan) -> list[str]:
    """Label the PR: prod if a prod alias is involved, else staging; mark blocked."""
    prod = any(m.alias == "prod" for m in plan.alias_moves) or any(
        b.alias == "prod" for b in plan.blocked
    )
    labels = ["centinela:prod"] if prod else ["centinela:staging"]
    if plan.blocked:
        labels.append("centinela:blocked")
    return labels


def stub_binding(model: str, alias: str) -> dict:
    """A placeholder binding a human must complete with a real endpoint URL."""
    return {"model": model, "alias": alias, "endpoint": STUB_ENDPOINT}


def _fmt_delta(from_eval: dict | None, to_eval: dict | None, key: str) -> str:
    to_v = (to_eval or {}).get(key)
    from_v = (from_eval or {}).get(key)
    if to_v is None:
        return "—"
    if from_v is None:
        return f"{to_v}"
    return f"{from_v} → {to_v}"


def render_pr_body(plan: PromotionPlan, version: str) -> str:
    """Render the promotion summary + human checklist as Markdown."""
    prod = any(m.alias == "prod" for m in plan.alias_moves)
    lines = ["# ⬆️ Centinela PROD promotion" if prod else "# Centinela staging sync", ""]
    lines += [f"Nebula catalog version: `{version}`", ""]

    if plan.alias_moves:
        lines += [
            "## Alias moves",
            "",
            "| model | alias | from | to | macro_f1 | invalid_rate |",
            "|-------|-------|------|----|----------|--------------|",
        ]
        for m in plan.alias_moves:
            f1 = _fmt_delta(m.from_eval, m.to_eval, "macro_f1")
            inv = _fmt_delta(m.from_eval, m.to_eval, "invalid_rate")
            lines.append(
                f"| {m.model} | {m.alias} | {m.from_rev or '—'} | {m.to_rev} | {f1} | {inv} |"
            )
        lines.append("")

    if plan.missing_bindings:
        lines += [
            "## ⚠️ Missing endpoint bindings",
            "",
            "A stub was added to `config/centinela/bindings.yaml`. "
            "Provide the live endpoint URL before merge:",
            "",
        ]
        for mb in plan.missing_bindings:
            lines.append(f"- [ ] set the endpoint for `{mb.model}` / `{mb.alias}`")
        lines.append("")

    if plan.blocked:
        lines += ["## 🚫 Blocked — do not merge until resolved", ""]
        for b in plan.blocked:
            lines.append(f"- `{b.model}` / `{b.alias}`: {b.reason}")
        lines.append("")

    return "\n".join(lines)


def bump_nebula_pin(text: str, version: str) -> str:
    """Rewrite every `astromesh-nebula>=…` constraint to `>=<version>`."""
    return _PIN_RE.sub(f"astromesh-nebula>={version}", text)
