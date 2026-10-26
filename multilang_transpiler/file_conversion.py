"""Safe single-file conversion for the ``multilang convert`` command."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile

from .errors import CompileError
from .transpiler import transpile_source
from .validation import validate_generated

LANGUAGES = ("c", "python", "javascript")
SOURCE_EXTENSIONS = {
    ".c": "c", ".h": "c", ".py": "python", ".pyw": "python",
    ".js": "javascript", ".mjs": "javascript",
}
TARGET_EXTENSIONS = {"c": ".c", "python": ".py", "javascript": ".js"}
DISPLAY_NAMES = {"c": "C", "python": "Python", "javascript": "JavaScript"}


class ConversionError(Exception):
    """An actionable input, compilation, or output error."""


def infer_language(path: str | Path) -> str:
    language = SOURCE_EXTENSIONS.get(Path(path).suffix.lower())
    if language is None:
        raise ConversionError(
            f"cannot infer source language from extension {Path(path).suffix or '(none)'!r}; use --from c, python, or javascript"
        )
    return language


def choose_output_path(source: Path, target: str, output: str | None = None,
                       output_dir: str | None = None, cwd: Path | None = None) -> Path:
    if output is not None and output_dir is not None:
        raise ConversionError("--output and --output-dir cannot be used together")
    if output is not None:
        result = Path(output).expanduser()
    elif output_dir is not None:
        result = Path(output_dir).expanduser() / (source.stem + TARGET_EXTENSIONS[target])
    else:
        result = (cwd or Path.cwd()) / (source.stem + TARGET_EXTENSIONS[target])
        # Same-language conversion must never default to replacing its input.
        if result.resolve() == source.resolve():
            result = result.with_name(source.stem + "_converted" + TARGET_EXTENSIONS[target])
    return result.absolute()


def convert_file(input_path: str | Path, target: str, *, source_language: str | None = None,
                 output: str | None = None, output_dir: str | None = None,
                 force: bool = False, check: bool = False,
                 cwd: Path | None = None) -> dict:
    source_path = Path(input_path).expanduser().absolute()
    if target not in LANGUAGES:
        raise ConversionError(f"unknown target language {target!r}; choose c, python, or javascript")
    language = source_language or infer_language(source_path)
    if language not in LANGUAGES:
        raise ConversionError(f"unknown source language {language!r}; choose c, python, or javascript")
    if not source_path.exists() or not source_path.is_file():
        raise ConversionError(f"input file does not exist or is not a regular file: {source_path}")
    destination = choose_output_path(source_path, target, output, output_dir, cwd)
    if destination.resolve() == source_path.resolve():
        raise ConversionError("output path is the input file; choose another path to protect the source")
    if destination.exists() and not force:
        raise ConversionError(f"output file already exists: {destination} (use --force to replace it)")
    try:
        source = source_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConversionError(f"input is not valid UTF-8 text: {source_path}") from exc
    try:
        generated = transpile_source(source, language, target)
    except CompileError:
        raise
    except (ValueError, TypeError) as exc:
        raise ConversionError(f"compiler failed: {exc}") from exc

    validation = None
    if check:
        validation = validate_generated(target, generated)
        if validation["status"] == "failed":
            raise ConversionError(
                f"generated {target} syntax check failed with {validation.get('tool', 'validator')}: {validation['message']}"
            )

    destination.parent.mkdir(parents=True, exist_ok=True) if output_dir is not None else None
    if not destination.parent.is_dir():
        raise ConversionError(f"output directory does not exist: {destination.parent}")
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=destination.parent,
                                         prefix=f".{destination.name}.", suffix=".tmp", delete=False) as stream:
            temp_name = stream.name
            stream.write(generated)
            stream.flush()
            os.fsync(stream.fileno())
        if destination.exists() and not force:
            raise ConversionError(f"output file already exists: {destination} (use --force to replace it)")
        os.replace(temp_name, destination)
    except Exception:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
        raise
    return {"source": source_path, "source_language": language, "target_language": target,
            "output": destination, "code": generated, "validation": validation}
