"""Shared source-to-source compiler pipeline used by the CLI and migration tools."""

from .codegen import generate
from .ir import lower
from .parser import parse
from .semantic import analyze


def transpile_source(source: str, source_language: str, target_language: str) -> str:
    """Compile source through the project's real parser, semantic pass, IR, and generator."""
    tree = parse(source, source_language)
    analyze(tree, source_language)
    return generate(lower(tree), target_language)
