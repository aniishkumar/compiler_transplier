"""Code generators for the documented, type-checked common language subset."""
import ast
import json
import re

from .ast_nodes import Expr, Stmt
from .errors import CompileError

_PRINTF_SPEC = re.compile(r'%(?:%|[di fsc])'.replace(' ',''))


def generate(program, target):
    if target not in ('c', 'python', 'javascript'):
        raise ValueError(f'unknown target {target!r}')
    if isinstance(program, dict):
        from .ir import restore
        program = restore(program)
    return Generator(target).program(program)


class Generator:
    def __init__(self, lang):
        self.lang = lang
        self.source = None
        self.level = 0
        self.lines = []
        self.function_nodes = {}
        self.function_returns = {}
        self.function_params = {}
        self.statement_envs = {}
        self.function_envs = {}
        self.call_arg_types = {}
        self.function_name_map = {}

    @staticmethod
    def _literal_value(value):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return None

    def _explicit_type(self, source_type):
        return {
            'int': 'int', 'float': 'double', 'double': 'double', 'char': 'char',
            'bool': 'bool', 'string': 'string',
        }.get(source_type)

    def _expr_type(self, e, env):
        if e.kind == 'char': return 'char'
        if e.kind == 'literal':
            value = self._literal_value(e.value)
            if isinstance(value, bool): return 'bool'
            if isinstance(value, int): return 'int'
            if isinstance(value, float): return 'double'
            if isinstance(value, str): return 'string'
            return None
        if e.kind == 'name': return env.get(e.value)
        if e.kind == 'index':
            array_type = env.get(e.value)
            return array_type[:-2] if array_type and array_type.endswith('[]') else None
        if e.kind == 'array':
            item_types = {self._expr_type(child, env) for child in e.children}
            return 'int[]' if not item_types or item_types <= {'int'} else None
        if e.kind == 'unary':
            return 'bool' if e.value in ('!', 'not') else self._expr_type(e.children[0], env)
        if e.kind == 'binary':
            left = self._expr_type(e.children[0], env)
            right = self._expr_type(e.children[1], env)
            if e.value in ('==', '!=', '<', '>', '<=', '>=', '&&', '||', 'and', 'or'):
                return 'bool'
            if e.value == '+' and left == right == 'string': return 'string_concat'
            if left in ('int', 'double') and right in ('int', 'double'):
                return 'double' if 'double' in (left, right) or e.value == '/' else 'int'
            return None
        if e.kind == 'call': return self.function_returns.get(e.value)
        return None

    def _record_calls(self, e, env):
        if e.kind == 'call' and e.value in self.function_nodes:
            self.call_arg_types.setdefault(e.value, []).append([self._expr_type(a, env) for a in e.children])
        for child in e.children:
            if isinstance(child, Expr): self._record_calls(child, env)

    def _bind_type(self, env, name, inferred, line):
        if not inferred: return
        prior=env.get(name)
        if prior and prior != inferred:
            if prior in ('int','double') and inferred in ('int','double'):
                env[name]='double' if 'double' in (prior,inferred) else 'int'
                return
            if self.lang=='c':
                raise CompileError(f"variable {name!r} changes from {prior} to {inferred}; a single C type cannot preserve that behavior",line,'semantic')
            env[name]=inferred
            return
        env[name]=inferred

    def _infer_block(self, statements, inherited=None, record=True):
        env = dict(inherited or {})
        for s in statements:
            if s.kind == 'group':
                env.update(self._infer_block(s.body, env, record))
                continue
            if s.kind == 'function':
                continue
            if s.kind == 'for':
                init = s.exprs[0]
                loop_env = dict(env)
                loop_env[s.value] = 'int'
                if record: self.statement_envs[id(s)] = dict(loop_env)
                self._record_calls(init.children[0], loop_env)
                self._record_calls(s.exprs[1], loop_env)
                self._infer_block(s.body, loop_env, record)
                continue
            if record: self.statement_envs[id(s)] = dict(env)
            for expression in s.exprs: self._record_calls(expression, env)
            if s.kind in ('decl', 'array_decl'):
                declared = self._explicit_type(s.declared_type)
                initializer = self._expr_type(s.exprs[0], env) if s.exprs else None
                if self.lang=='c' and s.kind!='array_decl' and declared and initializer:
                    compatible=(declared==initializer or declared in ('int','double') and initializer in ('int','double','bool') or declared=='bool' and initializer in ('int','double','bool') or declared=='char' and initializer in ('char','int'))
                    if not compatible: raise CompileError(f"initializer type {initializer} is incompatible with declared {declared} variable {s.value!r}",s.line,'semantic')
                inferred = declared or initializer
                if s.kind == 'array_decl': inferred = 'int[]'
                if inferred: self._bind_type(env,s.value,inferred,s.line)
            elif s.kind == 'assign':
                inferred = self._expr_type(s.exprs[0], env)
                prior=env.get(s.value)
                if self.source=='c' and prior and inferred:
                    if prior in ('int','double') and inferred in ('int','double','bool'): pass
                    elif prior!=inferred: raise CompileError(f"assignment type {inferred} is incompatible with C variable {s.value!r} of type {prior}",s.line,'semantic')
                    else: self._bind_type(env,s.value,inferred,s.line)
                elif inferred: self._bind_type(env,s.value,inferred,s.line)
            elif s.kind == 'compound_assign' and self.lang=='c':
                left=env.get(s.value); right=self._expr_type(s.exprs[1],env)
                if left not in ('int','double') or (right is not None and right not in ('int','double')):
                    raise CompileError(f"compound assignment to {s.value!r} requires numeric operands for C output",s.line,'semantic')
            elif s.kind == 'array_assign' and self.lang=='c':
                if self._expr_type(s.exprs[1],env)!='int':
                    raise CompileError('only integer values can be assigned to supported C arrays',s.line,'semantic')
            elif s.kind in ('if', 'while'):
                self._infer_block(s.body, env, record)
                self._infer_block(s.otherwise, env, record)
        return env

    def _infer_types(self, program):
        self.source = program.source_language
        self.function_nodes = {s.value: s for s in program.body if s.kind == 'function'}
        for name, fn in self.function_nodes.items():
            explicit = self._explicit_type(fn.declared_type)
            if explicit: self.function_returns[name] = explicit
        self.call_arg_types = {}
        # Iterate so call-site arguments can constrain function parameters and return types.
        for _ in range(4):
            self.call_arg_types = {}
            global_statements = [s for s in program.body if s.kind != 'function']
            self._infer_block(global_statements, {}, record=False)
            for fn in self.function_nodes.values():
                params = fn.exprs[0].children
                declared_params = fn.exprs[0].value or []
                arg_sets = self.call_arg_types.get(fn.value, [])
                param_types = {}
                for index, param in enumerate(params):
                    explicit = self._explicit_type(declared_params[index]) if index < len(declared_params) else None
                    inferred = explicit
                    if not inferred:
                        candidates = {args[index] for args in arg_sets if index < len(args) and args[index]}
                        if len(candidates) == 1: inferred = candidates.pop()
                    if inferred: param_types[param] = inferred
                env = self._infer_block(fn.body, param_types, record=False)
                returns = set()
                def collect_returns(stmts, scope):
                    local = dict(scope)
                    for stmt in stmts:
                        if stmt.kind == 'decl':
                            typ = self._explicit_type(stmt.declared_type) or (self._expr_type(stmt.exprs[0], local) if stmt.exprs else None)
                            if typ: local[stmt.value] = typ
                        elif stmt.kind == 'return' and stmt.exprs:
                            typ = self._expr_type(stmt.exprs[0], local)
                            if typ: returns.add(typ)
                        collect_returns(stmt.body, local)
                        collect_returns(stmt.otherwise, local)
                        if stmt.kind == 'group': collect_returns(stmt.body, local)
                collect_returns(fn.body, env)
                ret = self._explicit_type(fn.declared_type)
                if not ret and len(returns) == 1: ret = returns.pop()
                elif not ret and len(returns) > 1: ret = 'conflict'
                elif not ret and any(self._contains_value_return(stmt) for stmt in fn.body): ret = 'unknown'
                if not ret and not any(self._contains_value_return(stmt) for stmt in fn.body): ret = 'void'
                if ret: self.function_returns[fn.value] = ret
                self.function_params[fn.value] = param_types
        self.statement_envs = {}
        self.global_env = self._infer_block([s for s in program.body if s.kind != 'function'], {}, record=True)
        for fn in self.function_nodes.values():
            params = dict(self.function_params.get(fn.value, {}))
            self.function_envs[fn.value] = self._infer_block(fn.body, params, record=True)

    @staticmethod
    def _contains_value_return(stmt):
        if stmt.kind == 'return' and stmt.exprs: return True
        return any(Generator._contains_value_return(child) for child in stmt.body + stmt.otherwise)

    def _c_type(self, typ, line, name):
        result = {'int': 'int', 'double': 'double', 'char': 'char', 'bool': 'bool', 'string': 'const char *', 'int[]': 'int *'} .get(typ)
        if result: return result
        raise CompileError(f"cannot safely infer a C type for {name!r}; initialize it with an integer, decimal, string, or Boolean in the supported subset", line, 'generation')

    def _type_for(self, e, s):
        env = self.statement_envs.get(id(s), self.global_env)
        # Declarations are represented in the environment after their initializer is processed.
        typ = self._explicit_type(s.declared_type) if getattr(s, 'declared_type', None) else None
        if s.kind == 'array_decl': return 'int[]'
        if not typ and s.exprs: typ = self._expr_type(s.exprs[0], env)
        if not typ: typ = env.get(s.value)
        if not typ:
            candidates = {scope[s.value] for scope in self.function_envs.values() if s.value in scope}
            if len(candidates) == 1: typ = candidates.pop()
        return typ

    def emit(self, text): self.lines.append('    ' * self.level + text)

    def expr(self, e):
        if e.kind in ('literal', 'char'):
            if e.kind == 'char':
                value = self._literal_value(e.value)
                if not isinstance(value, str) or len(value) != 1:
                    raise CompileError('character literals must contain exactly one character', e.line, 'generation')
                if self.lang == 'c': return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"
                return json.dumps(value)
            v = e.value
            if v in ('True', 'true'): return 'True' if self.lang == 'python' else ('true' if self.lang == 'javascript' else 'true')
            if v in ('False', 'false'): return 'False' if self.lang == 'python' else ('false' if self.lang == 'javascript' else 'false')
            if v in ('None', 'null'): return 'None' if self.lang == 'python' else 'null'
            if isinstance(v, str) and v[:1] in ('"', "'"):
                value = self._literal_value(v)
                if isinstance(value, str): return json.dumps(value, ensure_ascii=False)
            return v
        if e.kind == 'name': return e.value
        if e.kind == 'index': return f'{e.value}[{self.expr(e.children[0])}]'
        if e.kind == 'array': return '[' + ', '.join(self.expr(x) for x in e.children) + ']'
        if e.kind == 'unary':
            op = 'not ' if self.lang == 'python' and e.value in ('!', 'not') else e.value
            return op + self.expr(e.children[0])
        if e.kind == 'binary':
            op = e.value
            if self.lang == 'python': op = {'&&': 'and', '||': 'or'}.get(op, op)
            else: op = {'and': '&&', 'or': '||'}.get(op, op)
            left=self.expr(e.children[0]); right=self.expr(e.children[1])
            env=getattr(self,'_active_env',self.global_env if hasattr(self,'global_env') else {})
            left_type=self._expr_type(e.children[0],env); right_type=self._expr_type(e.children[1],env)
            if e.value=='/' and self.source=='c' and self.lang=='python' and left_type=='int' and right_type=='int':
                return f'int(({left}) / ({right}))'
            if e.value=='/' and self.source=='c' and self.lang=='javascript' and left_type=='int' and right_type=='int':
                return f'Math.trunc(({left}) / ({right}))'
            if e.value=='/' and self.lang=='c' and self.source in ('python','javascript') and left_type=='int' and right_type=='int':
                left=f'((double)({left}))'
            return f'({left} {op} {right})'
        if e.kind == 'call': return f"{self.function_name_map.get(e.value,e.value)}({', '.join(self.expr(x) for x in e.children)})"
        return 'None'

    def _format_data(self, format_expr, args, line):
        raw = self._literal_value(format_expr.value) if format_expr.kind == 'literal' else None
        if not isinstance(raw, str): raise CompileError('printf requires a literal format string', line, 'generation')
        specs=[]; index=0
        while index < len(raw):
            if raw[index] != '%': index += 1; continue
            if index+1 < len(raw) and raw[index+1] == '%': index += 2; continue
            start=index; index+=1
            while index < len(raw) and raw[index] in '-+0 #0123456789.': index+=1
            if index >= len(raw): raise CompileError('printf format ends with an incomplete % conversion',line,'syntax')
            specifier=raw[index]; index+=1
            if specifier not in 'disfc':
                raise CompileError(f'printf conversion %{specifier} is unsupported; use %d, %i, %f, %s, or %c',line,'generation')
            full=raw[start:index]
            if len(full)>2:
                raise CompileError('printf flags and field widths are outside the portable subset',line,'generation')
            specs.append(full)
        if len(specs) != len(args):
            raise CompileError(f'printf format has {len(specs)} supported conversion specifier(s) but {len(args)} value argument(s)', line, 'semantic')
        env = self.statement_envs.get(getattr(self, '_current_print_id', -1), self.global_env)
        for spec, arg in zip(specs, args):
            typ = self._expr_type(arg, env); code=spec[-1]
            valid = (code in 'di' and typ == 'int') or (code == 'f' and typ in ('int','double')) or (code == 's' and typ in ('string','char')) or (code == 'c' and typ in ('char','int'))
            if typ and not valid:
                raise CompileError(f'printf {spec!r} does not match the inferred {typ} argument type', arg.line, 'semantic')
        return raw, specs

    def _printf(self, s):
        self._current_print_id = id(s)
        fmt_expr, *args = s.exprs
        raw, specs = self._format_data(fmt_expr, args, s.line)
        if self.lang == 'c': return f'printf({json.dumps(raw, ensure_ascii=False)}' + (', ' + ', '.join(self.expr(a) for a in args) if args else '') + ')'
        if self.lang == 'python':
            if not args: return json.dumps(raw.replace('%%', '%'), ensure_ascii=False)
            values = self.expr(args[0]) if len(args) == 1 else '(' + ', '.join(self.expr(a) for a in args) + ')'
            if len(args) == 1 and isinstance(args[0], Expr) and args[0].kind == 'array': values += ','
            return f'({json.dumps(raw, ensure_ascii=False)} % {values})'
        # Use console.log for newline-terminated C output; it preserves the usual C printf result
        # without a Node-specific formatting helper. Use util.format only when printf omits newline.
        js_raw = raw.replace('%%', '%')
        js_args=[]
        for spec, arg in zip(specs, args):
            value=self.expr(arg)
            if spec[-1] == 'c' and self._expr_type(arg, self.statement_envs.get(id(s), self.global_env)) == 'int': value=f'String.fromCharCode({value})'
            js_args.append(value)
        js_raw=re.sub(r'%(?:[-+0 #]*\d*(?:\.\d+)?)c', '%s', js_raw)
        if js_raw.endswith('\n'):
            js_raw = js_raw[:-1]
            return f'console.log({json.dumps(js_raw, ensure_ascii=False)}' + (', ' + ', '.join(js_args) if js_args else '') + ')'
        call = f'require("util").format({json.dumps(js_raw, ensure_ascii=False)}' + (', ' + ', '.join(js_args) if js_args else '') + ')'
        return f'process.stdout.write({call})'

    def _c_print(self, s):
        if s.value == 'printf':
            self._current_print_id = id(s)
            call = self._printf(s)
            self.emit(call + ';')
            return
        args = s.exprs
        if not args:
            self.emit('printf("\\n");')
            return
        env = self.statement_envs.get(id(s), self.global_env)
        formats=[]; values=[]
        for arg in args:
            typ = self._expr_type(arg, env)
            if typ == 'string': formats.append('%s'); values.append(self.expr(arg))
            elif typ == 'char': formats.append('%c'); values.append(self.expr(arg))
            elif typ == 'int': formats.append('%d'); values.append(self.expr(arg))
            elif typ == 'double': formats.append('%g'); values.append(self.expr(arg))
            elif typ == 'bool':
                formats.append('%s')
                value=self.expr(arg)
                words=('True','False') if self.source=='python' else ('true','false')
                values.append(f'({value} ? "{words[0]}" : "{words[1]}")')
            else:
                name=arg.value if arg.kind=='name' else 'expression'
                raise CompileError(f"cannot safely print {name!r} as C because its type cannot be inferred",arg.line,'generation')
        self.emit(f'printf({json.dumps(" ".join(formats)+"\n")}, {", ".join(values)});')

    def suite(self, body):
        if not body:
            self.emit('pass' if self.lang == 'python' else ';')
            return
        self.level += 1
        for stmt in body: self.stmt(stmt)
        self.level -= 1

    def blockhead(self, head, body):
        if self.lang == 'python': self.emit(head + ':'); self.suite(body)
        else: self.emit(head + ' {'); self.suite(body); self.emit('}')

    def _assignment_value(self, s, expression):
        if self.source!='c' or self.lang not in ('python','javascript'): return expression
        target_type=self._explicit_type(s.declared_type) or self.statement_envs.get(id(s),{}).get(s.value)
        if not target_type and s.exprs: target_type=self._expr_type(s.exprs[0],self.statement_envs.get(id(s),{}))
        value_type=self._expr_type(s.exprs[0],self.statement_envs.get(id(s),{})) if s.exprs else None
        if target_type=='int' and value_type in ('double','bool'):
            return f'int({expression})' if self.lang=='python' else f'Math.trunc({expression})'
        if target_type=='bool' and value_type in ('int','double'):
            return f'bool({expression})' if self.lang=='python' else f'Boolean({expression})'
        return expression

    def stmt(self, s):
        L = self.lang
        self._active_env=self.statement_envs.get(id(s),getattr(self,'global_env',{}))
        if s.kind == 'group':
            for child in s.body: self.stmt(child)
            return
        if s.kind == 'decl':
            val = f' = {self._assignment_value(s,self.expr(s.exprs[0]))}' if s.exprs else ''
            if L == 'python': self.emit(f'{s.value}{val}')
            elif L == 'c':
                qualifier='const ' if s.declared_type=='const' else ''
                self.emit(f'{qualifier}{self._c_type(self._type_for(s.exprs[0] if s.exprs else None, s), s.line, s.value)} {s.value}{val};')
            else: self.emit(f'{"const" if s.declared_type=='const' else "let"} {s.value}{val};')
        elif s.kind == 'array_decl':
            arr = s.exprs[0]; size = arr.value if arr.value is not None else len(arr.children)
            values_list = [self.expr(x) for x in arr.children]
            if L != 'c' and arr.value is not None: values_list.extend('0' for _ in range(max(0, size-len(values_list))))
            values = ', '.join(values_list)
            if L == 'c': self.emit(f'int {s.value}[{size}] = {{{values}}};' if values else f'int {s.value}[{size}] = {{0}};')
            else:
                prefix='' if L=='python' else ('const ' if s.declared_type=='const' else 'let ')
                self.emit(prefix + f'{s.value} = [{values}]' + (';' if L != 'python' else ''))
        elif s.kind == 'assign':
            value=self._assignment_value(s,self.expr(s.exprs[0]))
            self.emit(f'{s.value} = {value}' + (';' if L != 'python' else ''))
        elif s.kind == 'array_assign': self.emit(f'{s.value}[{self.expr(s.exprs[0])}] = {self.expr(s.exprs[1])}' + (';' if L != 'python' else ''))
        elif s.kind == 'compound_assign': self.emit(f'{s.value} {s.exprs[0].value} {self.expr(s.exprs[1])}' + (';' if L != 'python' else ''))
        elif s.kind == 'print':
            if L == 'c': self._c_print(s)
            elif s.value == 'printf':
                expression=self._printf(s)
                if L == 'python': self.emit(f'print({expression}, end="")')
                else: self.emit(expression + ';')
            elif L == 'python': self.emit('print(' + ', '.join(self.expr(x) for x in s.exprs) + ')')
            else: self.emit('console.log(' + ', '.join(self.expr(x) for x in s.exprs) + ');')
        elif s.kind in ('if', 'while'):
            self.blockhead(f'{s.kind} {"(" if L != "python" else ""}{self.expr(s.exprs[0])}{")" if L != "python" else ""}', s.body)
            if s.otherwise: self.blockhead('else', s.otherwise)
        elif s.kind == 'for':
            init, cond, step = s.exprs; initval = self.expr(init.children[0]); update = self.update(step)
            if L == 'python':
                self.emit(f'{s.value} = {initval}')
                body = list(s.body) + [self.update_stmt(s.value, step)]
                self.blockhead(f'while {self.expr(cond)}', body)
            else:
                prefix = ('let ' if L == 'javascript' and init.value is True else ('int ' if L == 'c' and init.value is True else ''))
                self.blockhead(f'for ({prefix}{s.value} = {initval}; {self.expr(cond)}; {update})', s.body)
        elif s.kind == 'return': self.emit('return' + (' ' + self.expr(s.exprs[0]) if s.exprs else '') + (';' if L != 'python' else ''))
        elif s.kind == 'call': self.emit(f"{self.function_name_map.get(s.value,s.value)}({', '.join(self.expr(x) for x in s.exprs)})" + (';' if L != 'python' else ''))
        elif s.kind == 'function':
            function_name=self.function_name_map.get(s.value,s.value)
            args = ', '.join(s.exprs[0].children)
            if L == 'python': self.blockhead(f'def {function_name}({args})', s.body)
            elif L == 'javascript': self.blockhead(f'function {function_name}({args})', s.body)
            else:
                param_types = s.exprs[0].value or []
                rendered=[]
                for index, name in enumerate(s.exprs[0].children):
                    typ = self._explicit_type(param_types[index]) if index < len(param_types) else None
                    typ = typ or self.function_params.get(s.value, {}).get(name)
                    rendered.append(f'{self._c_type(typ, s.line, name)} {name}')
                ret=self._explicit_type(s.declared_type) or self.function_returns.get(s.value)
                if s.value=='main': ret='int'
                if not ret and any(self._contains_value_return(child) for child in s.body):
                    raise CompileError(f"cannot infer the return type of function {s.value!r} for C output",s.line,'generation')
                if not ret: ret='void'
                c_return='void' if ret=='void' else self._c_type(ret,s.line,s.value+' return value')
                self.emit(f'{c_return} {function_name}({", ".join(rendered) if rendered else "void"}) {{')
                self.suite(s.body)
                if s.value=='main' and not any(child.kind=='return' for child in s.body): self.emit('    '*(self.level+1)+'return 0;')
                self.emit('}')

    def update(self, step):
        target = self.expr(step.children[0])
        if step.value == '++': return f'{target}++'
        if step.value == '--': return f'{target}--'
        if step.value == '=': return f'{target} = {self.expr(step.children[1])}'
        return f'{target} {step.value} {self.expr(step.children[1])}'

    def update_stmt(self, name, step):
        target = Expr('name', name)
        if step.value == '++': return Stmt('assign', name, [Expr('binary', '+', [target, Expr('literal', '1')])])
        if step.value == '--': return Stmt('assign', name, [Expr('binary', '-', [target, Expr('literal', '1')])])
        if step.value in ('+=', '-='): return Stmt('compound_assign', name, [Expr('operator', step.value), step.children[1]])
        return Stmt('assign', name, [step.children[1]])

    def program(self, p):
        self._infer_types(p)
        c_functions=[s for s in p.body if s.kind=='function']
        has_c_entry=any(s.value=='main' for s in c_functions)
        if self.lang=='c':
            if self.source!='c' and has_c_entry:
                self.function_name_map['main']='multilang_main'
            if self.source=='c' and has_c_entry:
                for stmt in p.body: self.stmt(stmt)
                return '#include <stdio.h>\n#include <stdbool.h>\n\n'+'\n'.join(self.lines)+'\n'
            for function in c_functions: self.stmt(function)
            helper_source='\n'.join(self.lines)
            self.lines=[]; self.level=1
            for statement in p.body:
                if statement.kind!='function': self.stmt(statement)
            body=''.join('    '+line+'\n' for line in self.lines)
            body+='    return 0;\n'
            return '#include <stdio.h>\n#include <stdbool.h>\n\n'+(helper_source+'\n\n' if helper_source else '')+'int main(void) {\n'+body+'}\n'
        for stmt in p.body: self.stmt(stmt)
        if self.source == 'c' and has_c_entry:
            if self.lang == 'python': self.emit('raise SystemExit(main())')
            else: self.emit('process.exitCode = main();')
        return '\n'.join(self.lines) + '\n'
