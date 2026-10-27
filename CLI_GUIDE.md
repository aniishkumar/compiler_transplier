# MultiLang Transpiler CLI Guide

`multilang convert` is the primary CLI command. It converts one source file using the existing compiler pipeline and writes a target-language source file to disk. It does not start Flask, execute user code, or create a ZIP. The separate `multilang migrate` command remains available for users who explicitly need project-folder migration.

## What it does and does not do

- Uses the real compiler stages: preprocessing, tokenization, parsing, semantic analysis, IR lowering, code generation, and target syntax validation.
- Translates each eligible file independently. It is not a linker or whole-program module migrator.
- Does not execute input or generated programs. Migration reports always say runtime equivalence is **NOT TESTED**.
- Does not claim arbitrary C, Python, or JavaScript programs will translate. Only the subset in [docs/GRAMMAR.md](docs/GRAMMAR.md) is supported.

## Supported languages and file extensions

| Inferred language | Extensions | Targets |
|---|---|---|
| `c` | `.c`, `.h` | C, Python, JavaScript |
| `python` | `.py`, `.pyw` | C, Python, JavaScript |
| `javascript` | `.js`, `.mjs` | C, Python, JavaScript |

All nine language pairs are implemented by the shared compiler and exercised by the test suite. This does not mean every construct in the full languages is supported. JavaScript `.mjs` inputs infer JavaScript; generated output uses the standard `.js` extension.

## Installation

### Windows (PowerShell)

From the project root directory:

```powershell
python --version                 # Must be Python 3.10 or newer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .

# Test CLI
transpiler --help
multilang --help
```

### macOS and Linux

```sh
python3 --version                 # Must be Python 3.10 or newer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
multilang --help
transpiler --help
```

This builds and installs the CLI into the active virtual environment without administrator access. Flask is optional and is not required for file conversion. For the web dashboard, install `python -m pip install '.[dashboard]'` from the project directory.

## Commands

### 3×3 Transpiler CLI (`transpiler`)

PowerShell commands:
```powershell
# In PowerShell:
.\transpiler.bat translate samples\hello.c --to python
.\transpiler.bat translate samples\hello.py --to javascript
.\transpiler.bat translate samples\hello.js --to c
.\transpiler.bat translate main.c --to python -o output.py

# Inspect AST, IR, or tokens
.\transpiler.bat inspect samples\hello.c --ast
.\transpiler.bat inspect samples\hello.c --ir

# Validate syntax and semantics
.\transpiler.bat check samples\hello.c
.\transpiler.bat languages
.\transpiler.bat --version
```

### Multilang CLI (`multilang`)

```powershell
multilang --help
multilang --version
multilang languages
```

`languages` prints implemented source extensions and the three targets for each source language.

### Convert one file

```sh
multilang convert main.py --to javascript
multilang convert calculator.js --to c
multilang convert program.txt --from python --to javascript
```

When `--from` is omitted, the source language is inferred from `.c`, `.h`, `.py`, `.pyw`, `.js`, or `.mjs`. Unknown extensions require an explicit `--from`; the CLI never guesses. `--to` is required. Default output is the current working directory with the source stem and target extension: `calculator.py` becomes `calculator.js`. Same-language conversion that would collide with the input uses a `_converted` suffix to protect the source.

Choose an exact file or output directory with:

```sh
multilang convert main.py --to c --output ./build/translated.c
multilang convert main.py --to javascript --output-dir ./converted
```

`--output-dir` creates the directory when possible and keeps the source stem. An exact `--output` path requires its parent directory to exist. Existing output files are protected; add `--force` only when you intend to replace one. Filenames with spaces or Unicode are supported. Conversion writes atomically, so a failure does not leave a partial generated file.

Optional `--check` performs syntax-only validation using Python's AST parser, Node.js `--check`, or an installed C compiler. If a validator is unavailable, conversion succeeds and reports that validation was unavailable. The CLI never runs source or generated programs, so syntax validation is not proof of equivalent behavior.

Failures print an actionable message and return a nonzero status. Compiler diagnostics identify the phase and source line. Empty input follows the compiler's existing behavior and generates a newline-only output file.

### Migrate a project

```sh
multilang migrate ./my_project --from python --to javascript
```

By default the CLI creates `./my_project_migrated/` and `./my_project_migrated.zip`. If those names are already occupied, it chooses a free numbered name such as `my_project_migrated_2/`. It does not modify the source project.

### Choose output paths

```sh
multilang migrate ./my_project --from python --to c \
  --output ./build/migrated_project \
  --archive ./dist/migrated_project.zip
```

The output project and archive must be separate from the input project and from each other. Existing custom destinations cause an error unless the command includes `--overwrite`. With `--overwrite`, new content is staged first; existing destinations are moved aside and restored if finalization fails.

### Preview files

```sh
multilang migrate ./my_project --from python --to javascript --dry-run
```

Dry-run lists candidate translations, resources to copy, exclusions, and unsupported source files. It does not create directories, output files, reports, or ZIP archives. It cannot check syntax because it does not run the compiler.

