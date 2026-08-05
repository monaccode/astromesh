"""Nodos del AST de Glyph.

Cinco sentencias y ocho expresiones. Cada nodo lleva `line` porque todo error de
compilación se le devuelve al modelo con la línea, y sin eso la reparación es a
ciegas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Node:
    line: int = 0


# ---- expresiones -------------------------------------------------------------


@dataclass
class Literal(Node):
    value: Any = None


@dataclass
class Name(Node):
    id: str = ""


@dataclass
class Attribute(Node):
    value: Node | None = None
    attr: str = ""


@dataclass
class Call(Node):
    func: str = ""
    args: list[Node] = field(default_factory=list)
    kwargs: dict[str, Node] = field(default_factory=dict)


@dataclass
class Pipe(Node):
    left: Node | None = None
    stages: list[Call] = field(default_factory=list)


@dataclass
class BinOp(Node):
    op: str = ""
    left: Node | None = None
    right: Node | None = None


@dataclass
class DictLit(Node):
    items: list[tuple[str, Node]] = field(default_factory=list)


@dataclass
class ListLit(Node):
    items: list[Node] = field(default_factory=list)


# ---- sentencias --------------------------------------------------------------


@dataclass
class Assign(Node):
    target: str = ""
    value: Node | None = None


@dataclass
class If(Node):
    test: Node | None = None
    body: list[Node] = field(default_factory=list)
    orelse: list[Node] = field(default_factory=list)


@dataclass
class Return(Node):
    value: Node | None = None


@dataclass
class ExprStmt(Node):
    value: Node | None = None


@dataclass
class Program(Node):
    body: list[Node] = field(default_factory=list)
