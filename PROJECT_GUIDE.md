# MultiLang Transpiler: Project and Dashboard Guide

This guide describes the code in this repository. It is an educational compiler for a deliberately limited, shared subset of C, Python, and JavaScript. It does not parse every legal program in any of those languages.

## 1. Purpose and features

The project translates a program from one supported source language into one of three target languages. All nine source/target combinations use one pipeline and a shared, language-neutral representation. The compiler can tokenize, parse, perform basic name/type checks, produce a structured AST and IR, generate target source, and validate target syntax when the relevant checker is installed.

Supported constructs include scalar declarations and assignments, integer/decimal/string/Boolean literals, arithmetic and comparisons, output, functions and returns, `if`/`else`/`elif`, `while`, a limited counted-loop form, and one-dimensional integer arrays. Exact constraints are in [docs/GRAMMAR.md](docs/GRAMMAR.md).

## 2. Folder structure

```text
multilang_transpiler 5/
├── README.md                    # Quick setup, usage, and feature overview
├── PROJECT_GUIDE.md             # This full walkthrough
├── pyproject.toml               # Python package metadata and CLI entry point
├── requirements.txt             # Flask runtime dependency
├── multilang_transpiler/        # Compiler library and command-line program
│   ├── __main__.py              # Enables python -m multilang_transpiler
│   ├── cli.py                   # CLI arguments, file I/O, optional phase dumps
│   ├── lexer.py                 # Token definitions and lexical analysis
│   ├── parser.py                # Recursive-descent parser and AST construction
│   ├── ast_nodes.py             # Expr, Stmt, Program dataclasses
│   ├── preprocessor.py          # Supported C include handling and fence diagnostic
│   ├── semantic.py              # Supported name/function/array/const checks and report
│   ├── ir.py                    # AST-to-operation-IR lowering and restoration
│   ├── codegen.py               # C, Python, and JavaScript generators
│   └── errors.py                # CompileError with phase and source line
├── webapp/
│   ├── app.py                   # Flask app factory and HTTP routes
│   ├── compiler_service.py      # Runs phases and returns JSON results
│   ├── templates/index.html     # Dashboard structure and controls
│   └── static/
│       ├── css/style.css        # Responsive layout and editor styling
│       └── js/app.js            # UI events, requests, and result rendering
├── samples/                     # C, Python, and JS examples and regressions
├── tests/                       # unittest compiler and Flask/API coverage
├── tools/build_matrix_report.py # Runs checked-in programs for route evidence
└── docs/                        # Grammar, API, architecture, demo, and reports
```

The implementation dependency is Python 3.10+ and Flask 3.x. The compiler modules use the Python standard library. C syntax/runtime checks use an installed C compiler; JavaScript checks use Node.js. The web app itself never executes submitted source.

## 3. Setup and run on macOS or Linux

From the project root (the folder containing `pyproject.toml`):

```sh
python3 --version                 # 3.10 or newer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
```

Start the dashboard:

```sh
python -m webapp.app
```

Open `http://127.0.0.1:5000/`. Stop the local server with Ctrl+C. The app binds to loopback. Do not open `webapp/templates/index.html` through `file://`; Flask must render it so its static asset URLs work.

To translate from the terminal:

```sh
multilang-transpiler --from python --to javascript \
  --input samples/hello.py --output /tmp/hello.js --dump tokens
```

The compiler does not run either file. Inspect generated code before executing it.

## 4. Architecture and data flow

```mermaid
flowchart LR
  U[Dashboard editor or CLI file] --> R[Flask route or CLI]
  R --> S[Compiler service]
  S --> P[Preprocessor]
  P --> L[Lexer: source text to tokens]
  L --> Q[Parser: tokens to AST]
  Q --> T[AST construction]
  T --> V[Semantic checks and symbol report]
  V --> I[IR: named operations]
  I --> G[Target code generator]
  G --> C[Generated source]
  C --> X[Static target syntax validation]
  X --> J[JSON phases, tokens, AST, IR, code, diagnostics]
  J --> D[Dashboard result panels]
```

