from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TokenType(StrEnum):
    NAME = "NAME"
    NUMBER = "NUMBER"
    STRING = "STRING"
    OP = "OP"
    NEWLINE = "NEWLINE"
    INDENT = "INDENT"
    DEDENT = "DEDENT"
    EOF = "EOF"


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str
    line: int
    column: int
