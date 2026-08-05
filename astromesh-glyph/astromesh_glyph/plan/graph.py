"""El producto del compilador: un DAG de sentencias.

Un nodo por sentencia. Las aristas salen de qué variables lee cada sentencia,
lo cual es exacto porque el lenguaje prohíbe reasignar: un nombre tiene un único
productor en todo el programa.
"""

from __future__ import annotations

from dataclasses import dataclass

from astromesh_glyph.syntax import nodes as ast_nodes


@dataclass(frozen=True)
class PlanNode:
    id: str
    stmt: ast_nodes.Node
    depends_on: frozenset[str]
    produces: frozenset[str]


@dataclass(frozen=True)
class PlanGraph:
    nodes: tuple[PlanNode, ...]

    def node(self, node_id: str) -> PlanNode:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(node_id)

    def dependents(self, node_id: str) -> tuple[str, ...]:
        produced = self.node(node_id).produces
        if not produced:
            return ()
        return tuple(n.id for n in self.nodes if produced & n.depends_on)