The AST and IR are different structures. The AST uses parser-oriented node kinds such as `decl`, `binary`, and `print`; version 2 IR lowers them to named operations such as `DECLARE_VARIABLE`, `BINARY_OPERATION`, and `OUTPUT`. The generator's `restore()` adapter maps that operation structure back into existing compiler node objects so the three target generators remain reusable. Source-language metadata is retained where generation needs it to preserve behavior, such as C integer division and `main` handling. This is an operation-oriented educational IR, not machine code, SSA, or an optimizing three-address IR.

### Compiler phases

| Phase | What it does | Implementation | Completeness |
|---|---|---|---|
| Preprocessing | Removes a small set of supported C standard includes while preserving line positions; rejects unsupported directives and Markdown fences with a useful line diagnostic. | `multilang_transpiler/preprocessor.py`, `preprocess` | Partial by design; not a C preprocessor. |
| Lexical analysis | Scans source and emits positioned tokens for names, keywords, numbers, strings, operators, punctuation, and Python indentation. Skips comments. | `multilang_transpiler/lexer.py`, `tokenize`, `Token` | Implemented for grammar subset; columns are not currently retained. |
| Syntax analysis | Recursive-descent parser consumes tokens and applies operator precedence to expressions. It reports syntax errors with a line number. | `multilang_transpiler/parser.py`, `Parser.program`, `Parser.stmt`, `Parser.expr`, `parse` | Implemented for grammar subset, not a full language parser. |
| AST construction | Represents expressions/statements with typed node kinds and children/body lists. | `multilang_transpiler/ast_nodes.py`, `Expr`, `Stmt`, `Program` | Implemented tree structure. |
| Semantic analysis | Checks undeclared reads, invalid assignments, arrays, constants, unknown/duplicate functions, and function call arity. Detailed mode reports these checks, declarations with types when available, and function signatures. | `multilang_transpiler/semantic.py`, `analyze` | Partial semantic/type analysis; not full static typing or complete block-scope rules. |
| IR lowering | Lowers AST nodes to versioned, named operations and restores them for existing generators. | `multilang_transpiler/ir.py`, `lower`, `restore` | Operation-oriented IR; no optimization pass. |
| Code generation | Walks the shared tree and writes syntax for C, Python, or JavaScript. | `multilang_transpiler/codegen.py`, `generate`, `Generator` | Implemented for documented subset. |
| Target validation | Parses Python output or invokes Node/C compiler in syntax-only mode if present. | `webapp/compiler_service.py`, `_syntax_validate` | Optional static validation; not execution or equivalence proof. |

### Small example through the phases

Input in `samples/hello.py`:

```python
count = 2
print(count + 3)
```

Representative lexer tokens are `IDENT(count)`, `OP(=)`, `NUMBER(2)`, `KEYWORD(print)`, `IDENT(count)`, `OP(+)`, `NUMBER(3)`. The parser builds a `Program` containing an assignment and an output statement; the output expression is a binary `+` node with a name and numeric literal. In semantic analysis, the first Python assignment introduces `count` and its integer initializer gives the report an available inferred type. Lowering represents that normalized declaration as `DECLARE_VARIABLE`, then maps output to `OUTPUT` containing a `BINARY_OPERATION` with `READ_VARIABLE` and `CONSTANT` operands. The JavaScript generator produces:

```javascript
let count = 2;
console.log((count + 3));
```

Running this reviewed target with Node prints `5` plus a newline. `tools/build_matrix_report.py` and automated tests run only committed fixtures in temporary directories. Dashboard requests are never executed.

## 5. Dashboard walkthrough

The page is defined in `webapp/templates/index.html`, styled by `webapp/static/css/style.css`, and wired by `webapp/static/js/app.js`. The browser sends JSON to Flask; it does not implement a separate compiler.

