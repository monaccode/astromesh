import pytest

from astromesh.centinela.promote import (
    MissingBinding,
    PromoteError,
    plan_promotion,
)


def _rev(rev, gate="passed", f1=0.9, inv=0.01):
    return {"version": rev, "sha": "a" * 40, "gate": gate,
            "eval": {"macro_f1": f1, "invalid_rate": inv}}


def _model(name="centinela-sentiment", kind="classifier", aliases=None, revisions=None):
    return {
        "name": name, "kind": kind, "task": "text-classification",
        "vertical": "finanzas", "hf_repo": "astromesh/Centinela-Qwen3-4B",
        "contract": {"labels": ["positivo", "neutral", "negativo"]},
        "aliases": aliases if aliases is not None else {"prod": "v0.1"},
        "revisions": revisions if revisions is not None else {"v0.1": _rev("v0.1")},
    }


def _lock(models):
    return {"schema_version": "1", "models": models}


def _bindings(entries):
    return {"apiVersion": "astromesh/v1", "kind": "CentinelaBindings",
            "metadata": {"name": "default"}, "spec": {"bindings": entries}}


BIND_PROD = [{"model": "centinela-sentiment", "alias": "prod",
              "endpoint": "https://ep.example.cloud"}]


def test_staging_alias_moved_with_binding_is_a_clean_move():
    old = _lock([_model(aliases={"staging": "v0.1"},
                        revisions={"v0.1": _rev("v0.1"), "v0.2": _rev("v0.2")})])
    new = _lock([_model(aliases={"staging": "v0.2"},
                        revisions={"v0.1": _rev("v0.1"), "v0.2": _rev("v0.2")})])
    bindings = _bindings([{"model": "centinela-sentiment", "alias": "staging",
                           "endpoint": "https://ep.example.cloud"}])
    plan = plan_promotion(old, new, bindings)
    assert len(plan.alias_moves) == 1
    assert plan.alias_moves[0].from_rev == "v0.1"
    assert plan.alias_moves[0].to_rev == "v0.2"
    assert plan.missing_bindings == []
    assert plan.blocked == []
    assert plan.is_noop is False


def test_new_served_alias_without_binding_is_missing():
    old = _lock([_model(aliases={}, revisions={"v0.1": _rev("v0.1")})])
    new = _lock([_model(aliases={"staging": "v0.1"}, revisions={"v0.1": _rev("v0.1")})])
    plan = plan_promotion(old, new, _bindings([]))
    assert plan.missing_bindings == [MissingBinding("centinela-sentiment", "staging")]


def test_bound_alias_moved_to_failing_gate_is_blocked():
    old = _lock([_model(aliases={"prod": "v0.1"},
                        revisions={"v0.1": _rev("v0.1"), "v0.2": _rev("v0.2", gate="pending")})])
    new = _lock([_model(aliases={"prod": "v0.2"},
                        revisions={"v0.1": _rev("v0.1"), "v0.2": _rev("v0.2", gate="pending")})])
    plan = plan_promotion(old, new, _bindings(BIND_PROD))
    assert len(plan.blocked) == 1
    assert plan.blocked[0].alias == "prod"
    assert plan.alias_moves == []  # a blocked move is not also reported clean


def test_removed_revision_under_bound_alias_is_blocked():
    old = _lock([_model(aliases={"prod": "v0.1"}, revisions={"v0.1": _rev("v0.1")})])
    new = _lock([_model(aliases={"prod": "v0.1"}, revisions={})])  # v0.1 gone
    plan = plan_promotion(old, new, _bindings(BIND_PROD))
    assert len(plan.blocked) == 1
    assert "absent" in plan.blocked[0].reason


def test_identical_locks_is_noop():
    lock = _lock([_model()])
    plan = plan_promotion(lock, lock, _bindings(BIND_PROD))
    assert plan.is_noop is True


def test_non_served_kind_alias_is_not_flagged_missing():
    old = _lock([_model(name="centinela-chat", kind="instruct", aliases={},
                        revisions={"v1": _rev("v1")})])
    new = _lock([_model(name="centinela-chat", kind="instruct", aliases={"prod": "v1"},
                        revisions={"v1": _rev("v1")})])
    plan = plan_promotion(old, new, _bindings([]))
    assert plan.missing_bindings == []


def test_unsupported_schema_version_raises():
    new = {"schema_version": "2", "models": []}
    with pytest.raises(PromoteError):
        plan_promotion(_lock([]), new, _bindings([]))
