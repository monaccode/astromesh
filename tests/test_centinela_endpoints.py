import pytest

from astromesh.centinela.endpoints import (
    EndpointAction,
    EndpointPlanError,
    diff_endpoint,
    endpoint_name,
    plan_endpoints,
)

REAL_SHA = "a" * 40


def _rev(rev, sha=REAL_SHA, gate="passed"):
    return {"version": rev, "sha": sha, "gate": gate,
            "eval": {"macro_f1": 0.9, "invalid_rate": 0.01}}


def _model(name="centinela-sentiment", kind="classifier", aliases=None, revisions=None):
    return {"name": name, "kind": kind, "task": "text-classification", "vertical": "finanzas",
            "hf_repo": "astromesh/Centinela-Qwen3-4B",
            "contract": {"labels": ["positivo", "neutral", "negativo"]},
            "aliases": aliases if aliases is not None else {"prod": "v0.1"},
            "revisions": revisions if revisions is not None else {"v0.1": _rev("v0.1")}}


def _lock(models):
    return {"schema_version": "1", "models": models}


def _bindings(entries):
    return {"apiVersion": "astromesh/v1", "kind": "CentinelaBindings",
            "metadata": {"name": "default"}, "spec": {"bindings": entries}}


def _binding(alias="prod", serving=None):
    b = {"model": "centinela-sentiment", "alias": alias}
    if serving is not None:
        b["serving"] = serving
    return b


def test_endpoint_name_is_deterministic():
    assert endpoint_name("centinela-sentiment", "prod") == "centinela-sentiment-prod"


def test_plan_served_binding_real_sha_is_ready():
    plan = plan_endpoints(_lock([_model()]), _bindings([_binding(serving={
        "vendor": "aws", "region": "us-east-1", "accelerator": "gpu",
        "instance_type": "nvidia-a10g", "instance_size": "x1"})]))
    assert len(plan) == 1
    d = plan[0]
    assert d.name == "centinela-sentiment-prod"
    assert d.repository == "astromesh/Centinela-Qwen3-4B"
    assert d.revision == REAL_SHA
    assert d.instance_type == "nvidia-a10g"
    assert d.type == "protected"
    assert d.ready is True


def test_plan_placeholder_sha_is_not_ready():
    m = _model(revisions={"v0.1": _rev("v0.1", sha="REPLACE_WITH_REAL_HF_REVISION_SHA")})
    plan = plan_endpoints(_lock([m]), _bindings([_binding()]))
    assert plan[0].ready is False


def test_plan_defaults_serving_when_absent():
    plan = plan_endpoints(_lock([_model()]), _bindings([_binding(serving=None)]))
    d = plan[0]
    assert d.vendor == "aws" and d.scale_to_zero is True and d.api_key_env == "HF_TOKEN"


def test_plan_unknown_model_raises():
    with pytest.raises(EndpointPlanError):
        plan_endpoints(_lock([]), _bindings([_binding()]))


def test_plan_non_served_kind_raises():
    m = _model(name="centinela-chat", kind="instruct", aliases={"prod": "v1"},
               revisions={"v1": _rev("v1")})
    with pytest.raises(EndpointPlanError):
        plan_endpoints(_lock([m]), _bindings([{"model": "centinela-chat", "alias": "prod"}]))


def test_plan_gate_not_passed_raises():
    m = _model(revisions={"v0.1": _rev("v0.1", gate="pending")})
    with pytest.raises(EndpointPlanError):
        plan_endpoints(_lock([m]), _bindings([_binding()]))


def test_diff_create_when_absent():
    d = plan_endpoints(_lock([_model()]), _bindings([_binding()]))[0]
    assert diff_endpoint(d, None) == EndpointAction("create", {})


def test_diff_update_on_revision_change():
    d = plan_endpoints(_lock([_model()]), _bindings([_binding()]))[0]
    actual = {"revision": "b" * 40, "accelerator": "gpu",
              "instance_type": "nvidia-a10g", "instance_size": "x1"}
    action = diff_endpoint(d, actual)
    assert action.kind == "update"
    assert action.fields == {"revision": REAL_SHA}


def test_diff_noop_when_identical():
    d = plan_endpoints(_lock([_model()]), _bindings([_binding(serving={
        "instance_type": "nvidia-a10g", "instance_size": "x1", "accelerator": "gpu"})]))[0]
    actual = {"revision": REAL_SHA, "accelerator": "gpu",
              "instance_type": "nvidia-a10g", "instance_size": "x1"}
    assert diff_endpoint(d, actual) == EndpointAction("noop", {})