| Visible area/control | Purpose and interaction | Implementation and data | Verification/limits |
|---|---|---|---|
| Brand/header and availability pill | Names the tool and shows whether `/api/health` responds. | Template header; `checkHealth()` requests `GET /api/health`. | API test exists. A green pill means the service responds, not that every language toolchain is installed. |
| Intro and **Run 3 × 3 checks** | Identifies the compiler workbench and requests the checked-in conversion matrix. | `runMatrix()` calls `POST /api/test-matrix`; server calls `run_matrix_checks()`. | The endpoint translates and syntax-checks committed sample programs; it explicitly does not execute programs. |
| Source and Target selectors | Pick source and output language. Changing either invalidates old results. | `<select>` controls and `change` listeners in `app.js`; values sent as `source_language` and `target_language`. | All three names are accepted by the compiler service. |
| Swap languages | Exchanges source/target selections, retains the source text, and clears stale result data. | `swap-languages` event handler. | Source text is not automatically translated when swapped. |
| Example selector and Load example | Loads a committed language-specific sample and updates the source selector/editor. | `GET /api/examples` reads files in `samples/`; `loadSelectedExample()` updates the editor. | API returns 15 samples (five example types × three languages) in this checkout. |
| Source code editor | Enter or paste raw code. Line numbers and simple syntax colors are a local overlay on a textarea. | Template textarea; `updateEditor`, `highlight`, and input listener in `app.js`. | This is not Monaco/CodeMirror and does not provide language-server completion. Markdown fences now produce a preprocessing diagnostic. |
| **Transpile Code** | Sends source text and language choices to the backend and displays conversion results. Ctrl/Cmd+Enter in the source editor also submits. | `transpile()` posts JSON to `POST /api/transpile`. | Backend parses; it never executes user code. Target syntax validation can be unavailable if Node/C compiler is missing. |
| Target program panel | Shows generated source. Copy and Download are enabled when usable generated code exists; Clear removes output. | Read-only output textarea; `copyCode()`, `downloadCode()`, clear handler. Download suffix is `.c`, `.py`, or `.js`. | A failed conversion clears the prior output to prevent stale code being mistaken for new output. |
| Notice and counts | Shows status/error text and source/output line and character counts. | `setNotice`, `updateEditor`, and `setConversion`. | Diagnostics contain phase and line, but parser does not currently preserve exact columns. |
| Compiler pipeline | Displays eight numbered phase cards with status and short purpose descriptions. | `renderPipeline`, `phaseDefinitions`; descriptions/statuses are returned by `compiler_service.transpile`. | Completed, warning, failed, pending, and not-run are distinct; the cards are not timing measurements. |
| Phase inspector | Shows phase number, name, purpose, and selected phase output. AST is a readable tree; semantic output shows checks/symbols/functions; IR shows named operations. | `selectPhase`, `renderPhaseOutput`, `astLines`, `semanticLines`, `irLines`. | Views are built from actual phase results; missing data falls back to readable text. |
| Conversion Details section | Removed from the dashboard, including its summary, tabs, result panel, and per-conversion test button. | Removed from `index.html` and exclusive handlers in `app.js`; backend diagnostic/test functionality remains. | `/api/test-conversion` and `/api/test-matrix` routes remain available. |
| Footer | Repeats the educational subset and safety boundary. | Template footer. | Accurate: server does not execute submitted programs. |

The layout has responsive breakpoints in `style.css`: the editors stack on narrow screens; the phase grid reduces from eight columns to four and then two. The inspector expands for readable trees and instructions without a separate Conversion Details panel. It includes keyboard focus treatment and reduced-motion styling. No remote frontend library or CDN is loaded.

### Backend routes

