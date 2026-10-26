# Cross-language conversion matrix report

Generated: 2026-10-25 18:14 UTC

This report was produced by `python tools/build_matrix_report.py`. It parses, analyzes, lowers through the shared IR, generates each target, syntax-checks it, and runs only the committed regression programs in temporary directories.

**Actual result: 9/9 passed, 0 failed, 0 unverified.**

| Source | Target | Test program | Parse | IR lowering | Code generation | Syntax validation | Runtime / compilation | Output equivalent | Status |
|---|---|---|---|---|---|---|---|---|---|
| c | c | Regression (c) | pass | pass | pass | passed (cc) | source passed; target passed | yes | **PASS** |
| c | python | Regression (c) | pass | pass | pass | passed (Python AST parser) | source passed; target passed | yes | **PASS** |
| c | javascript | Regression (c) | pass | pass | pass | passed (node) | source passed; target passed | yes | **PASS** |
| python | c | Regression (python) | pass | pass | pass | passed (cc) | source passed; target passed | yes | **PASS** |
| python | python | Regression (python) | pass | pass | pass | passed (Python AST parser) | source passed; target passed | yes | **PASS** |
| python | javascript | Regression (python) | pass | pass | pass | passed (node) | source passed; target passed | yes | **PASS** |
| javascript | c | Regression (javascript) | pass | pass | pass | passed (cc) | source passed; target passed | yes | **PASS** |
| javascript | python | Regression (javascript) | pass | pass | pass | passed (Python AST parser) | source passed; target passed | yes | **PASS** |
| javascript | javascript | Regression (javascript) | pass | pass | pass | passed (node) | source passed; target passed | yes | **PASS** |

## Captured runtime evidence

Stdout is shown with escaped newlines. Source and target exit codes and stderr are compared as well as stdout.

- **c → c (PASS):** source exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`; target exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`.
- **c → python (PASS):** source exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`; target exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`.
- **c → javascript (PASS):** source exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`; target exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`.
- **python → c (PASS):** source exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`; target exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`.
- **python → python (PASS):** source exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`; target exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`.
- **python → javascript (PASS):** source exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`; target exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`.
- **javascript → c (PASS):** source exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`; target exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`.
- **javascript → python (PASS):** source exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`; target exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`.
- **javascript → javascript (PASS):** source exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`; target exit 0; stdout `'Sum = 30\nGreater than 25\nProgram completed\n'`; stderr `''`.

## Regression output

Expected and observed output for each supplied language variant:

```text
Sum = 30
Greater than 25
Program completed
```

The dashboard itself never executes user-submitted programs. Runtime runs in this report are limited to the three checked-in regression files.
