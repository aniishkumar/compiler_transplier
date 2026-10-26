# Local API reference

The Flask API is intended for the local dashboard. JSON responses use UTF-8. The server binds to `127.0.0.1:5000` by default. Source programs are never executed.

## `GET /api/health`

Returns backend availability, supported language identifiers, and the source-character limit.

```json
{"available":true,"compiler":"MultiLang Transpiler","languages":["c","javascript","python"],"max_source_characters":50000}
```

## `GET /api/examples`

Returns the committed sample files as `{id, name, language, description, source_code}` objects.

## `POST /api/transpile`

Request:

```json
{"source_language":"python","target_language":"javascript","source_code":"count = 2\nprint(count + 3)"}
```

Identifiers are `c`, `python`, and `javascript`. `source_code` must be a string no longer than 50,000 characters. A successful response includes `success`, `generated_code`, `tokens`, `ast`, `ir`, `diagnostics`, `warnings`, and ordered `phases`. Each phase contains `id`, `name`, `status`, and `output`. Status is `completed`, `completed_with_warnings`, `failed`, or `not_reached`. On compile failure, `generated_code` is null and `error` includes category, phase, line, column (null where the compiler does not supply one), and message. Request validation errors use HTTP 400; oversized requests use HTTP 413; source compile errors are structured responses with HTTP 200 and `success: false`.

The eight phases report preprocessing, lexical analysis, syntax analysis, AST construction, semantic analysis, IR lowering, target generation, and target validation. Every phase includes a purpose description and an execution status. AST Construction returns an explanation, a source-line example, and the parsed AST tree. Semantic Analysis returns the actual supported checks, declarations with declared/literal-inferred types where available, function signatures, warnings, and checks not implemented. IR is version 2 operation-oriented data (`DECLARE_VARIABLE`, `BINARY_OPERATION`, `OUTPUT`, `BRANCH`, and related operations), distinct from the AST. Validation uses Python's parser, Node `--check`, or a C compiler's `-fsyntax-only` when available. Missing validators are surfaced as warnings; no program execution is performed.

## `POST /api/test-conversion`

Accepts the same JSON body as `/api/transpile`. Returns translation and available target syntax-check counts, individual check results, and an explicit statement that programs were not executed.

## `POST /api/test-matrix`

Runs the checked-in cross-language regression program through the nine source/target combinations and static target syntax checks. It returns `passed`, `failed`, named checks, and execution-safety information. This route does not launch the full unittest suite or execute example programs. For controlled runtime results, see `docs/CONVERSION_MATRIX.md`; regenerate them with `python tools/build_matrix_report.py`.

## Example request

```sh
curl -s http://127.0.0.1:5000/api/transpile \
  -H 'Content-Type: application/json' \
  -d '{"source_language":"python","target_language":"javascript","source_code":"count = 2\nprint(count + 3)"}'
```

## Error handling

Diagnostics have `category`, `phase`, `message`, `line`, and `column`. The current lexer/parser report line numbers; exact source columns are not available yet and are returned as null. Invalid inputs do not reuse results from earlier requests.
