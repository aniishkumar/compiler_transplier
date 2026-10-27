"""The `multilang` command for safe project-level migration."""
import argparse
from pathlib import Path
import sys

from . import __version__
from .project_migration import LANGUAGES, MigrationError, SOURCE_EXTENSIONS, migrate_project
from .file_conversion import ConversionError, DISPLAY_NAMES, convert_file
from .errors import CompileError
from .console import configure_console


def _language_matrix() -> str:
    names = {"c": "C", "python": "Python", "javascript": "JavaScript"}
    rows = ["Supported languages and routes:"]
    for source in LANGUAGES:
        targets = ", ".join(names[target] for target in LANGUAGES)
        extensions = ", ".join(sorted(SOURCE_EXTENSIONS[source]))
        rows.append(f"  {names[source]:<12} → {targets} (source extensions: {extensions})")
    rows.append("All nine routes use the compiler's documented shared subset.")
    return "\n".join(rows)


def _progress(message: str) -> None:
    stages = {
        "Discovering project files": "[1/5] Discovering project files...",
        "Translating source files through the compiler": "[2/5] Translating supported source files...",
        "Copying permitted non-source project files": "[3/5] Copying permitted project resources...",
        "Validating generated source syntax": "[4/5] Validating generated files...",
        "Creating and verifying ZIP archive": "[5/5] Creating and verifying ZIP archive...",
        "Finalizing output directory and archive": "Finalizing output...",
    }
    print(stages.get(message, message), flush=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="multilang",
        description="Convert a source file or migrate a project using the MultiLang Transpiler compiler.",
        epilog=("Examples:\n"
                "  multilang convert main.py --to javascript\n"
                "  multilang convert program.txt --from python --to c --output converted.c\n"
                "  multilang languages\n"
                "  multilang migrate ./my_project --from python --to javascript\n"
                "  multilang migrate ./my_project --from python --to c --output ./build/migrated --archive ./dist/migrated.zip\n"
                "  multilang migrate ./my_project --from javascript --to python --dry-run"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"multilang {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    convert = commands.add_parser("convert", help="convert one source file to another language")
    convert.add_argument("input", help="source file to convert")
    convert.add_argument("--from", dest="source", choices=LANGUAGES,
                         help="source language (inferred from .c, .h, .py, .pyw, .js, or .mjs when omitted)")
    convert.add_argument("--to", dest="target", required=True, choices=LANGUAGES, help="target language")
    outputs = convert.add_mutually_exclusive_group()
    outputs.add_argument("--output", help="exact output file path")
    outputs.add_argument("--output-dir", help="directory for the generated file (created if needed)")
    convert.add_argument("--force", action="store_true", help="replace an existing output file")
    convert.add_argument("--check", action="store_true", help="syntax-check generated code when a validator is available")

    commands.add_parser("languages", help="list implemented languages and conversion routes")

    migrate = commands.add_parser("migrate", help="translate supported source files in a project")
    migrate.add_argument("project", help="source project directory")
    migrate.add_argument("--from", dest="source", required=True, choices=LANGUAGES, help="source language")
    migrate.add_argument("--to", dest="target", required=True, choices=LANGUAGES, help="target language")
    migrate.add_argument("--output", help="separate output project directory; default is <project>_migrated")
    migrate.add_argument("--archive", help="ZIP archive path; default is next to the output directory")
    migrate.add_argument("--dry-run", action="store_true", help="list planned translations, copies, and skips without writing files")
    migrate.add_argument("--overwrite", action="store_true", help="replace an existing output directory/archive after staging succeeds")
    migrate.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                         help="add a relative glob exclusion (repeatable; common caches are excluded by default)")
    return parser


def _print_dry_run(result: dict) -> int:
    print("\nDry run — no output files or archive were created.")
    print(f"Source: {result['source']}")
    print(f"From: {result['source_language']}")
    print(f"To: {result['target_language']}")
    print(f"Planned project: {result['output']}")
    print("\nFiles to translate:")
    for source, target in result["translations"].items():
        print(f"  {source.as_posix()} → {target.as_posix()} (syntax not checked in dry-run)")
    print("\nNon-source files to copy:")
    for path in result["resources"]:
        print(f"  {path.as_posix()}")
    print("\nFiles to skip:")
    for item in result["skipped"]:
        print(f"  {item['path']} — {item['reason']}")
    for path in result["ignored_directories"]:
        print(f"  {path}/ — default/custom excluded directory")
    print(f"\nPlanned ZIP: {result['archive']}")
    return 0 if result["translations"] else 1


def _run_migration(args) -> int:
    project = Path(args.project).expanduser()
    print("MultiLang Transpiler — Project Migration")
    print(f"\nSource: {project}")
    print(f"From: {args.source}")
    print(f"To: {args.target}\n")
    result = migrate_project(
        project, args.source, args.target,
        output_dir=args.output, archive_path=args.archive,
        dry_run=args.dry_run, overwrite=args.overwrite,
        excludes=args.exclude, progress=_progress,
    )
    if args.dry_run:
        return _print_dry_run(result)

    print(f"\nMigration completed: {result['status']}")
    print(f"Files discovered: {result['discovered_count']}")
    print(f"Translated successfully: {len(result['translated'])}")
    print(f"Skipped: {len(result['skipped'])}")
    print(f"Failed: {len(result['failed'])}")
    print(f"Non-source files copied: {len(result['copied'])}")
    print(f"Project: {result['output']}/")
    print(f"Archive: {result['archive']}")
    print(f"Report: {result['output'] / 'migration-report.md'}")
    if result["failed"]:
        print("\nFailures:", file=sys.stderr)
        for item in result["failed"]:
            print(f"  {item['path']} [{item['phase']}] {item['message']}", file=sys.stderr)
    if result["skipped"]:
        print("\nSkipped files:", file=sys.stderr)
        for item in result["skipped"]:
            print(f"  {item['path']} — {item['reason']}", file=sys.stderr)
    if result["status"] != "SUCCESS":
        print("Runtime equivalence was not tested; review migration-report.md and run target tests manually.", file=sys.stderr)
    return 0 if result["status"] == "SUCCESS" else 1


def _run_conversion(args) -> int:
    result = convert_file(args.input, args.target, source_language=args.source,
                          output=args.output, output_dir=args.output_dir,
                          force=args.force, check=args.check)
    print("MultiLang Transpiler")
    print(f"\nSource: {result['source']}")
    print(f"Source language: {DISPLAY_NAMES[result['source_language']]}")
    print(f"Target language: {DISPLAY_NAMES[result['target_language']]}")
    print("\nConversion successful.")
    print(f"Output file: {result['output']}")
    if result["validation"]:
        state = result["validation"]
        print(f"Syntax check: {state['status'].upper()} — {state['message']}")
    return 0


def main(argv=None) -> int:
    configure_console()
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "languages":
        print(_language_matrix())
        return 0
    try:
        if args.command == "convert":
            return _run_conversion(args)
        return _run_migration(args)
    except CompileError as exc:
        print(f"multilang: {exc}", file=sys.stderr)
        return 1
    except ConversionError as exc:
        print(f"multilang: {exc}", file=sys.stderr)
        return 1
    except MigrationError as exc:
        print(f"multilang: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"multilang: filesystem operation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

