# MultiLang Transpiler

An educational source-to-source compiler for a documented common subset of C, Python, and JavaScript. Its `multilang convert` command converts one file at a time through the shared tokenizer, parser, semantic checks, IR, and target generators. An optional `multilang migrate` command handles project folders separately. The local Flask dashboard remains available, and conversion never executes user programs.

## Setup (macOS and Linux)

```sh
cd multilang_transpiler
python3 --version                 # Python 3.10+
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
```

The CLI has no third-party runtime dependencies. To run the optional dashboard, install Flask with `python -m pip install '.[dashboard]'` (or `python -m pip install -r requirements.txt`).

For generated-code validation, install a C compiler (`clang` or `gcc`) and Node.js. On macOS, `xcode-select --install` provides clang. On Debian/Ubuntu, install the C toolchain with `sudo apt install build-essential`; install Node.js with your preferred package manager.

## Run

```sh
multilang --help
multilang convert samples/hello.py --to javascript
multilang convert samples/hello.py --to c --output ./build/hello.c
multilang convert program.txt --from python --to javascript --check
multilang languages
# Optional project migration:
multilang migrate ./my_project --from python --to javascript
multilang migrate ./my_project --from python --to javascript --dry-run

# Existing one-file compiler command remains available:
multilang-transpiler --from python --to javascript --input samples/hello.py --output /tmp/hello.js
python -m multilang_transpiler --from javascript --to c --input samples/hello.js --output /tmp/hello.c --dump ir
```

Single-file conversion writes `<source-stem>.<target-extension>` in the current directory, or the selected path/directory. It never silently replaces an existing output; use `--force` deliberately. Project migration, when explicitly selected, writes a separate project folder and ZIP. See [CLI_GUIDE.md](CLI_GUIDE.md) for installation, usage, validation, migration details, and limitations.

The CLI does not execute the input or generated program. Review generated code before running it. `--dump tokens`, `--dump ast`, and `--dump ir` write diagnostics to stderr; output source goes to the requested file.

## Start the dashboard on macOS

Install the optional dashboard dependency first, then run from the project directory with the virtual environment active:

```sh
python -m pip install '.[dashboard]'
python -m webapp.app
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). The server binds to localhost only. The browser app uses the built-in editor with syntax coloring and does not load third-party scripts.

## Tests

```sh
python -m unittest discover -s tests -v
```

The complete suite includes dashboard tests, so install the optional dashboard extra before running it: `python -m pip install '.[dashboard]'`.

Tests cover the supplied regression programs through all nine routes, array conversions, false branches, output argument parsing, type diagnostics, and Flask/API behavior. The [test report](docs/TEST_REPORT.md) records the actual suite result. Run `python tools/build_matrix_report.py` to regenerate the actual syntax/runtime results in [the conversion matrix report](docs/CONVERSION_MATRIX.md). Syntax validation alone does not prove runtime equivalence. Runtime checks execute only the checked-in regression programs; dashboard submissions are never executed. Dashboard tests validate generated syntax when possible; no user or generated programs are executed by API endpoints.

## Feature support

| Construct | Parser/generator status | Limits |
|---|---|---|
| Declarations and assignment | Implemented for the subset | C declarations preserve supported scalar types. Python/JavaScript values are inferred for C output; unknown or changing types are rejected with diagnostics instead of assumed to be integers. |
| Arithmetic, comparisons, Boolean operators | Implemented | Integer division and truthiness can differ across languages; Python `and`/`or` and C/JS `&&`/`||` are normalized. |
| Output (`print`, `println`, `console.log`, simple `printf`) | Implemented | Python and JavaScript default multi-argument output is preserved. C `printf` supports `%d`, `%i`, `%f`, `%s`, `%c`, `%%` and matching argument types; widths, flags, dynamic formats and other conversions are rejected. |
| If/else, `elif`/`else if`, and while | Implemented | No `do`, `switch`, or loop control statements. |
| Counted loops | Implemented | C/JavaScript `for` loops and Python `range()` with one or two bounds; positive unit step only for Python. |
| One-dimensional arrays | Implemented | Integer arrays with literal initializer/list and indexed reads/writes; fixed size for C. No multidimensional, slicing, dynamic allocation, or bounds checks. |
| Compound assignment and increment | Implemented | `+=`, `-=`, `*=`, `/=`, `++`, and `--` in the counted loop update; array compound assignment is accepted. |
| Functions and return | Implemented for typed/inferable scalar functions | C parameters and returns use declared or inferred scalar types. Unknown C-target parameter/return types are diagnosed. No overloads or full type/scope checking. |
| Comments and common C declarations | Implemented | C/JavaScript line and block comments; C `main(void)` and common comma-separated scalar declarations. |
| Lexical/syntax/name errors | Implemented | Diagnostics include phase and line. |
| Structs/classes, imports, pointers, exceptions, comprehensions, slicing | Unsupported | Rejected by parser or outside analyzed grammar. |

Although all nine source/target pairs use the same pipeline, source constructs must belong to the grammar in `docs/GRAMMAR.md`. This is not a complete C, Python, or ECMAScript compiler. C/Python/JavaScript differences (integer division, booleans, coercion, evaluation order, string formatting, types) mean behaviour is only preserved for compatible uses of the subset.

## Demo in VS Code

Open this folder in VS Code (`code .`), activate the venv, install `requirements.txt`, then start the dashboard using the command above. Load a sample, inspect the compiler pipeline and its readable AST, semantic report, and operation-based IR, then select **Run 3 × 3 checks**. See [the dashboard guide](docs/DASHBOARD.md) and [demo walkthrough](docs/DEMO.md). CLI diagnostics remain available with `--dump tokens`, `--dump ast`, and `--dump ir`.

## Dashboard API

See [API.md](docs/API.md) for request/response details. The key endpoints are `GET /api/health`, `GET /api/examples`, `POST /api/transpile`, `POST /api/test-conversion`, and `POST /api/test-matrix`.

## Troubleshooting

- **`No module named multilang_transpiler`**: run from this directory or execute `python -m pip install .` in the activated venv.
- **Unexpected character / syntax error**: check the documented grammar; diagnostics report source line.
- **Undeclared variable**: a name must be assigned or declared before it is read. Python-style first assignment introduces the name; C and JavaScript require declarations in this subset.
- **Generated C type diagnostic**: C output uses declared source types or infers supported scalar types from initial values and call sites. If the type is ambiguous or changes incompatibly, the compiler reports an error rather than guessing.
- **Different output**: check integer division, Boolean formatting, and the supported `printf` specifiers. The compiler preserves behavior for the documented common subset, not every rule in the three full languages.
