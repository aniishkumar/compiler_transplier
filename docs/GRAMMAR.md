# Supported grammar (v1 subset)

Notation: `*` means repetition; this grammar is intentionally smaller than any full language grammar. C and JavaScript statements use braces and optional semicolons. Both `//` and `/* ... */` comments are ignored. Python comment-only and blank lines do not change indentation. Python blocks use four-space indentation. Expressions use parentheses, names, numeric/string/boolean literals, unary `-`/`!`/`not`, calls and binary `+ - * / % == != < > <= >= && || and or`. Boolean operators are normalized per target.

```ebnf
program    = statement* ;
statement  = declaration | array-declaration | assignment | array-assignment | output | if | while | for | function | return | call ;
declaration= (int|float|double|char|bool|string|let|const|var) identifier ["=" expr] {"," identifier ["=" expr]} [";"] ;
assignment = identifier ("=" | "+=" | "-=" | "*=" | "/=") expr [";"] ;
call       = identifier "(" [expr {"," expr} [","]] ")" ;
array-declaration = type identifier "[" integer "]" "=" "{" [expr {"," expr}] "}" [";"] | identifier "=" "[" [expr {"," expr}] "]" ;
array-assignment = identifier "[" expr "]" "=" expr [";"] ;
output     = ("print" | "println" | "console.log") "(" [expr {"," expr} [","]] ")" | "printf" "(" string {"," expr} ")" ;
if         = "if" ["("] expr [")"] block [("elif" ["("] expr [")"] block | "else" ["if" ["("] expr [")"] block] block)] ;
while      = "while" ["("] expr [")"] block ;
for        = "for" "(" [type] identifier "=" expr ";" expr ";" identifier ("++" | "--" | ("+=" | "-=") expr) ")" block | "for" identifier "in" "range" "(" expr ["," expr] ")" block ;
function   = ["function"|"def"|return-type] identifier "(" [parameters] ")" block ;
return     = "return" [expr] [";"] ;
block      = "{" statement* "}" | ":" NEWLINE INDENT statement* DEDENT ;
expr       = literal | identifier | call | "(" expr ")" | unary expr | expr operator expr ;
```

`println(expr)` is an educational output alias accepted in all three source modes; it is not a standard C function. Comma-separated scalar declarations are supported. JavaScript `const` requires an initializer and cannot be reassigned. Unknown and duplicate function definitions, and calls with the wrong number of positional arguments, are rejected during semantic analysis. The parser rejects unsupported syntax instead of silently preserving it. Markdown code fences are rejected during preprocessing with a message asking the user to paste only source code. C `int main(void)` is accepted. Arrays are one-dimensional integer arrays with literal initializers and indexed access. C requires a literal fixed size; array bounds are not checked. Counted loops support C/JavaScript `for` and Python `range()` with one or two bounds and a positive unit step. Loop updates support increment/decrement and `+=`/`-=`. `printf` supports literal formats using `%d`, `%i`, `%f`, `%s`, `%c`, and `%%`, with matching argument counts and compatible inferred types. Flags, widths, dynamic format strings, and other conversions are rejected. Python and JavaScript output calls support comma-separated arguments with nested expressions; Python `sep`/`end` keyword options are not in the subset. Objects, pointers, classes, imports, exceptions, slicing, and dynamic/multidimensional arrays remain unsupported.
