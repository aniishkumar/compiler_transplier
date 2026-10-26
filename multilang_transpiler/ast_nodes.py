from dataclasses import dataclass, field
from typing import Any

@dataclass
class Expr: kind: str; value: Any = None; children: list = field(default_factory=list); line: int = 1
@dataclass
class Stmt: kind: str; value: Any = None; exprs: list = field(default_factory=list); body: list = field(default_factory=list); otherwise: list = field(default_factory=list); line: int = 1; declared_type: str | None = None
@dataclass
class Program: body: list; line: int = 1; source_language: str | None = None
