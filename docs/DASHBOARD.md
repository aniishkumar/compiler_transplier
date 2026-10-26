# Dashboard user guide

## Start it

From the project root on macOS or Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m webapp.app
```

Open `http://127.0.0.1:5000`. The dashboard binds to loopback, so it is available on the local machine only.

Do not open `webapp/templates/index.html` from Finder or a `file://` URL. It is a Flask/Jinja template: `url_for('static', ...)` is resolved by Flask, so a direct file open cannot load the stylesheet or dashboard JavaScript. The root route renders the template and serves both static assets at `/static/...`.

## Use it in a demonstration

1. Choose a source and target language. All nine combinations are available.
2. Load an example, or paste source in the left editor. The example selector changes the source language to match the sample.
3. Press **Transpile Code** (or Ctrl/Cmd+Enter while in the source editor).
4. Review generated code in the target panel, copy it, or download a `.c`, `.py`, or `.js` file.
5. Click a pipeline phase to inspect its result and purpose. AST Construction shows a readable tree, Semantic Analysis shows supported checks and actual declarations/functions, and IR shows named operation instructions.
6. Use **Run 3 × 3 checks** to translate all nine committed regression examples and validate target syntax. Results appear in the live conversion notice; the dashboard does not execute the examples.

The dashboard editor is a lightweight, local syntax-colored textarea with line numbers; it does not depend on a remote Monaco/CodeMirror CDN. Swap Languages exchanges the two language selectors and keeps the source text intact. Clear Output removes the current generated code. Failed conversions discard old output so stale code is not presented as a new result. The separate Conversion Details section and its tabs were removed; phase outputs are inspected directly from the pipeline.

## Safety and what the tests mean

User input is size-limited to 50,000 characters, parsed by the constrained compiler grammar, and never run by Flask. Available target syntax checkers parse/compile generated code only (`ast.parse`, `node --check`, or C `-fsyntax-only`). The matrix panel reports translation and static syntax validation; it does not claim compilation or runtime equivalence. Runtime behavior tests remain in the local unittest suite and execute only the project's fixed test fixtures.

## Accessibility and responsive layout

The dashboard has labeled controls, keyboard focus indicators, live status announcements, Ctrl/Cmd+Enter submission, reduced-motion support, and responsive two-column/stacked editor layouts. Pipeline cards distinguish completed, warning, failed, pending, and not-run states.
