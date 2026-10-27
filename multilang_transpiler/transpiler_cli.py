"""Professional CLI for the 3x3 bidirectional transpiler (C, Python, JavaScript)."""
import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .parser import parse
from .semantic import analyze
from .ir import lower
from .codegen import generate
from .lexer import tokenize
from .errors import CompileError
from .validation import validate_generated
from .console import configure_console

LANG_MAP = {
    'c': 'c',
    'python': 'python',
    'py': 'python',
    'javascript': 'javascript',
    'js': 'javascript',
}

EXT_MAP = {
    '.c': 'c',
    '.h': 'c',
    '.py': 'python',
    '.pyw': 'python',
    '.js': 'javascript',
    '.mjs': 'javascript',
}


def detect_language(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in EXT_MAP:
        return EXT_MAP[ext]
    raise ValueError(f"Cannot automatically detect language from extension {ext!r}. Please specify --from.")


def normalize_target(target: str) -> str:
    t = target.lower().strip()
    if t in LANG_MAP:
        return LANG_MAP[t]
    raise ValueError(f"Unknown target language {target!r}. Choose from: c, python, js/javascript.")


def cmd_translate(args) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file {input_path} does not exist.", file=sys.stderr)
        return 1

    source_lang = LANG_MAP[args.source.lower()] if args.source else detect_language(input_path)
    target_lang = normalize_target(args.to)

    try:
        source_code = input_path.read_text(encoding='utf-8')
    except Exception as exc:
        print(f"Error reading {input_path}: {exc}", file=sys.stderr)
        return 1

    try:
        program = parse(source_code, source_lang)
        analyze(program, source_lang)
        ir_payload = lower(program)
        generated_code = generate(ir_payload, target_lang)
    except CompileError as ce:
        print(f"Compilation error ({ce.phase} on line {ce.line}): {ce}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error during transpilation: {exc}", file=sys.stderr)
        return 1

    out_file = args.output
    if out_file:
        out_path = Path(out_file)
        if out_path.exists() and not args.force:
            print(f"Error: output file {out_path} already exists. Use --force to overwrite.", file=sys.stderr)
            return 1
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(generated_code, encoding='utf-8')
            if getattr(args, 'verbose', False):
                print(f"[OK] Transpiled {source_lang.upper()} -> {target_lang.upper()}: {input_path} -> {out_path}")
            else:
                print(f"Successfully generated: {out_path}")
        except Exception as exc:
            print(f"Error writing to {out_path}: {exc}", file=sys.stderr)
            return 1
    else:
        # Output directly to stdout
        sys.stdout.write(generated_code)

    return 0


def cmd_inspect(args) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file {input_path} does not exist.", file=sys.stderr)
        return 1

    source_lang = LANG_MAP[args.source.lower()] if args.source else detect_language(input_path)
    source_code = input_path.read_text(encoding='utf-8')

    try:
        if args.tokens:
            tokens = tokenize(source_code, source_lang)
            print(json.dumps([t.__dict__ for t in tokens], indent=2))
            return 0

        program = parse(source_code, source_lang)
        analyze(program, source_lang)

        if args.ast:
            print(json.dumps(program, default=lambda x: x.__dict__, indent=2))
            return 0
        elif args.ir:
            print(json.dumps(lower(program), indent=2))
            return 0
        else:
            # Default inspect: show summary
            print(f"File: {input_path}")
            print(f"Detected Language: {source_lang.upper()}")
            print(f"Statements: {len(program.body)}")
            print(f"Use --ast, --ir, or --tokens to view detailed representations.")
            return 0
    except CompileError as ce:
        print(f"Compilation error ({ce.phase} on line {ce.line}): {ce}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error inspecting {input_path}: {exc}", file=sys.stderr)
        return 1


def cmd_check(args) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file {input_path} does not exist.", file=sys.stderr)
        return 1

    source_lang = LANG_MAP[args.source.lower()] if args.source else detect_language(input_path)
    source_code = input_path.read_text(encoding='utf-8')

    try:
        program = parse(source_code, source_lang)
        report = analyze(program, source_lang, detailed=True)
        print(f"[VALID] {input_path} ({source_lang.upper()}): Syntax and semantics passed.")
        if report and report.get('warnings'):
            for w in report['warnings']:
                print(f"  Warning: {w}")
        return 0
    except CompileError as ce:
        print(f"[INVALID] {input_path} ({source_lang.upper()}): {ce}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error checking {input_path}: {exc}", file=sys.stderr)
        return 1


def cmd_languages() -> int:
    print("MultiLang Bidirectional 3x3 Transpiler")
    print("Supported Languages:")
    print("  - C          (extensions: .c, .h)")
    print("  - Python     (extensions: .py, .pyw)")
    print("  - JavaScript (extensions: .js, .mjs)")
    print("\nSupported 3x3 Translation Routes (All 6 Directions):")
    print("  1. C          -> Python")
    print("  2. C          -> JavaScript")
    print("  3. Python     -> C")
    print("  4. Python     -> JavaScript")
    print("  5. JavaScript -> C")
    print("  6. JavaScript -> Python")
    print("\nFeatures:")
    print("  * Semantic logic preservation through unified Intermediate Representation (IR)")
    print("  * Pointers and dereferencing (*p, &x) <-> Reference abstractions (IntReference / {value})")
    print("  * Structs (typedef struct) <-> Classes / Dataclasses (@dataclass / constructor)")
    print("  * Companion function translation for instance methods")
    print("  * Import and standard library mappings (stdio, math, string, stdlib)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transpiler",
        description="MultiLang Transpiler: Robust 3x3 Bidirectional Transpiler (C, Python, JavaScript).",
    )
    parser.add_argument("--version", action="version", version=f"transpiler {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    # translate command
    trans_p = subparsers.add_parser("translate", help="Translate source file to target language")
    trans_p.add_argument("input", help="Source file path")
    trans_p.add_argument("--to", required=True, help="Target language: c, python/py, javascript/js")
    trans_p.add_argument("--from", dest="source", choices=['c', 'python', 'py', 'javascript', 'js'],
                         help="Source language (auto-detected if omitted)")
    trans_p.add_argument("-o", "--output", help="Output file path (prints to stdout if omitted)")
    trans_p.add_argument("--force", action="store_true", help="Overwrite output file if it exists")
    trans_p.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    # inspect command
    insp_p = subparsers.add_parser("inspect", help="Inspect AST, IR, or tokens of source file")
    insp_p.add_argument("input", help="Source file path")
    insp_p.add_argument("--from", dest="source", choices=['c', 'python', 'py', 'javascript', 'js'],
                        help="Source language (auto-detected if omitted)")
    insp_group = insp_p.add_mutually_exclusive_group()
    insp_group.add_argument("--ast", action="store_true", help="Display AST as JSON")
    insp_group.add_argument("--ir", action="store_true", help="Display IR as JSON")
    insp_group.add_argument("--tokens", action="store_true", help="Display tokens")

    # check command
    chk_p = subparsers.add_parser("check", help="Validate syntax and semantics of source file")
    chk_p.add_argument("input", help="Source file path")
    chk_p.add_argument("--from", dest="source", choices=['c', 'python', 'py', 'javascript', 'js'],
                       help="Source language (auto-detected if omitted)")

    # languages command
    subparsers.add_parser("languages", help="List supported languages and translation routes")

    return parser


def main(argv=None) -> int:
    configure_console()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "translate":
        return cmd_translate(args)
    elif args.command == "inspect":
        return cmd_inspect(args)
    elif args.command == "check":
        return cmd_check(args)
    elif args.command == "languages":
        return cmd_languages()

    return 0


if __name__ == "__main__":
    sys.exit(main())
