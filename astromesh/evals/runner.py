"""Corre un eval contra un AgentRuntime ya arrancado y `preparar`-ado.

Un caso nunca corta el eval: lo que levanta queda en `error` y cuenta como no aprobado.
"""

from __future__ import annotations

import copy
import time

from astromesh.api.usage import usage_from_trace
from astromesh.evals import fixtures
from astromesh.evals.asserts import chequear
from astromesh.evals.formato import Caso, Eval
from astromesh.evals.juez import juzgar


def _uso(trace) -> tuple[int, int, int, float]:
    u = usage_from_trace(trace) or {}
    filas = u.get("by_model") or []
    return (
        int(u.get("tokens_in", 0)),
        int(u.get("tokens_out", 0)),
        sum(int(f.get("tokens_cached", 0)) for f in filas),
        sum(float(f.get("cost", 0.0)) for f in filas),
    )


async def _correr_caso(runtime, ev: Eval, caso: Caso, run_id: str, juez) -> dict:
    session = f"eval-{run_id}-{caso.id}"
    r = {
        "id": caso.id,
        "status": "pass",
        "motivos": [],
        "judge": None,
        "tokens_in": 0,
        "tokens_out": 0,
        "cached_tokens": 0,
        "cost": 0.0,
        "latency_ms": 0.0,
        "judge_tokens": 0,
        "tools_llamadas": [],
        "answer": "",
    }
    inicio = time.monotonic()
    with fixtures.caso(caso.tools, bloquear=ev.tools_default == "block") as estado:
        try:
            for turno in caso.turns:
                res = await runtime.run(
                    ev.agent, turno, session, context=copy.deepcopy(caso.context)
                )
                r["answer"] = (res or {}).get("answer") or ""
                tin, tout, cached, cost = _uso((res or {}).get("trace"))
                r["tokens_in"] += tin
                r["tokens_out"] += tout
                r["cached_tokens"] += cached
                r["cost"] += cost
        except Exception as exc:  # noqa: BLE001  (un caso que levanta no corta el eval)
            r["status"] = "error"
            r["motivos"].append(f"{type(exc).__name__}: {exc}")
        r["tools_llamadas"] = list(estado.llamadas)
    r["latency_ms"] = round((time.monotonic() - inicio) * 1000, 1)
    if r["status"] == "error":
        return r

    for asercion in caso.expect:
        motivo = chequear(asercion, r["answer"], r["tools_llamadas"])
        if motivo:
            r["motivos"].append(motivo)
    if caso.rubric is not None:
        v = await juzgar(juez, caso.rubric, caso.turns, r["answer"])
        r["judge_tokens"] = v.tokens
        if v.error:
            r["status"] = "error"
            r["motivos"].append(v.error)
            return r
        r["judge"] = {"score": v.score, "reason": v.reason}
        if v.score < ev.judge_pass_score:
            r["motivos"].append(f"el juez dio {v.score} (< {ev.judge_pass_score}): {v.reason}")
    if r["motivos"]:
        r["status"] = "fail"
    return r


async def correr_eval(runtime, ev: Eval, run_id: str, juez=None) -> dict:
    casos = [await _correr_caso(runtime, ev, c, run_id, juez) for c in ev.casos]
    aprobados = sum(1 for c in casos if c["status"] == "pass")
    pass_rate = aprobados / len(casos)
    avg_tokens = sum(c["tokens_in"] + c["tokens_out"] for c in casos) / len(casos)
    passed = pass_rate >= ev.pass_rate and (
        ev.max_avg_tokens is None or avg_tokens <= ev.max_avg_tokens
    )
    return {
        "name": ev.name,
        "agent": ev.agent,
        "passed": passed,
        "pass_rate": round(pass_rate, 4),
        "avg_tokens": round(avg_tokens, 1),
        "total_cost": round(sum(c["cost"] for c in casos), 6),
        "cases": casos,
    }
