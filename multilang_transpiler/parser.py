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
        self.classes_by_name = {}

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
        self.skipnl()
        if self.t.value == closing:
            return args
        while True:
            self.skipnl()
            if self.t.value == closing:
                break
            args.append(self.expr())
            self.skipnl()
            if not self.accept(','):
                break
            self.skipnl()
            if self.t.value == closing:
                break
        self.skipnl()
        return args

    def _extract_promise_val(self, node):
        if not hasattr(node, 'kind'):
            return None
        if node.kind == 'arrow_func':
            for child in node.children[1:]:
                res = self._find_resolve_arg(child)
                if res is not None:
                    return res
        return None

    def _find_resolve_arg(self, node):
        if not node:
            return None
        if hasattr(node, 'kind'):
            if node.kind == 'call' and getattr(node, 'value', '') == 'resolve':
                if getattr(node, 'children', []):
                    return node.children[0]
                if getattr(node, 'exprs', []):
                    return node.exprs[0]
            if getattr(node, 'kind', '') == 'method_call' and getattr(node, 'value', '') == 'resolve':
                return node.children[1] if len(node.children) > 1 else None
            for child in getattr(node, 'children', []):
                r = self._find_resolve_arg(child)
                if r is not None:
                    return r
            for e in getattr(node, 'exprs', []):
                r = self._find_resolve_arg(e)
                if r is not None:
                    return r
            for b in getattr(node, 'body', []):
                r = self._find_resolve_arg(b)
                if r is not None:
                    return r
        elif isinstance(node, list):
            for item in node:
                r = self._find_resolve_arg(item)
                if r is not None:
                    return r
        return None

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
            base_class = None
            if self.accept('('):
                if self.t.value != ')':
                    base_class = self.take().value
                self.take(')')
            elif self.accept('extends'):
                base_class = self.take().value
            fields = []
            methods = []
            if base_class and hasattr(self, 'classes_by_name') and base_class in self.classes_by_name:
                for f in self.classes_by_name[base_class].exprs:
                    if not any(ex.value == f.value for ex in fields):
                        fields.append(Stmt('field', f.value, exprs=list(f.exprs), line=f.line, declared_type=f.declared_type))
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
                    if m_name in ('get', 'set', 'async') and self.t.value != '(':
                        m_name = self.take().value
                    self.take('(')
                    m_params = []
                    while self.t.value != ')':
                        m_params.append(self.take().value)
                        if self.accept('='):
                            self.expr()
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
                            if not any(f.value in (p, f'_{p}') for f in fields):
                                fields.append(Stmt('field', p, line=t.line))
                    else:
                        methods.append(Stmt('function', m_name, [Expr('params', value=[], children=m_params, line=t.line)], m_body, line=t.line))
                    self.skipnl()
                self.take('}')
            cls_node = Stmt('class', name, exprs=fields, body=methods, line=t.line, declared_type=base_class)
            if hasattr(self, 'classes_by_name'):
                self.classes_by_name[name] = cls_node
            return cls_node

        # Functions
        if v == 'async':
            self.take('async')
            self.skipnl()
            t = self.t
            v = t.value

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
                if self.accept('struct'):
                    s_name = self.take().value
                    p_type = f"struct {s_name}"
                    while self.accept('*'):
                        p_type += '*'
                elif self.t.kind in ('IDENT', 'KEYWORD') and (self.t.value in ('int', 'float', 'double', 'string', 'char', 'bool', 'void') or self.t.value in self.struct_names):
                    p_type = self.take().value
                    while self.accept('*'):
                        p_type += '*'
                while self.accept('*'):
                    p_type = (p_type or 'void') + '*'
                p_name = self.take().value
                params.append(p_name)
                param_types.append(p_type)
                if self.accept('='):
                    self.expr()
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
                    clean_st = declared_type.rstrip('*').replace('struct ', '').strip()
                    if self.lang == 'c' and clean_st in self.struct_names and self.accept('{'):
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

        if v == 'try':
            self.take('try')
            try_body = self.block()
            catch_body = []
            self.skipnl()
            if self.accept('catch'):
                if self.accept('('):
                    err_name = self.take().value
                    self.take(')')
                catch_body = self.block()
            elif self.accept('except'):
                if self.t.value != ':':
                    self.take()
                catch_body = self.block()
            return Stmt('try', None, exprs=[], body=try_body, otherwise=catch_body, line=t.line)

        # Identifiers, calls, assignments, member assignments
        if self.t.kind in ('IDENT', 'KEYWORD'):
            name = self.take().value
            left = Expr('name', name, line=t.line)
            if self.accept('('):
                args = self.parse_arguments(')')
                self.take(')')
                left = Expr('call', name, args, line=t.line)

            # Check for member access or index
            while True:
                if self.t.value in ('.', '->'):
                    op = self.take().value
                    member = self.take().value
                    if self.accept('('):
                        args = self.parse_arguments(')')
                        self.take(')')
                        left = Expr('method_call', member, [left] + args, line=t.line)
                        continue
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
                elif self.t.value == '(' and left.kind == 'member':
                    self.take()
                    args = self.parse_arguments(')')
                    self.take(')')
                    left = Expr('method_call', left.value, [left.children[0]] + args, line=t.line)
                else:
                    break

            if left.kind == 'method_call':
                if left.value == 'forEach' and len(left.children) >= 2:
                    cb = left.children[1]
                    if cb.kind == 'arrow_func':
                        p_node = cb.children[0]
                        p_name = p_node.children[0] if p_node.children else 'item'
                        if hasattr(p_name, 'value'):
                            p_name = p_name.value
                        loop_body = cb.children[1:]
                        if len(loop_body) == 1 and isinstance(loop_body[0], list):
                            loop_body = loop_body[0]
                        self.accept(';')
                        return Stmt('for_in', p_name, [left.children[0]], loop_body, line=t.line)
                self.accept(';')
                return Stmt('method_call', left.value, left.children, line=t.line)

            if left.kind == 'call':
                self.accept(';')
                return Stmt('call', left.value, left.children, line=t.line)

            if left.kind == 'member':
                if self.t.value in ('=', '+=', '-=', '*=', '/='):
                    op = self.take().value
                    rhs = self.expr()
                    self.accept(';')
                    return Stmt('member_assign', left.value, [left.children[0], rhs], line=t.line, declared_type=op)

            if self.t.value in ('++', '--'):
                op = self.take().value
                self.accept(';')
                return Stmt('compound_assign', name, [Expr('operator', op[0], line=t.line), Expr('literal', '1', line=t.line)], line=t.line)

            # Regular assignment
            op = self.t.value
            if op in ('=', '+=', '-=', '*=', '/='):
                self.take()
                rhs = self.expr()
                self.accept(';')
                return Stmt('assign' if op == '=' else 'compound_assign', name, [rhs] if op == '=' else [Expr('operator', op, line=t.line), rhs], line=t.line)

            raise CompileError('expected assignment or function call', t.line, 'syntax')

        raise CompileError(f"unsupported statement starting with {v!r}", t.line, 'syntax')

    def for_stmt(self):
        t = self.take('for')
        self.take('(')
        declared = self.t.value in ('int', 'float', 'double', 'let', 'const', 'var')
        if declared:
            self.take()
        name = self.take().value
        if self.accept('of') or self.accept('in'):
            iter_expr = self.expr()
            self.take(')')
            body = self.block()
            return Stmt('for_in', name, [iter_expr], body, line=t.line)
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
        if self.accept('range'):
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
        else:
            iter_expr = self.expr()
            body = self.block()
            return Stmt('for_in', name, [iter_expr], body, line=t.line)

    def expr(self, minp=0):
        t = self.take()

        # Unary operators
        if t.value in ('-', '!', 'not'):
            left = Expr('unary', t.value, [self.expr(7)], t.line)
        elif t.value == 'await':
            left = self.expr(7)
        elif t.value == '&':
            left = Expr('address_of', None, [self.expr(7)], t.line)
        elif t.value == '*':
            left = Expr('deref', None, [self.expr(7)], t.line)
        elif t.value == 'new':
            class_name = self.take().value
            self.take('(')
            args = self.parse_arguments(')')
            self.take(')')
            if class_name == 'Promise' and args:
                prom_val = self._extract_promise_val(args[0])
                left = prom_val if prom_val is not None else Expr('construct', class_name, args, t.line)
            else:
                left = Expr('construct', class_name, args, t.line)
        elif t.value == '(':
            # Check for C cast e.g. (Student*), (struct Student *), (int), (float)
            is_cast = False
            if self.lang == 'c':
                k = 0
                tok_val = self.t.value
                if tok_val == 'struct':
                    k += 1
                if self.peek(k).kind in ('IDENT', 'KEYWORD') and (self.peek(k).value in ('int', 'float', 'double', 'char', 'void', 'bool', 'short', 'long') or self.peek(k).value in self.struct_names or tok_val == 'struct'):
                    k += 1
                    while self.peek(k).value == '*':
                        k += 1
                    if self.peek(k).value == ')':
                        is_cast = True
            if is_cast:
                cast_type = ""
                if self.t.value == 'struct':
                    self.take()
                    cast_type = f"struct {self.take().value}"
                else:
                    cast_type = self.take().value
                while self.accept('*'):
                    cast_type += '*'
                self.take(')')
                operand = self.expr(minp=7)
                left = Expr('cast', cast_type, [operand], t.line)
            else:
                self.skipnl()
                if self.accept(')'):
                    if self.accept('=>'):
                        body = self.block() if self.t.value == '{' else self.expr()
                        body_list = body if isinstance(body, list) else [body]
                        left = Expr('arrow_func', None, [Expr('params', value=[], children=[], line=t.line)] + body_list, line=t.line)
                    else:
                        left = Expr('name', 'None', line=t.line)
                else:
                    first = self.expr()
                    if self.accept(','):
                        params = [first.value if hasattr(first, 'value') else str(first)]
                        while True:
                            self.skipnl()
                            if self.t.value == ')':
                                break
                            p_tok = self.expr()
                            params.append(p_tok.value if hasattr(p_tok, 'value') else str(p_tok))
                            self.skipnl()
                            if not self.accept(','):
                                break
                        self.take(')')
                        self.take('=>')
                        body = self.block() if self.t.value == '{' else self.expr()
                        body_list = body if isinstance(body, list) else [body]
                        left = Expr('arrow_func', None, [Expr('params', value=[], children=params, line=t.line)] + body_list, line=t.line)
                    else:
                        self.take(')')
                        if self.accept('=>'):
                            body = self.block() if self.t.value == '{' else self.expr()
                            body_list = body if isinstance(body, list) else [body]
                            left = Expr('arrow_func', None, [Expr('params', value=[], children=[first.value if hasattr(first, 'value') else str(first)], line=t.line)] + body_list, line=t.line)
                        else:
                            left = first
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
            if self.lang == 'c':
                # C struct compound literal / initializer list: { expr1, expr2, ... }
                items = []
                if self.t.value != '}':
                    while True:
                        items.append(self.expr())
                        if not self.accept(','):
                            break
                        if self.t.value == '}':
                            break
                self.take('}')
                left = Expr('array', None, items, t.line)
            else:
                # Object / Dict literal
                pairs = []
                self.skipnl()
                if self.t.value != '}':
                    while True:
                        self.skipnl()
                        if self.t.value == '}':
                            break
                        k_tok = self.take()
                        key = k_tok.value.strip('"\'') if k_tok.kind in ('STRING', 'IDENT', 'KEYWORD') else k_tok.value
                        self.skipnl()
                        self.take(':')
                        self.skipnl()
                        v_expr = self.expr()
                        pairs.append(Expr('pair', key, [v_expr], k_tok.line))
                        self.skipnl()
                        if not self.accept(','):
                            break
                        self.skipnl()
                        if self.t.value == '}':
                            break
                self.skipnl()
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
            if t.value == 'sizeof' and self.accept('('):
                type_name = ""
                if self.accept('struct'):
                    type_name = f"struct {self.take().value}"
                    while self.accept('*'):
                        type_name += '*'
                    arg = Expr('type', type_name, line=t.line)
                elif self.t.value in ('int', 'float', 'double', 'char', 'void', 'bool', 'short', 'long') or self.t.value in self.struct_names:
                    type_name = self.take().value
                    while self.accept('*'):
                        type_name += '*'
                    arg = Expr('type', type_name, line=t.line)
                else:
                    arg = self.expr()
                self.take(')')
                left = Expr('call', 'sizeof', [arg], t.line)
            elif self.accept('('):
                args = self.parse_arguments(')')
                self.take(')')
                # If identifier is a known struct / class name or PascalCase, treat as construct call in Python/C
                if t.value in self.struct_names or (t.value[0].isupper() and t.value not in ('True', 'False', 'None')):
                    left = Expr('construct', t.value, args, t.line)
                else:
                    left = Expr('call', t.value, args, t.line)
            else:
                if self.accept('=>'):
                    body = self.block() if self.t.value == '{' else self.expr()
                    body_list = body if isinstance(body, list) else [body]
                    left = Expr('arrow_func', None, [Expr('params', value=[], children=[t.value], line=t.line)] + body_list, line=t.line)
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