### Add project-specific exclusions

```sh
multilang migrate ./my_project --from python --to javascript \
  --exclude 'vendor/**' --exclude 'tests/fixtures/private/**'
```

Exclusion patterns are relative to the input project and can be repeated. Common generated/environment directories are excluded by default: Git metadata, virtual environments, `node_modules`, Python caches, test/type/lint caches, build outputs, coverage, and IDE directories. Common bytecode, editor swap, temporary, and `.env` files are also skipped; `.env.example` remains copyable. Symlink files and directories are skipped and are not followed.

## File handling rules

- Supported source extensions are translated and get the target extension while retaining their relative parent directories.
- Known programming-language extensions that do not match `--from` are listed as skipped. They are never copied unchanged as though migrated.
- Other regular files—such as images, data, documentation, and configuration—are copied with their relative paths.
- Dependency/build manifests are copied unchanged and listed in the report; the CLI does not invent target-language dependency files.
- Root `README.md` is replaced with generated migration guidance. Its original content is retained as `README.original.md` (or a numbered variant if that name already exists).
- Filename collisions are resolved by retaining the source extension in the generated name, for example `common.c.js` and `common.h.js`.
- The input project is never used as the output. Destination paths that overlap the input are rejected.

## Migration report and statuses

Each completed output includes `migration-report.md`. It records the source project name (not its absolute path), language pair, UTC time, discovered/translated/skipped/failed/copied counts, file lists, compiler phase errors, validation results, ignored directories, and manual follow-up steps.

- **SUCCESS:** all discovered eligible source files translated and passed syntax validation; no unsupported source files were skipped.
- **PARTIAL SUCCESS:** at least one source file translated, but another source was skipped/failed or a validator was unavailable.
- **FAILED:** no source file translated, or a fatal operation failed. When per-file errors occur, the CLI still packages a report if it can do so safely.
- **NOT VALIDATED:** a file translated, but its target syntax checker was unavailable. This appears as that file's validation status and makes the overall result partial.
- **SKIPPED:** a file was excluded or has a known source-code extension not enabled for the selected source language.

Exit codes: `0` for SUCCESS, `1` for PARTIAL SUCCESS or FAILED migration result, `2` for invalid arguments, paths, destination conflicts, or fatal packaging errors. Argparse handles invalid command syntax with its standard nonzero code.

## Validation and runtime behavior

Validation is syntax-only: Python uses the Python AST parser, JavaScript uses `node --check`, and C uses `cc`, `clang`, or `gcc` with `-fsyntax-only`. If a validator is absent, the report says NOT VALIDATED. No source or generated project program is run by the CLI.

The existing compiler's tests include controlled runtime comparisons for checked-in regression fixtures. Those tests do not prove runtime equivalence for a user's arbitrary migrated project. Run the target project's own tests manually in a safe environment.

## Multi-file and dependency limitations

The compiler parses each file independently and does not resolve imports, translate module references, share declarations between files, resolve user headers, or link multiple translation units. For example, a C `#include "local.h"` is rejected by the existing preprocessor. A Python package with imports may be only partially migrated even when some individual files translate.

Report failures by file and phase. Review all skipped and failed items, update manifests, resolve dependencies and linking manually, and run target-language tests before treating the result as a usable project.

## Complete example

The repository contains `examples/demo_project/`, a small import-free Python project with a text asset. From the repository root:

```sh
multilang migrate examples/demo_project --from python --to javascript
```

This creates `examples/demo_project_migrated/` plus `examples/demo_project_migrated.zip`, containing the generated `.js` file, copied data resource, generated README, and migration report. Confirm the actual results in the report; this checked-in demo does not execute source or generated code.

## Troubleshooting

- **`multilang: command not found`:** activate the virtual environment where `python -m pip install .` was run. Alternatively run `python -m multilang_transpiler.project_cli ...` from the CLI project directory.
- **`Output already exists`:** choose a new `--output`/`--archive`, remove the old generated result yourself, or pass `--overwrite` after checking those destinations.
- **No source files for selected language:** check `--from` and ensure the project contains one of its listed extensions.
- **Skipped source extension:** the file appears to be code but is not part of the selected source language's supported extension set.
- **Compiler error:** inspect the source file and reported phase/line. Confirm the construct is in [docs/GRAMMAR.md](docs/GRAMMAR.md).
- **NOT VALIDATED:** install the relevant target checker on PATH: Node.js for JavaScript or a C compiler for C. Python syntax validation is built into Python.
- **Different behavior:** inspect language-specific type, division, truthiness, coercion, and formatting semantics; runtime equivalence is not tested by project migration.

## Run tests

Install the optional dashboard extra to run the entire repository suite, then:

```sh
python -m pip install '.[dashboard]'
python -m unittest discover -s tests -v
```

The CLI tests use temporary fixture projects and include all nine source-target combinations, file/path handling, error reporting, destination safety, dry-run, ZIP integrity, and failure cleanup. They never alter a real project.
