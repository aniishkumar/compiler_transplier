# Reproducible demonstration

Start the web dashboard and open `http://127.0.0.1:5000`. Select Python → JavaScript, load “Arithmetic output (python)”, click **Transpile Code**, then select AST Construction, Semantic Analysis, and Intermediate Representation in the Compiler Pipeline. Their inspector results show the parsed AST tree, actual semantic checks and symbols, and named IR operations. The “Run 3 × 3 checks” control checks the committed regression program across all nine routes without executing programs.

The CLI walk-through below shows the same compiler pipeline with explicit token/AST/IR dumps.

Input (`samples/hello.py`):

```python
count = 2
print(count + 3)
```

Run the stages and then review and execute the generated JavaScript:

```sh
python -m multilang_transpiler --from python --to javascript --input samples/hello.py --output /tmp/hello.js --dump tokens
python -m multilang_transpiler --from python --to javascript --input samples/hello.py --output /tmp/hello.js --dump ast
python -m multilang_transpiler --from python --to javascript --input samples/hello.py --output /tmp/hello.js --dump ir
cat /tmp/hello.js
node /tmp/hello.js
```

Tokens (selected): `IDENT(count)`, `=(OP)`, `NUMBER(2)`, `KEYWORD(print)`, `IDENT(count)`, `+(OP)`, `NUMBER(3)`. Each token includes its source line in the CLI JSON dump.

AST and IR are structurally the same language-neutral tree. The declaration node is `decl(count, literal(2))`; the output node contains `binary(+, name(count), literal(3))`.

Generated JavaScript:

```javascript
let count = 2;
console.log((count + 3));
```

Observed execution result with Node.js 25.6.0 in the development environment: `5` followed by a newline. The compiler itself never executes input; this explicit demo command executes only the reviewed generated sample.
