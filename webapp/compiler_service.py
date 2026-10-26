"""Adapt the existing compiler stages into structured, non-executing API results."""
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path

from multilang_transpiler.codegen import generate
from multilang_transpiler.errors import CompileError
from multilang_transpiler.ir import lower
from multilang_transpiler.lexer import tokenize
from multilang_transpiler.parser import parse
from multilang_transpiler.preprocessor import preprocess
from multilang_transpiler.semantic import analyze
from multilang_transpiler.validation import validate_generated as _syntax_validate

LANGUAGES = {"c", "python", "javascript"}
MAX_SOURCE_CHARS = 50_000
ROOT = Path(__file__).resolve().parents[1]
PHASES = [
    ("preprocessing", "Preprocessing", "Normalize accepted source conventions and handle supported C headers."),
    ("lexical", "Lexical Analysis", "Turn source characters into positioned tokens such as names, literals, and operators."),
    ("syntax", "Syntax Analysis", "Check token order against the supported grammar and build the program structure."),
    ("ast", "AST Construction", "Show the parsed program as a tree of statements and expressions."),
    ("semantic", "Semantic Analysis", "Check supported declarations, names, arrays, constants, and function calls."),
    ("ir", "Intermediate Representation", "Lower the AST into language-neutral operations used by target code generation."),
    ("generation", "Code Generation", "Render the intermediate operations as source code in the selected target language."),
    ("validation", "Validation", "Check generated target syntax when the required validator is installed; do not execute it."),
]


def _jsonable(value):
    if is_dataclass(value):
        return asdict(value)
    return value


def _blank_phases():
    return [{"id": key, "name": name, "description": description, "status": "not_reached", "output": None}
            for key, name, description in PHASES]


def _set_phase(phases, key, status, output):
    next(p for p in phases if p["id"] == key).update(status=status, output=output)


def transpile(source_language, target_language, source_code):
    if source_language not in LANGUAGES or target_language not in LANGUAGES:
        raise ValueError("Languages must be c, python, or javascript.")
    if not isinstance(source_code, str):
        raise ValueError("source_code must be a string.")
    if len(source_code) > MAX_SOURCE_CHARS:
        raise ValueError(f"Source exceeds the {MAX_SOURCE_CHARS:,} character limit.")

    phases = _blank_phases()
    result = {
        "success": False,
        "source_language": source_language,
        "target_language": target_language,
        "generated_code": None,
        "tokens": None,
        "ast": None,
        "ir": None,
        "diagnostics": [],
        "warnings": [],
        "phases": phases,
    }
    failed_phase = "preprocessing"
    try:
        prepared = preprocess(source_code, source_language)
        _set_phase(phases, "preprocessing", "completed", prepared)
        failed_phase = "lexical"
        tokens = tokenize(prepared, source_language)
        token_data = [asdict(token) for token in tokens]
        result["tokens"] = token_data
        _set_phase(phases, "lexical", "completed", token_data)
        failed_phase = "syntax"
        tree = parse(prepared, source_language)
        ast_data = _jsonable(tree)
        result["ast"] = ast_data
        _set_phase(phases, "syntax", "completed", {"message": "Program parsed successfully."})
        first_statement = (ast_data.get("body") or [None])[0]
        example = None
        if first_statement:
            source_lines = source_code.splitlines()
            source_line = first_statement.get("line", 1)
            example = {"source": source_lines[source_line - 1].strip() if 0 < source_line <= len(source_lines) else "",
                       "node": first_statement}
        _set_phase(phases, "ast", "completed", {
            "explanation": "The Abstract Syntax Tree (AST) records the source program's nested structure using statement and expression nodes.",
            "example": example,
            "tree": ast_data,
        })
        failed_phase = "semantic"
        semantic_result = analyze(tree, source_language, detailed=True)
        semantic_warnings = semantic_result["warnings"]
        result["warnings"].extend(semantic_warnings)
        _set_phase(phases, "semantic", "completed_with_warnings" if semantic_warnings else "completed", semantic_result)
        failed_phase = "ir"
        ir_data = lower(tree)
        result["ir"] = ir_data
        _set_phase(phases, "ir", "completed", ir_data)
        failed_phase = "generation"
        target_code = generate(ir_data, target_language)
        result["generated_code"] = target_code
        _set_phase(phases, "generation", "completed", target_code)
        failed_phase = "validation"
        validation = _syntax_validate(target_language, target_code)
        status = "failed" if validation["status"] == "failed" else ("completed" if validation["status"] == "passed" else "completed_with_warnings")
        _set_phase(phases, "validation", status, validation)
        if validation["status"] == "unavailable":
            result["warnings"].append(validation["message"])
        elif validation["status"] == "failed":
            result["diagnostics"].append({"category": "target_validation", "phase": "validation", "message": validation["message"], "line": validation.get("line"), "column": validation.get("column")})
            result["error"] = result["diagnostics"][-1]
            # Keep the rejected text in the generation phase trace for diagnosis,
            # but do not surface it as usable output after a failed conversion.
            result["generated_code"] = None
            return result
        result["success"] = True
        return result
    except CompileError as exc:
        phase = exc.phase if exc.phase in {p[0] for p in PHASES} else failed_phase
        error = {"category": exc.phase, "phase": phase, "message": exc.message, "line": exc.line, "column": None}
        result["error"] = error
        result["diagnostics"].append(error)
        _set_phase(phases, phase, "failed", error)
        return result
    except (ValueError, IndexError, RecursionError) as exc:
        error = {"category": "compiler", "phase": failed_phase, "message": str(exc) or "Malformed input.", "line": None, "column": None}
        result["error"] = error
        result["diagnostics"].append(error)
        _set_phase(phases, failed_phase, "failed", error)
        return result


def run_matrix_checks():
    """Exercise the nine regression routes through syntax validation; never run submitted programs."""
    extensions = {"c": "c", "python": "py", "javascript": "js"}
    samples = {language: (ROOT / "samples" / f"regression.{extension}").read_text(encoding="utf-8")
               for language, extension in extensions.items()}
    checks = []
    for source_language, code in samples.items():
        for target_language in samples:
            converted = transpile(source_language, target_language, code)
            validation = next(p["output"] for p in converted["phases"] if p["id"] == "validation")
            status = "failed" if not converted["success"] or validation and validation.get("status") == "failed" else ("skipped" if validation and validation.get("status") == "unavailable" else "passed")
            message = converted.get("error", {}).get("message", "Conversion failed.") if status == "failed" else ("Translation completed; target syntax checker unavailable. No programs were executed." if status == "skipped" else "Translation and target syntax validation passed. No programs were executed.")
            checks.append({"name": f"{source_language} → {target_language}", "status": status, "passed": status == "passed", "message": message, "validation": validation})
    return {"passed": sum(c["status"] == "passed" for c in checks), "failed": sum(c["status"] == "failed" for c in checks), "skipped": sum(c["status"] == "skipped" for c in checks), "checks": checks, "execution": "No source or generated programs were executed."}
