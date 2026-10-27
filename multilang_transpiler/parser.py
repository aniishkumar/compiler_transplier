"""Parser for C, Python, and JavaScript subsets into unified AST nodes."""
from .ast_nodes import Expr, Stmt, Program
from .errors import CompileError
from .lexer import tokenize
from .preprocessor import preprocess


class Parser:
    def __init__(self, source, language):
        self.lang = language
        self.source = preprocess(source, language)
        self.ts = tokenize(self.source, language)
        self.i = 0
        self.struct_names = set()

    @property
    def t(self):
        return self.ts[self.i]

    def peek(self, offset=1):
        idx = self.i + offset
        if idx < len(self.ts):
            return self.ts[idx]
        return self.ts[-1]

    def take(self, v=None):
        t = self.t
        if v is not None and ((v in ('INDENT', 'DEDENT') and t.kind != v) or (v not in ('INDENT', 'DEDENT') and t.value != v)):
            raise CompileError(f"expected {v!r}, got {t.value!r}", t.line, 'syntax')
        self.i += 1
        return t

    def accept(self, v):
        if (self.t.kind == v if v in ('INDENT', 'DEDENT') else self.t.value == v):
            return self.take()
        return None

    def skipnl(self):
        while self.t.kind == 'NEWLINE' or self.t.value == ';':
            self.take()

    def program(self):
        body = []
        self.skipnl()
        while self.t.kind != 'EOF':
            body.append(self.stmt())
            self.skipnl()
        return Program(body, source_language=self.lang)

    def block(self):
        if self.lang == 'python':
            self.take(':')
            self.skipnl()
            self.take('INDENT')
            body = []
            while self.t.kind not in ('DEDENT', 'EOF'):
                if self.accept('pass'):
                    self.skipnl()
                    continue
                body.append(self.stmt())
                self.skipnl()
            self.accept('DEDENT')
            return body
        self.take('{')
        self.skipnl()
        body = []
        while self.t.value != '}' and self.t.kind != 'EOF':
            body.append(self.stmt())
            self.skipnl()
        self.take('}')
        return body

    def _array_decl(self, name, line, declared_type='int'):
        if declared_type not in ('int', 'let', 'const', 'var', 'char'):
            raise CompileError('only integer and char arrays are supported', line, 'syntax')
        self.take('[')
        size_tok = self.take()
        if size_tok.kind != 'NUMBER' or '.' in size_tok.value:
            raise CompileError('array size must be a non-negative integer literal', size_tok.line, 'syntax')
        size = int(size_tok.value)
        self.take(']')
        values = []
        if self.accept('='):
            if self.t.kind == 'STRING':
                s_tok = self.take()
                values = [Expr('char' if self.lang == 'c' else 'literal', ch, line=s_tok.line) for ch in s_tok.value.strip('"')]
            elif self.accept('{'):
                if self.t.value != '}':
                    while True:
                        values.append(self.expr())
                        if not self.accept(','):
                            break
                self.take('}')
        self.accept(';')
        if values and len(values) > size:
            raise CompileError('array initializer has more values than its declared size', line, 'syntax')
        return Stmt('array_decl', name, [Expr('array', size, values, line)], line=line, declared_type=declared_type)

    def parse_arguments(self, closing):
        args = []
        if self.t.value == closing:
            return args
        while True:
            args.append(self.expr())
            if not self.accept(','):
                break
            if self.t.value == closing:
                break
        return args

    def parse_field(self):
        t = self.t
        type_name = self.take().value
        while self.accept('*'):
            type_name += '*'
        while self.accept('*'):
            type_name += '*'
        field_name = self.take().value
        size = None
        if self.accept('['):
            size_tok = self.take()
            size = size_tok.value
            self.take(']')
        self.accept(';')
        field_type = f'{type_name}[{size}]' if size else type_name
        exprs = [Expr('literal', size, line=t.line)] if size else []
        return Stmt('field', field_name, exprs=exprs, line=t.line, declared_type=field_type)

    def parse_var_decl(self, name, declared_type='int'):
        t = self.t
        if self.t.value == '[':
            return self._array_decl(name, t.line, declared_type)
        exprs = []
        if self.accept('='):
            if self.accept('{'):
                args = []
                if self.t.value != '}':
                    while True:
                        args.append(self.expr())
                        if not self.accept(','):
                            break
                        if self.t.value == '}':
                            break
                self.take('}')
                clean_type = declared_type.replace('struct ', '').rstrip('*').strip()
                exprs = [Expr('construct', clean_type, args, line=t.line)]
            else:
                e = self.expr()
                exprs = [e]
        else:
            if declared_type == 'const' and self.lang == 'javascript':
                raise CompileError('const declarations require an initializer', t.line, 'syntax')
        self.accept(';')
        kind = 'array_decl' if exprs and exprs[0].kind == 'array' else 'decl'
        return Stmt(kind, name, exprs, line=t.line, declared_type=declared_type)

    def stmt(self):
        t = self.t
        v = t.value

        # Decorator (Python @dataclass)
        if v == '@':
            self.take('@')
            dec = self.take().value
            self.skipnl()
            s = self.stmt()
            s.declared_type = dec
            return s

        # Import statements
        if v in ('import', 'from'):
            if v == 'from':
                self.take('from')
                module = self.take().value
                self.take('import')
                items = []
                if self.accept('{'):
                    while self.t.value != '}':
                        items.append(Expr('name', self.take().value, line=t.line))
                        if not self.accept(','):
                            break
                    self.take('}')
                else:
                    while True:
                        items.append(Expr('name', self.take().value, line=t.line))
                        if not self.accept(','):
                            break
                self.accept(';')
                return Stmt('import', module, exprs=items, line=t.line)
            else:
                self.take('import')
                if self.t.kind == 'STRING':
                    module = self.take().value.strip('"\'')
                    self.accept(';')
                    return Stmt('import', module, line=t.line)
                if self.accept('{'):
                    items = []
                    while self.t.value != '}':
                        items.append(Expr('name', self.take().value, line=t.line))
                        if not self.accept(','):
                            break
                    self.take('}')
                    self.take('from')
                    module = self.take().value.strip('"\'')
                    self.accept(';')
                    return Stmt('import', module, exprs=items, line=t.line)
                name = self.take().value
                if self.accept('from'):
                    module = self.take().value.strip('"\'')
                    self.accept(';')
                    return Stmt('import', module, exprs=[Expr('name', name, line=t.line)], line=t.line)
                alias = None
                if self.accept('as'):
                    alias = self.take().value
                self.accept(';')
                return Stmt('import', name, line=t.line, declared_type=alias)

        # Typedef struct in C
        if v == 'typedef':
            self.take('typedef')
            self.take('struct')
            if self.t.kind == 'IDENT':
                self.take()  # optional tag
            self.take('{')
            self.skipnl()
            fields = []
            while self.t.value != '}' and self.t.kind != 'EOF':
                fields.append(self.parse_field())
                self.skipnl()
            self.take('}')
            name = self.take().value
            self.struct_names.add(name)
            self.accept(';')
            return Stmt('struct', name, exprs=fields, line=t.line)

        # Struct definition or struct variable declaration in C
        if v == 'struct':
            self.take('struct')
            name = self.take().value
            if self.t.value == '{':
                self.take('{')
                self.skipnl()
                fields = []
                while self.t.value != '}' and self.t.kind != 'EOF':
                    fields.append(self.parse_field())
                    self.skipnl()
                self.take('}')
                self.struct_names.add(name)
                self.accept(';')
                return Stmt('struct', name, exprs=fields, line=t.line)
            else:
                decl_type = f'struct {name}'
                while self.accept('*'):
                    decl_type += '*'
                var_name = self.take().value
                return self.parse_var_decl(var_name, declared_type=decl_type)

        # Class definition in Python or JS
        if v == 'class':
            self.take('class')
            name = self.take().value
            self.struct_names.add(name)
            if self.accept('('):
                self.take()  # base class
                self.take(')')
            elif self.accept('extends'):
                self.take()  # base class
            fields = []
            methods = []
            if self.lang == 'python':
                self.take(':')
                self.skipnl()
                self.take('INDENT')
                while self.t.kind not in ('DEDENT', 'EOF'):
                    if self.accept('pass'):
                        self.skipnl()
                        continue
                    if self.t.value == 'def':
                        m = self.stmt()
                        if m.value == '__init__':
                            for s in m.body:
                                if s.kind == 'member_assign' and s.exprs[0].kind == 'name' and s.exprs[0].value == 'self':
                                    if not any(f.value == s.value for f in fields):
                                        fields.append(Stmt('field', s.value, line=s.line))
                            init_params = [p for p in m.exprs[0].children if p != 'self']
                            for p in init_params:
                                if not any(f.value == p for f in fields):
                                    fields.append(Stmt('field', p, line=m.line))
                        else:
                            methods.append(m)
                    elif self.t.kind == 'IDENT':
                        fname = self.take().value
                        ftype = None
                        if self.accept(':'):
                            ftype = self.take().value
                        default_val = None
                        if self.accept('='):
                            default_val = self.expr()
                        self.skipnl()
                        fields.append(Stmt('field', fname, exprs=[default_val] if default_val else [], line=t.line, declared_type=ftype))
                    else:
                        self.stmt()
                    self.skipnl()
                self.accept('DEDENT')
            else:
                self.take('{')
                self.skipnl()
                while self.t.value != '}' and self.t.kind != 'EOF':
                    m_name = self.take().value
                    self.take('(')
                    m_params = []
                    while self.t.value != ')':
                        m_params.append(self.take().value)
                        if not self.accept(','):
                            break
                    self.take(')')
                    m_body = self.block()
                    if m_name == 'constructor':
                        for s in m_body:
                            if s.kind == 'member_assign' and s.exprs[0].kind == 'name' and s.exprs[0].value == 'this':
                                if not any(f.value == s.value for f in fields):
                                    fields.append(Stmt('field', s.value, line=s.line))
                        for p in m_params:
                            if not any(f.value == p for f in fields):
                                fields.append(Stmt('field', p, line=t.line))
                    else:
                        methods.append(Stmt('function', m_name, [Expr('params', value=[], children=m_params, line=t.line)], m_body, line=t.line))
                    self.skipnl()
                self.take('}')
            return Stmt('class', name, exprs=fields, body=methods, line=t.line)

        # Functions
        is_c_func = False
        if v in ('int', 'void', 'float', 'double', 'char', 'bool', 'string') or v in self.struct_names:
            offset = 1
            while self.peek(offset).value == '*':
                offset += 1
            if self.peek(offset).kind == 'IDENT' and self.peek(offset + 1).value == '(':
                is_c_func = True

        if v in ('def', 'function') or is_c_func:
            return_type = None
            if is_c_func:
                return_type = self.take().value
                while self.accept('*'):
                    return_type += '*'
            else:
                self.take()
            name = self.take().value
            self.take('(')
            params = []
            param_types = []
            while self.t.value != ')':
                if self.t.value == 'void' and self.peek(1).value == ')':
                    self.take()
                    break
                p_type = None
                if self.t.kind in ('IDENT', 'KEYWORD') and (self.t.value in ('int', 'float', 'double', 'string', 'char', 'bool', 'void') or self.t.value in self.struct_names):
                    p_type = self.take().value
                    while self.accept('*'):
                        p_type += '*'
                while self.accept('*'):
                    p_type = (p_type or 'void') + '*'
                p_name = self.take().value
                params.append(p_name)
                param_types.append(p_type)
                if not self.accept(','):
                    break
            self.take(')')
            body = self.block()
            return Stmt('function', name, [Expr('params', value=param_types, children=params, line=t.line)], body, line=t.line, declared_type=return_type)

        # Pointer deref assignments: *p = 20; (*p)++; (*p) += 1;
        if v == '*':
            self.take('*')
            target = self.expr(minp=6)
            op = self.take().value
            if op not in ('=', '+=', '-=', '*=', '/='):
                raise CompileError('expected assignment after dereference', t.line, 'syntax')
            rhs = self.expr()
            self.accept(';')
            return Stmt('deref_assign', op, exprs=[target, rhs], line=t.line)

        if v == '(' and self.peek(1).value == '*':
            self.take('(')
            self.take('*')
            target = Expr('name', self.take().value, line=t.line)
            self.take(')')
            if self.t.value in ('++', '--'):
                up_op = self.take().value
                self.accept(';')
                amount = Expr('literal', '1', line=t.line)
                return Stmt('deref_assign', '+=' if up_op == '++' else '-=', exprs=[target, amount], line=t.line)
            op = self.take().value
            if op in ('=', '+=', '-=', '*=', '/='):
                rhs = self.expr()
                self.accept(';')
                return Stmt('deref_assign', op, exprs=[target, rhs], line=t.line)

        # Declarations of primitives, pointers, and user-defined struct variables
        is_type_decl = v in ('int', 'float', 'double', 'char', 'bool', 'string', 'let', 'const', 'var') or v in self.struct_names
        if is_type_decl and not (self.peek(1).value == '('):
            declared_type = self.take().value
            while self.accept('*'):
                declared_type += '*'
            declarations = []
            while True:
                while self.accept('*'):
                    declared_type += '*'
                name = self.take().value
                if self.t.value == '[':
                    if declarations:
                        raise CompileError('array declarations cannot be combined with other declarators', t.line, 'syntax')
                    return self._array_decl(name, t.line, declared_type)
                exprs = []
                if self.accept('='):
                    if self.accept('{'):
                        args = []
                        if self.t.value != '}':
                            while True:
                                args.append(self.expr())
                                if not self.accept(','):
                                    break
                                if self.t.value == '}':
                                    break
                        self.take('}')
                        clean_type = declared_type.rstrip('*').strip()
                        e = Expr('construct', clean_type, args, line=t.line)
                    else:
                        e = self.expr()
                    exprs = [e]
                    kind = 'array_decl' if e.kind == 'array' else 'decl'
                else:
                    if declared_type == 'const' and self.lang == 'javascript':
                        raise CompileError('const declarations require an initializer', t.line, 'syntax')
                    kind = 'decl'
                declarations.append(Stmt(kind, name, exprs, line=t.line, declared_type=declared_type))
                if not self.accept(','):
                    break
            self.accept(';')
            return declarations[0] if len(declarations) == 1 else Stmt('group', body=declarations, line=t.line)

        if v == 'for':
            if self.lang == 'python':
                return self.python_for()
            return self.for_stmt()

        if v in ('print', 'println', 'console'):
            self.take()
            style = 'println' if v == 'println' else ('console.log' if v == 'console' else 'print')
            if v == 'console':
                self.take('.')
                self.take('log')
            self.take('(')
            args = self.parse_arguments(')')
            self.take(')')
            self.accept(';')
            return Stmt('print', value=style, exprs=args, line=t.line)

        if v == 'printf':
            self.take()
            self.take('(')
            if self.t.value == ')':
                raise CompileError('printf requires a format string argument', t.line, 'syntax')
            fmt = self.take()
            if fmt.kind != 'STRING':
                raise CompileError('printf format must be a string literal', fmt.line, 'syntax')
            args = [Expr('literal', fmt.value, line=fmt.line)]
            if self.accept(','):
                if self.t.value == ')':
                    raise CompileError('printf has a trailing comma without an argument', self.t.line, 'syntax')
                args.extend(self.parse_arguments(')'))
            self.take(')')
            self.accept(';')
            return Stmt('print', value='printf', exprs=args, line=t.line)

        if v in ('if', 'while'):
            self.take()
            par = bool(self.accept('('))
            cond = self.expr()
            if par:
                self.take(')')
            body = self.block()
            other = []
            if v == 'if':
                if self.lang != 'python':
                    self.skipnl()
                if self.accept('elif'):
                    elif_token = self.ts[self.i - 1]
                    elif_cond = self.expr()
                    elif_body = self.block()
                    nested = Stmt('if', exprs=[elif_cond], body=elif_body, line=elif_token.line)
                    other = [nested]
                    if self.lang != 'python':
                        self.skipnl()
                    if self.accept('else'):
                        nested.otherwise = self.block()
                elif self.accept('else'):
                    if self.t.value == 'if':
                        other = [self.stmt()]
                    else:
                        other = self.block()
            return Stmt(v, exprs=[cond], body=body, otherwise=other, line=t.line)

        if v == 'return':
            self.take()
            exprs = [] if self.t.value in (';', '}') or self.t.kind in ('NEWLINE', 'DEDENT', 'EOF') else [self.expr()]
            self.accept(';')
            return Stmt('return', exprs=exprs, line=t.line)

        # Identifiers, calls, assignments, member assignments
        if self.t.kind in ('IDENT', 'KEYWORD'):
            name = self.take().value
            left = Expr('name', name, line=t.line)

            # Check for member access or index
            while True:
                if self.t.value in ('.', '->'):
                    op = self.take().value
                    member = self.take().value
                    if self.accept('('):
                        args = self.parse_arguments(')')
                        self.take(')')
                        self.accept(';')
                        return Stmt('method_call', member, [left] + args, line=t.line)
                    left = Expr('member', member, [left], line=t.line)
                elif self.t.value == '[':
                    self.take()
                    idx = self.expr()
                    self.take(']')
                    if self.t.value in ('=', '+=', '-=', '*=', '/='):
                        op = self.take().value
                        rhs = self.expr()
                        self.accept(';')
                        if op != '=':
                            rhs = Expr('binary', op[0], [Expr('index', name, [idx], t.line), rhs], op.line)
                        return Stmt('array_assign', name, [idx, rhs], line=t.line)
                    left = Expr('index', left.value if left.kind == 'name' else left, [idx], line=t.line)
                else:
                    break

            if left.kind == 'member':
                if self.t.value in ('=', '+=', '-=', '*=', '/='):
                    op = self.take().value
                    rhs = self.expr()
                    self.accept(';')
                    return Stmt('member_assign', left.value, [left.children[0], rhs], line=t.line, declared_type=op)

            # Regular assignment
            op = self.t.value
            if op in ('=', '+=', '-=', '*=', '/='):
                self.take()
                rhs = self.expr()
                self.accept(';')
                return Stmt('assign' if op == '=' else 'compound_assign', name, [rhs] if op == '=' else [Expr('operator', op, line=t.line), rhs], line=t.line)

            if self.accept('('):
                args = self.parse_arguments(')')
                self.take(')')
                self.accept(';')
                return Stmt('call', name, args, line=t.line)

            raise CompileError('expected assignment or function call', t.line, 'syntax')

        raise CompileError(f"unsupported statement starting with {v!r}", t.line, 'syntax')

    def for_stmt(self):
        t = self.take('for')
        self.take('(')
        declared = self.t.value in ('int', 'float', 'double', 'let', 'const', 'var')
        if declared:
            self.take()
        name = self.take().value
        self.take('=')
        init = self.expr()
        self.take(';')
        cond = self.expr()
        self.take(';')
        step_name = self.take().value
        if self.t.value in ('++', '--'):
            op = self.take().value
            step = Expr('update', op, [Expr('name', step_name, line=t.line)], t.line)
        elif self.t.value in ('+=', '-='):
            op = self.take().value
            amount = self.expr()
            step = Expr('update', op, [Expr('name', step_name, line=t.line), amount], t.line)
        else:
            self.take('=')
            value = self.expr()
            step = Expr('update', '=', [Expr('name', step_name, line=t.line), value], t.line)
        if step_name != name:
            raise CompileError('for-loop initializer and update must use the same variable', t.line, 'syntax')
        self.take(')')
        body = self.block()
        return Stmt('for', name, [Expr('for_init', declared, [init], t.line), cond, step], body, line=t.line)

    def python_for(self):
        self.take('for')
        t = self.take()
        name = t.value
        self.take('in')
        self.take('range')
        self.take('(')
        args = []
        if self.t.value != ')':
            while True:
                args.append(self.expr())
                if not self.accept(','):
                    break
        self.take(')')
        if len(args) == 1:
            start = Expr('literal', '0', line=t.line)
            stop = args[0]
        elif len(args) == 2:
            start, stop = args
        else:
            raise CompileError('range() supports one or two arguments in this subset', t.line, 'syntax')
        body = self.block()
        return Stmt('for', name, [Expr('for_init', True, [start], t.line), Expr('binary', '<', [Expr('name', name, line=t.line), stop], t.line), Expr('update', '++', [Expr('name', name, line=t.line)], t.line)], body, line=t.line)

    def expr(self, minp=0):
        t = self.take()

        # Unary operators
        if t.value in ('-', '!', 'not'):
            left = Expr('unary', t.value, [self.expr(7)], t.line)
        elif t.value == '&':
            left = Expr('address_of', None, [self.expr(7)], t.line)
        elif t.value == '*':
            left = Expr('deref', None, [self.expr(7)], t.line)
        elif t.value == 'new':
            class_name = self.take().value
            self.take('(')
            args = self.parse_arguments(')')
            self.take(')')
            left = Expr('construct', class_name, args, t.line)
        elif t.value == '(':
            # Check for C cast e.g. (Student*) or (int)
            is_cast = False
            if self.lang == 'c' and self.t.kind in ('IDENT', 'KEYWORD'):
                peek_val = self.peek(1).value
                peek2_val = self.peek(2).value
                if peek_val == ')' or (peek_val == '*' and peek2_val == ')'):
                    is_cast = True
            if is_cast:
                cast_type = self.take().value
                while self.accept('*'):
                    cast_type += '*'
                self.take(')')
                operand = self.expr(minp=7)
                left = Expr('cast', cast_type, [operand], t.line)
            else:
                left = self.expr()
                self.take(')')
        elif t.value == '[':
            items = []
            if self.t.value != ']':
                while True:
                    items.append(self.expr())
                    if not self.accept(','):
                        break
            self.take(']')
            left = Expr('array', None, items, t.line)
        elif t.value == '{':
            # Object / Dict literal
            pairs = []
            if self.t.value != '}':
                while True:
                    k_tok = self.take()
                    key = k_tok.value.strip('"\'') if k_tok.kind in ('STRING', 'IDENT', 'KEYWORD') else k_tok.value
                    self.take(':')
                    v_expr = self.expr()
                    pairs.append(Expr('pair', key, [v_expr], k_tok.line))
                    if not self.accept(','):
                        break
                    if self.t.value == '}':
                        break
            self.take('}')
            left = Expr('dict', None, pairs, t.line)
        elif t.kind == 'NUMBER' or t.value in ('True', 'False', 'true', 'false', 'null', 'None', 'NULL'):
            val = t.value
            if val == 'NULL':
                val = 'null' if self.lang == 'javascript' else ('None' if self.lang == 'python' else 'NULL')
            left = Expr('literal', val, line=t.line)
        elif t.kind == 'STRING':
            left = Expr('char' if self.lang == 'c' and t.value.startswith("'") else 'literal', t.value, line=t.line)
        elif t.kind in ('IDENT', 'KEYWORD'):
            if self.accept('('):
                args = self.parse_arguments(')')
                self.take(')')
                # If identifier is a known struct / class name or PascalCase, treat as construct call in Python/C
                if t.value in self.struct_names or (t.value[0].isupper() and t.value not in ('True', 'False', 'None')):
                    left = Expr('construct', t.value, args, t.line)
                else:
                    left = Expr('call', t.value, args, t.line)
            else:
                left = Expr('name', t.value, line=t.line)
        else:
            raise CompileError(f"expected expression, got {t.value!r}", t.line, 'syntax')

        # Postfix operators: member access (.), pointer arrow (->), array index ([), postfix ++/--
        while True:
            if self.t.value in ('.', '->'):
                op = self.take().value
                member = self.take().value
                if self.accept('('):
                    args = self.parse_arguments(')')
                    self.take(')')
                    left = Expr('method_call', member, [left] + args, t.line)
                else:
                    left = Expr('member', member, [left], t.line)
            elif self.t.value == '[':
                self.take()
                index = self.expr()
                self.take(']')
                left = Expr('index', left.value if left.kind == 'name' else left, [index], t.line)
            elif self.t.value in ('++', '--'):
                op = self.take().value
                left = Expr('update', op, [left], t.line)
            else:
                break

        prec = {'or': 0, '||': 0, 'and': 1, '&&': 1, '==': 2, '!=': 2, '<': 2, '>': 2, '<=': 2, '>=': 2, '+': 3, '-': 3, '*': 4, '/': 4, '%': 4}
        while self.t.value in prec and prec[self.t.value] >= minp:
            op = self.take()
            p = prec[op.value]
            right = self.expr(p + 1)
            left = Expr('binary', op.value, [left, right], op.line)
        return left


def parse(source, language):
    if language not in ('c', 'python', 'javascript'):
        raise CompileError(f'unknown language {language!r}')
    return Parser(source, language).program()
