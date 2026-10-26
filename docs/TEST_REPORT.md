# Compiler and dashboard verification report

**Audit run:** 2026-10-25. Results below are from commands run against this checkout.

## Compiler tests

Command:

```sh
python3 -m unittest discover -s tests -p 'test_compiler.py' -v
```

**Result: 41 tests passed, 0 failed, 0 skipped** in 18.348 seconds on Python 3.13.7. The suite invokes the available Python interpreter, Node.js v25.6.0, and Apple clang 17.0.0 for runtime checks. It covers all nine routes, runtime output, loops, functions, arrays, formatted output, invalid syntax, semantic diagnostics, AST/semantic/IR payload separation, IR round-trip/legacy compatibility, wrong function arity, duplicate functions, and Markdown fence diagnostics.

## Nine-route syntax/runtime matrix

Command:

```sh
python3 tools/build_matrix_report.py
```

**Result: 9/9 passed, 0 failed, 0 unverified.** The script parsed each checked-in language regression, ran semantic analysis, lowered to IR, generated each target, syntax-checked generated code, compiled/executed the checked-in source and target, and compared stdout, stderr, and exit status. Available checkers were the Python parser, Node.js, and `cc` (Apple clang). See [CONVERSION_MATRIX.md](CONVERSION_MATRIX.md) for each observed route result and captured output.

## Additional static checks

These commands passed:

```sh
python3 -m py_compile multilang_transpiler/*.py webapp/*.py tests/*.py tools/*.py
node --check webapp/static/js/app.js
```

## Flask/dashboard test status

The project declares Flask in `requirements.txt`, but Flask is not installed in any of the available Python 3.11, 3.12, or 3.13 environments. The full discovery command:

```sh
python3 -m unittest discover -s tests -v
```

reported **42 discovered tests: 41 passed and one test-loader error** because `tests/test_webapp.py` could not import Flask (`ModuleNotFoundError: No module named 'flask'`). **The dashboard unittest cases were not executed.** No dependency was installed because the task prohibits adding packages without asking. The Flask routes and frontend were inspected statically, and a standard-library HTML structure check passed; the open browser tab showed a stale/different build (different defaults and fewer example options than this checkout), so it was not counted as an end-to-end verification of this checkout.

To run the Flask tests after setting up the project's own virtual environment, follow `README.md` and rerun the full discovery command. The browser UI never executes submitted source; the runtime checks above are confined to checked-in fixtures in temporary directories.
