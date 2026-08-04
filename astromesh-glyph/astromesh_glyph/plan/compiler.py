"""AST -> PlanGraph.

Dos trabajos: derivar el grafo de dependencias entre sentencias, y validar todo
lo que se pueda validar sin ejecutar nada. Lo segundo importa tanto como lo
primero: cada error detectado acá es un round-trip que no se gasta a mitad de la
ejecución, con efectos ya hechos.
"""

from __future__ import annotations

from collections.abc import Sequence

from astromesh_glyph.capabilities import CapabilitySpec
from astromesh_glyph.errors import GlyphCompileError
from astromesh_glyph.plan.graph import PlanGraph, PlanNode
from astromesh_glyph.syntax import nodes as n

# Etapas del pipe: son builtins del lenguaje, no capacidades. El host no puede
# redefinirlas ni agregar nuevas.
BUILTIN_STAGES = frozenset({"where", "top", "map"})


def compile_program(program: n.Program, capabilities: Sequence[CapabilitySpec]) -> PlanGraph:
    catalog = {cap.name: cap for cap in capabilities}
    bound: set[str] = set()
    nodes: list[PlanNode] = []

    for index, stmt in enumerate(program.body):
        reads: set[str] = set()
        writes: list[str] = []
        _walk_statement(stmt, catalog, reads, writes)

        undefined = reads - bound
        if undefined:
            raise GlyphCompileError(f"la variable `{min(undefined)}` no está definida", stmt.line)
        for name in writes:
            if name in bound:
                raise GlyphCompileError(
                    f"`{name}` ya está ligada: Glyph no permite reasignar", stmt.line
                )
            bound.add(name)

        nodes.append(
            PlanNode(
                id=f"n{index}",
                stmt=stmt,
                depends_on=frozenset(reads),
                produces=frozenset(writes),
            )
        )

    return PlanGraph(nodes=tuple(nodes))


def _walk_statement(
    stmt: n.Node,
    catalog: dict[str, CapabilitySpec],
    reads: set[str],
    writes: list[str],
) -> None:
    """Acumula lecturas y escrituras de una sentencia, validando de paso.

    Un `if` se trata como una unidad: sus lecturas son las del test más las de
    todo su cuerpo, y sus escrituras las de su cuerpo. Eso hace que el nodo
    entero espere a todo lo que necesita y que los nombres ligados adentro sean
    visibles después — al costo de que el cuerpo corre secuencial.
    """
    match stmt:
        case n.Assign(target=target, value=value):
            _walk_expression(value, catalog, reads)
            writes.append(target)
        case n.Return(value=value) | n.ExprStmt(value=value):
            if value is not None:
                _walk_expression(value, catalog, reads)
        case n.If(test=test, body=body, orelse=orelse):
            _walk_expression(test, catalog, reads)
            # Las ramas se recorren por separado y sus escrituras se unen. Ligar
            # el mismo nombre en el `if` y en el `else` NO es reasignar: corre una
            # sola de las dos. Aplanarlas en una lista lo hacía ver como
            # duplicado y rechazaba el patrón más natural del lenguaje.
            branch_writes: list[str] = []
            for branch in (body, orelse):
                seen: list[str] = []
                for inner in branch:
                    _walk_statement(inner, catalog, reads, seen)
                # Dentro de UNA rama, repetir un nombre sí es reasignar.
                for index, name in enumerate(seen):
                    if name in seen[:index]:
                        raise GlyphCompileError(
                            f"`{name}` ya está ligada: Glyph no permite reasignar", stmt.line
                        )
                branch_writes.extend(name for name in seen if name not in branch_writes)
            # Lo que el cuerpo escribe no cuenta como lectura pendiente del nodo.
            reads -= set(branch_writes)
            writes.extend(branch_writes)
        case _:
            raise GlyphCompileError(f"sentencia no soportada: {type(stmt).__name__}", stmt.line)


def _walk_expression(
    expr: n.Node | None, catalog: dict[str, CapabilitySpec], reads: set[str]
) -> None:
    match expr:
        case None | n.Literal():
            return
        case n.Name(id=name):
            reads.add(name)
        case n.Attribute(value=value):
            _walk_expression(value, catalog, reads)
        case n.ListLit(items=items):
            for item in items:
                _walk_expression(item, catalog, reads)
        case n.DictLit(items=items):
            for _, value in items:
                _walk_expression(value, catalog, reads)
        case n.BinOp(left=left, right=right):
            _walk_expression(left, catalog, reads)
            _walk_expression(right, catalog, reads)
        case n.Pipe(left=left, stages=stages):
            _walk_expression(left, catalog, reads)
            for stage in stages:
                if stage.func not in BUILTIN_STAGES:
                    raise GlyphCompileError(
                        f"`{stage.func}` no es una etapa válida; "
                        f"las etapas son: {', '.join(sorted(BUILTIN_STAGES))}",
                        stage.line,
                    )
                # Los argumentos de una etapa se evalúan por elemento, con los
                # campos del elemento en scope, así que sus nombres libres no son
                # dependencias del nodo.
        case n.Call() as call:
            _validate_call(call, catalog)
            for arg in call.args:
                _walk_expression(arg, catalog, reads)
            for value in call.kwargs.values():
                _walk_expression(value, catalog, reads)
        case _:
            raise GlyphCompileError(f"expresión no soportada: {type(expr).__name__}", expr.line)


def _validate_call(call: n.Call, catalog: dict[str, CapabilitySpec]) -> None:
    spec = catalog.get(call.func)
    if spec is None:
        available = ", ".join(sorted(catalog)) or "(ninguna)"
        raise GlyphCompileError(
            f"la capacidad `{call.func}` no existe; disponibles: {available}", call.line
        )
    if call.args:
        raise GlyphCompileError(
            f"`{call.func}` recibe sus argumentos por nombre, no por posición", call.line
        )

    properties = spec.parameters.get("properties", {})
    if properties:
        for key in call.kwargs:
            if key not in properties:
                raise GlyphCompileError(
                    f"`{call.func}` no acepta el argumento `{key}`; "
                    f"acepta: {', '.join(sorted(properties))}",
                    call.line,
                )
    for required in spec.parameters.get("required", []):
        if required not in call.kwargs:
            raise GlyphCompileError(f"`{call.func}` requiere `{required}`", call.line)
