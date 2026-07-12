"""Plan a Centinela catalog promotion: diff two locks against the operator's bindings.

Pure logic, no I/O. Given the previous (vendored) catalog lock, the newly published
lock, and `bindings.yaml`, produce a PromotionPlan describing which aliases moved, which
served aliases still need an endpoint binding, and which bound aliases are now unservable.
The CLI wrapper turns a plan into file edits + a PR body.
"""

from __future__ import annotations

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
    bound = {
        (b["model"], b["alias"])
        for b in bindings.get("spec", {}).get("bindings", [])
    }

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
                    blocked.append(Blocked(
                        name, alias,
                        f"alias '{alias}' points at '{target}', absent from the new lock",
                    ))
                continue

            if old_target == target:
                continue  # unchanged and valid — nothing to do

            if rev.get("gate") != "passed":
                if is_bound:
                    blocked.append(Blocked(
                        name, alias,
                        f"{name}:{target} has gate '{rev.get('gate')}', "
                        "only 'passed' may be served",
                    ))
                continue  # unbound + bad gate: not servable, no action

            moves.append(AliasMove(
                name, alias, old_target, target,
                _eval_of(old_model, old_target), _eval_of(model, target),
            ))
            if served and not is_bound:
                missing.append(MissingBinding(name, alias))

    for name, alias in bound:
        new_model = new_models.get(name)
        if new_model is None:
            blocked.append(Blocked(name, alias, f"model '{name}' removed from the new lock"))
        elif alias not in new_model.get("aliases", {}):
            blocked.append(Blocked(
                name, alias, f"alias '{alias}' removed from model '{name}' in the new lock",
            ))

    return PromotionPlan(moves, missing, blocked)