| Route | Behavior |
|---|---|
| `GET /` | Render the dashboard template. |
| `GET /api/health` | Report service availability, languages, and source size limit. |
| `GET /api/examples` | Return example code read from the committed sample files. |
| `POST /api/transpile` | Validate request fields, invoke real compiler phases, return JSON including generated code and diagnostics. |
| `POST /api/test-conversion` | Return translation and available syntax validation results; never execute code. |
| `POST /api/test-matrix` | Run nine translations of the checked-in regression inputs and report syntax validation; never execute code. |

`webapp/app.py` creates these routes and returns structured 400/413 errors for invalid requests. The 50,000-character limit is enforced in the request path and Flask body-size handler. See [docs/API.md](docs/API.md).

## 6. Supported languages and honest boundaries

The source and target set is C, Python, and JavaScript, and all nine pairs have compiler/runtime tests. Support means the documented grammar, not arbitrary files in these languages.

| Feature | Status | Key limitation |
|---|---|---|
| Scalar variables, assignment, arithmetic | Supported subset | C output needs an inferable/compatible scalar type; no general coercion model. |
| Output | Supported | C `printf` only literal formats `%d`, `%i`, `%f`, `%s`, `%c`, `%%`; no flags/widths or dynamic formats. Python `print` keyword options are not supported. |
| Comparisons and Boolean expressions | Supported subset | Truthiness and evaluation/coercion rules of full languages are not normalized. |
| `if`, `else`, `elif`/`else if`, `while` | Supported | `switch`, `do`, `break`, `continue` are not implemented. |
| Counted loops | Supported subset | C/JS counted form; Python `range` with one or two bounds and positive step 1 only. |
| Functions/returns/calls | Supported subset | No overloads, closures, default/keyword/variadic parameters, or full return-path/type checking. Call argument count is checked. |
| Arrays | Supported subset | One-dimensional integer arrays, literal initializers and indexed get/set; fixed C size, no bounds checks, multidimensional arrays or slicing. |
| Comments | Supported common forms | C/JS line/block and Python line comments. |
| Full language features | Unsupported | Imports, classes/objects, pointers, exceptions, comprehensions, templates, macros beyond accepted includes, and broad standard libraries are outside scope. |

Other semantic differences include integer division, booleans, string/character behavior, and C's static type system. The generators handle specific common cases and reject some uninferrable C output types; this is not a formal semantic-equivalence guarantee for arbitrary inputs.

## 7. Tests and current verification

Run the tests from the repository root:

```sh
python -m unittest discover -s tests -v
python tools/build_matrix_report.py
```

The unittest suite contains compiler runtime regressions plus Flask API tests. At the time this guide was updated, the compiler-only test file passed **41/41 tests**. The Flask tests could not be executed because Flask is not installed in the active Python environment. No package was installed because this task says not to add dependencies without asking. The generated matrix report separately runs the fixed regression sources and records real syntax/runtime results when C, Python, and Node are available. See [docs/CONVERSION_MATRIX.md](docs/CONVERSION_MATRIX.md) and [docs/TEST_REPORT.md](docs/TEST_REPORT.md) for the current evidence; regenerate the matrix after code changes.

The runtime matrix script is limited to repository-controlled regression fixtures and temporary files. It compares source and target stdout, stderr, and exit code. Never run arbitrary code pasted into the dashboard just to test conversion.

## 8. Troubleshooting

- **`No module named flask`**: activate the project virtual environment and run `python -m pip install -r requirements.txt`. This installs the declared project dependency into that venv; no OS package is needed.
- **`No module named multilang_transpiler`**: run from the project root or install the package with `python -m pip install -e .` in the active venv.
- **Unexpected backtick / Markdown error**: remove the opening and closing triple-backtick lines; paste only the code.
- **Unsupported statement or token**: compare the input to [docs/GRAMMAR.md](docs/GRAMMAR.md). This grammar intentionally excludes most of each full language.
- **Unknown function or wrong argument count**: define the function in the file and call it with its declared number of positional arguments.
- **C output type error**: use compatible, inferable scalar types. The compiler rejects ambiguous/incompatible values instead of silently treating everything as `int`.
- **No target validation**: Python parsing is built in; JavaScript validation needs Node, and C validation needs `cc`, Clang, or GCC. A missing checker is reported as unavailable and does not mean the generated code was validated.
- **Array output differs**: arrays have no bounds checks. Only initialized one-dimensional integer arrays and integer indexed assignments are in the supported subset.
- **Dashboard not loading**: start Flask from the project root and open `http://127.0.0.1:5000/`; don't open the template file directly.

