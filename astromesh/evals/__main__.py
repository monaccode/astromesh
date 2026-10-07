"""`astromesh-eval <config_dir> [archivo.eval.yaml ...] [--out reporte.json]`.

Exit: 0 si todos los evals cumplen sus umbrales, 1 si alguno no, 2 por error de carga
(en ese caso no corre ningún caso).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from astromesh.evals import fixtures
from astromesh.evals.formato import Eval, EvalError, cargar_eval
from astromesh.evals.runner import correr_eval


def _error(msg: str) -> int:
    print(f"astromesh-eval: {msg}", file=sys.stderr)
    return 2


def _tabla(ev: dict) -> None:
    print(f"\n{ev['name']} → {ev['agent']}")
    for c in ev["cases"]:
        tokens = c["tokens_in"] + c["tokens_out"]
        print(
            f"  {c['status']:<5} {c['id']:<24} {tokens:>7} tok  "
            f"${c['cost']:.4f}  {c['latency_ms']:>8.0f} ms"
        )
        for m in c["motivos"]:
            print(f"        · {m}")
    estado = "OK" if ev["passed"] else "BAJO UMBRAL"
    print(
        f"  pass_rate {ev['pass_rate']:.2f} · {ev['avg_tokens']:.0f} tok/caso · "
        f"${ev['total_cost']:.4f} · {estado}"
    )


async def correr(config_dir: str, evals: list[Eval], out: str | None) -> int:
    from astromesh.runtime.engine import AgentRuntime, build_candidate_provider

    try:
        runtime = AgentRuntime(config_dir=config_dir)
        await runtime.bootstrap()
    except Exception as exc:  # noqa: BLE001
        return _error(f"no arrancó el runtime: {exc}")
    jueces = {}
    for ev in evals:
        if ev.agent not in runtime._agents:
            motivo = runtime._agent_errors.get(ev.agent, "no está en el árbol de config")
            return _error(f"{ev.path}: agente {ev.agent!r} no disponible: {motivo}")
        if ev.judge_model is not None:
            try:
                juez = build_candidate_provider(ev.judge_model)
            except Exception as exc:  # noqa: BLE001
                return _error(f"{ev.path}: judge.model no construye un provider: {exc}")
            if juez is None:
                return _error(f"{ev.path}: judge.model no construye un provider")
            jueces[ev.path] = juez
    fixtures.preparar(runtime)
    run_id = uuid.uuid4().hex[:8]
    resultados = [await correr_eval(runtime, ev, run_id, jueces.get(ev.path)) for ev in evals]
    for r in resultados:
        _tabla(r)
    if out:
        Path(out).write_text(  # noqa: ASYNC240 - escritura única al final
            json.dumps({"run_id": run_id, "evals": resultados}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0 if all(r["passed"] for r in resultados) else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="astromesh-eval", description="Corre evals de agentes.")
    p.add_argument("config_dir")
    p.add_argument("archivos", nargs="*", help="por defecto, <config_dir>/evals/*.eval.yaml")
    p.add_argument("--out", help="escribe el reporte JSON acá")
    args = p.parse_args(argv)
    archivos = args.archivos or sorted(Path(args.config_dir, "evals").glob("*.eval.yaml"))
    if not archivos:
        return _error(f"no hay evals en {Path(args.config_dir, 'evals')}")
    try:
        evals = [cargar_eval(a) for a in archivos]
    except EvalError as exc:
        return _error(str(exc))
    return asyncio.run(correr(args.config_dir, evals, args.out))


if __name__ == "__main__":
    sys.exit(main())