## 9. Adding a language or feature

For a language addition, define source token/dialect rules in `lexer.py` and `parser.py`, preserve AST/IR nodes or extend `ast_nodes.py`/`ir.py` only when a distinct construct is needed, add a generator in `codegen.py`, add target syntax validation in `webapp/compiler_service.py`, register the language in `LANGUAGES`, and expose the selector/sample extension in the frontend/API. Add grammar documentation and fixtures.

For a feature, implement it end-to-end: tokenization, parser/AST representation, semantic validation, IR round-trip, all applicable generators, target validation/runtime tests, API behavior where relevant, and documentation. Add regression cases before claiming support. Avoid treating successful parsing as proof of correct generated behavior.

## 10. Faculty demonstration script

1. Start the dashboard and explain that the compiler translates only its documented subset.
2. Select Python → JavaScript and load **Arithmetic output (python)**.
3. Click **Transpile Code**. Show the generated program in the target panel.
4. Select Lexical Analysis, AST Construction, Semantic Analysis, Intermediate Representation, and Code Generation in the pipeline. Point out the AST node tree, semantic checks/symbols, and operation-based IR instructions in the inspector.
5. Load a function or array sample and show its source, generated form, and limitations.
6. Click **Run 3 × 3 checks**. Explain that this dashboard button performs translation and static syntax validation only; runtime equivalence is measured by the repository test suite/report using fixed sample programs.
7. To demonstrate real execution safely, use the checked-in `samples/hello.py` and review generated code before running the corresponding CLI-generated file with Node/Python/C compiler.
8. Paste malformed source or a function call with the wrong number of arguments to show a line-specific preprocessing, syntax, or semantic diagnostic.

The current default dashboard exposes all example types returned by `/api/examples`, including arrays; if the list appears shorter, reload the running server from this checkout and hard-refresh the browser to clear stale page assets.

## 11. Likely viva questions

**Why use an intermediate representation?** Each source parser and semantic pass lowers to the same operation vocabulary. Each target generator then consumes that common IR, avoiding a separate handwritten translation for every pair.

**Is this a complete C/Python/JavaScript compiler?** No. It is a source-to-source educational compiler for a small, documented common subset.

**What is the AST?** It is a tree of `Program`, `Stmt`, and `Expr` objects. For example, `count + 3` is a binary-expression node whose children represent a variable and a literal.

**What is the IR in this implementation?** It is version 2 operation-oriented IR with operations such as `DECLARE_VARIABLE` and `BINARY_OPERATION`, retaining source-language metadata where needed. It is not machine code and no optimization pass is currently implemented.

**What does semantic analysis check?** It checks variable use/declarations, arrays, constants, unknown/duplicate functions, and call argument counts. Type analysis is partial and some C target type inference happens in the generator.

**How is generated code tested?** Unit tests compile/run only committed test strings/samples in temporary paths. Dashboard validation invokes Python's parser, `node --check`, or C syntax-only compilation; it never runs dashboard input.

**What happens if the target runtime is unavailable?** Static syntax checking or runtime comparison is marked unavailable/not run. It is not counted as a pass.

**What remains unsupported?** See the feature table above and `docs/GRAMMAR.md`; examples include imports, pointers, classes, exceptions, multidimensional arrays, and Python `print` keyword options.

