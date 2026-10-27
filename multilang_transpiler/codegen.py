"""Code generators for C, Python, and JavaScript subsets."""
import ast
import json
import re

from .ast_nodes import Expr, Stmt
from .errors import CompileError

_PRINTF_SPEC = re.compile(r'%(?:%|[di fsc])'.replace(' ', ''))


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
        self.structs = {}
        self.ref_vars = set()
        self.ref_params = set()
        self.declared_in_scope = set()
        self._current_fn_params = set()
        self.needs_math = False
        self.needs_stdlib = False
        self.needs_string = False
        self.user_includes = []
        self._array_literal_values = {}

    @staticmethod
    def _subst_node(node, old_name, new_expr):
        if not hasattr(node, 'kind'):
            return node
        if node.kind == 'name' and node.value == old_name:
            return new_expr
        if isinstance(node, Expr):
            new_children = [Generator._subst_node(c, old_name, new_expr) for c in node.children]
            return Expr(node.kind, node.value, new_children, getattr(node, 'line', 1))
        if isinstance(node, Stmt):
            new_exprs = [Generator._subst_node(e, old_name, new_expr) for e in node.exprs]
            new_body = [Generator._subst_node(b, old_name, new_expr) for b in node.body]
            new_other = [Generator._subst_node(o, old_name, new_expr) for o in node.otherwise]
            return Stmt(node.kind, node.value, exprs=new_exprs, body=new_body, otherwise=new_other,
                        line=getattr(node, 'line', 1), declared_type=getattr(node, 'declared_type', None))
        return node

    @staticmethod
    def _literal_value(value):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return None

    def _explicit_type(self, source_type):
        if not source_type or source_type in ('let', 'var', 'const'):
            return None
        if source_type.endswith('*'):
            base = self._explicit_type(source_type[:-1])
            return f"{base}*" if base else source_type
        if source_type.startswith('struct '):
            return source_type
        if source_type in self.structs:
            return source_type
        return {
            'int': 'int', 'float': 'double', 'double': 'double', 'char': 'char',
            'bool': 'bool', 'string': 'string', 'void': 'void'
        }.get(source_type, source_type if (source_type.endswith('*') or source_type in self.structs) else None)

    def _expr_type(self, e, env):
        if not hasattr(e, 'kind'):
            return None
        if e.kind == 'char': return 'char'
        if e.kind == 'literal':
            value = self._literal_value(e.value)
            if isinstance(value, bool): return 'bool'
            if isinstance(value, int): return 'int'
            if isinstance(value, float): return 'double'
            if isinstance(value, str): return 'string'
            return None
        if e.kind == 'name':
            if e.value in self.ref_vars and self.lang == 'c':
                return 'int'
            return env.get(e.value)
        if e.kind == 'construct': return e.value
        if e.kind == 'type': return e.value
        if e.kind == 'cast': return e.value
        if e.kind == 'member':
            target_node = e.children[0]
            target_type = None
            if target_node.kind == 'name':
                if target_node.value in ('self', 'this', 's'):
                    target_type = env.get(target_node.value) or env.get('self') or env.get('this') or env.get('s')
                    if not target_type and getattr(self, '_current_struct', None):
                        target_type = f"{self._current_struct}*"
                else:
                    target_type = env.get(target_node.value)
            if not target_type:
                target_type = self._expr_type(target_node, env)
            st = self.structs.get(target_type.rstrip('*').replace('struct ', '').strip() if target_type else '')
            if st:
                for f in st.exprs:
                    if f.value == e.value:
                        f_t = f.declared_type or 'int'
                        if 'char' in f_t or 'string' in f_t:
                            return 'string'
                        if 'double' in f_t or 'float' in f_t:
                            return 'double'
                        return f_t
            return None
        if e.kind == 'address_of':
            sub = self._expr_type(e.children[0], env)
            return f"{sub}*" if sub else 'void*'
        if e.kind == 'deref':
            sub = self._expr_type(e.children[0], env)
            return sub[:-1] if sub and sub.endswith('*') else 'int'
        if e.kind == 'index':
            array_type = env.get(e.value) if isinstance(e.value, str) else self._expr_type(e.value, env)
            if array_type:
                if array_type.endswith('[]'): return array_type[:-2]
                if array_type.endswith('*'): return array_type[:-1]
            return None
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
            if e.value in ('+', '-') and left and ('*' in left or left.endswith('*')):
                return left
            return None
        if e.kind in ('call', 'method_call'):
            func_name = e.value
            if func_name == 'sizeof':
                return 'int'
            if func_name in ('sqrt', 'pow', 'sin', 'cos', 'tan', 'floor', 'ceil'):
                return 'double'
            if func_name == 'abs':
                return 'int'
            return self.function_returns.get(func_name)
        return None

    def _record_calls(self, e, env):
        if not hasattr(e, 'kind'):
            return
        if e.kind in ('call', 'method_call'):
            func_name = e.value
            if func_name in ('sqrt', 'pow', 'sin', 'cos', 'tan', 'floor', 'ceil', 'abs'):
                self.needs_math = True
            elif func_name in ('malloc', 'free', 'calloc', 'realloc'):
                self.needs_stdlib = True
            if func_name in self.function_nodes:
                self.call_arg_types.setdefault(func_name, []).append([self._expr_type(a, env) for a in e.children])
        for child in e.children:
            if isinstance(child, Expr): self._record_calls(child, env)

    def _bind_type(self, env, name, inferred, line):
        if not inferred: return
        prior = env.get(name)
        if prior and prior != inferred:
            if prior in ('int', 'double') and inferred in ('int', 'double'):
                env[name] = 'double' if 'double' in (prior, inferred) else 'int'
                return
            if self.lang == 'c':
                raise CompileError(f"variable {name!r} changes from {prior} to {inferred}; a single C type cannot preserve that behavior", line, 'semantic')
            env[name] = inferred
            return
        env[name] = inferred

    def _infer_block(self, statements, inherited=None, record=True):
        env = dict(inherited or {})
        for s in statements:
            if s.kind == 'group':
                env.update(self._infer_block(s.body, env, record))
                continue
            if s.kind in ('function', 'struct', 'class', 'import'):
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
            if s.kind == 'for_in':
                target_expr = s.exprs[0]
                loop_env = dict(env)
                loop_env[s.value] = 'int'
                if record: self.statement_envs[id(s)] = dict(loop_env)
                self._record_calls(target_expr, loop_env)
                self._infer_block(s.body, loop_env, record)
                continue
            if record: self.statement_envs[id(s)] = dict(env)
            if s.kind == 'call':
                func_name = s.value
                if func_name in ('sqrt', 'pow', 'sin', 'cos', 'tan', 'floor', 'ceil', 'abs'):
                    self.needs_math = True
                elif func_name in ('malloc', 'free', 'calloc', 'realloc'):
                    self.needs_stdlib = True
                if func_name in self.function_nodes:
                    self.call_arg_types.setdefault(func_name, []).append([self._expr_type(a, env) for a in s.exprs])
            for expression in s.exprs: self._record_calls(expression, env)
            if s.kind in ('decl', 'array_decl'):
                declared = self._explicit_type(s.declared_type)
                initializer = self._expr_type(s.exprs[0], env) if s.exprs else None
                if self.lang == 'c' and s.kind != 'array_decl' and declared and initializer:
                    compatible = (declared == initializer or
                                  declared in ('int', 'double') and initializer in ('int', 'double', 'bool') or
                                  declared == 'bool' and initializer in ('int', 'double', 'bool') or
                                  declared == 'char' and initializer in ('char', 'int') or
                                  declared in self.structs or declared.endswith('*'))
                    if not compatible:
                        raise CompileError(f"initializer type {initializer} is incompatible with declared {declared} variable {s.value!r}", s.line, 'semantic')
                inferred = declared or initializer
                if s.kind == 'array_decl': inferred = 'int[]'
                if inferred: self._bind_type(env, s.value, inferred, s.line)
            elif s.kind == 'assign':
                inferred = self._expr_type(s.exprs[0], env)
                prior = env.get(s.value)
                if self.source == 'c' and prior and inferred:
                    if prior in ('int', 'double') and inferred in ('int', 'double', 'bool'): pass
                    elif prior != inferred: raise CompileError(f"assignment type {inferred} is incompatible with C variable {s.value!r} of type {prior}", s.line, 'semantic')
                    else: self._bind_type(env, s.value, inferred, s.line)
                elif inferred: self._bind_type(env, s.value, inferred, s.line)
            elif s.kind == 'compound_assign' and self.lang == 'c':
                left = env.get(s.value)
                right = self._expr_type(s.exprs[1], env)
                if left not in ('int', 'double') or (right is not None and right not in ('int', 'double')):
                    raise CompileError(f"compound assignment to {s.value!r} requires numeric operands for C output", s.line, 'semantic')
            elif s.kind == 'array_assign' and self.lang == 'c':
                if self._expr_type(s.exprs[1], env) != 'int':
                    raise CompileError('only integer values can be assigned to supported C arrays', s.line, 'semantic')
            elif s.kind in ('if', 'while'):
                self._infer_block(s.body, env, record)
                self._infer_block(s.otherwise, env, record)
        return env

    def _detect_references(self, program):
        # 1. In C: Detect functions taking pointer parameters (*p) where mutations occur
        for s in program.body:
            if s.kind == 'function':
                for p_idx, p_name in enumerate(s.exprs[0].children):
                    types = s.exprs[0].value or []
                    p_type = types[p_idx] if p_idx < len(types) else None
                    if p_type and '*' in p_type and not p_type.startswith('char'):
                        self.ref_params.add(p_name)
        # Find calls passing &var
        def check_calls(stmts):
            for st in stmts:
                if st.kind == 'group': check_calls(st.body)
                elif st.kind == 'call':
                    for arg in st.exprs:
                        if hasattr(arg, 'kind') and arg.kind == 'address_of':
                            if arg.children and arg.children[0].kind == 'name':
                                self.ref_vars.add(arg.children[0].value)
                elif st.kind == 'decl':
                    if st.exprs and hasattr(st.exprs[0], 'kind'):
                        if st.exprs[0].kind == 'address_of' and st.exprs[0].children[0].kind == 'name':
                            self.ref_vars.add(st.exprs[0].children[0].value)
                        elif st.exprs[0].kind == 'construct' and st.exprs[0].value in ('IntReference', 'Ref'):
                            self.ref_vars.add(st.value)
                        elif st.exprs[0].kind == 'dict':
                            # check if it's { value: ... }
                            if len(st.exprs[0].children) == 1 and st.exprs[0].children[0].value == 'value':
                                self.ref_vars.add(st.value)
                check_calls(st.body)
                check_calls(st.otherwise)
        check_calls(program.body)

    def _infer_types(self, program):
        self.source = program.source_language
        self.structs = {s.value: s for s in program.body if s.kind in ('struct', 'class')}
        self.function_nodes = {s.value: s for s in program.body if s.kind == 'function'}
        self._detect_references(program)

        # Track method names per struct to qualify colliding companion functions in C
        self.struct_method_names = {}
        method_counts = {}
        for st in self.structs.values():
            for m in st.body:
                method_counts[m.value] = method_counts.get(m.value, 0) + 1
        for st in self.structs.values():
            for m in st.body:
                if method_counts[m.value] > 1 or getattr(st, 'declared_type', None):
                    self.struct_method_names[(st.value, m.value)] = f"{st.value}_{m.value}"
                else:
                    self.struct_method_names[(st.value, m.value)] = m.value

        # Infer field types of structs from construct calls
        for st in program.body:
            c_call = None
            if st.kind == 'decl' and st.exprs and hasattr(st.exprs[0], 'kind') and st.exprs[0].kind == 'construct':
                c_call = st.exprs[0]
            elif st.kind == 'assign' and st.exprs and hasattr(st.exprs[0], 'kind') and st.exprs[0].kind == 'construct':
                c_call = st.exprs[0]
            if c_call and c_call.value in self.structs:
                s_node = self.structs[c_call.value]
                for f_idx, arg in enumerate(c_call.children):
                    if f_idx < len(s_node.exprs):
                        if not s_node.exprs[f_idx].declared_type:
                            a_type = self._expr_type(arg, {})
                            if a_type == 'string':
                                s_node.exprs[f_idx].declared_type = 'char[50]'
                            elif a_type:
                                s_node.exprs[f_idx].declared_type = a_type

        # Propagate field types between derived and base classes
        for s_node in self.structs.values():
            base_name = getattr(s_node, 'declared_type', None)
            if base_name and base_name in self.structs:
                base_node = self.structs[base_name]
                for bf in base_node.exprs:
                    for df in s_node.exprs:
                        if bf.value == df.value:
                            if df.declared_type and not bf.declared_type:
                                bf.declared_type = df.declared_type
                            elif bf.declared_type and not df.declared_type:
                                df.declared_type = bf.declared_type

        # Heuristic for string fields if still unknown
        for s_node in self.structs.values():
            for f in s_node.exprs:
                if not f.declared_type:
                    if f.value in ('name', 'programming_language', 'title', 'language') or f.value.endswith(('_name', '_str', '_text', '_string')):
                        f.declared_type = 'char[50]'

        for name, fn in self.function_nodes.items():
            explicit = self._explicit_type(fn.declared_type)
            if explicit: self.function_returns[name] = explicit
        self.call_arg_types = {}

        for _ in range(4):
            self.call_arg_types = {}
            global_statements = [s for s in program.body if s.kind not in ('function', 'struct', 'class')]
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
                    if not inferred:
                        for stmt in fn.body:
                            if stmt.kind == 'method_call' and stmt.exprs and stmt.exprs[0].kind == 'name' and stmt.exprs[0].value == param:
                                m_cand = [s_name for s_name, s_def in self.structs.items() if any(m.value == stmt.value for m in s_def.body)]
                                if len(m_cand) == 1:
                                    inferred = m_cand[0]
                                    break
                    if inferred:
                        if (inferred in self.structs or inferred.replace('struct ', '').strip() in self.structs) and not inferred.endswith('*'):
                            inferred = f"{inferred.replace('struct ', '').strip()}*"
                        param_types[param] = inferred
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
        self.global_env = self._infer_block([s for s in program.body if s.kind not in ('function', 'struct', 'class')], {}, record=True)
        for st in self.structs.values():
            for m in st.body:
                m_env = {'s': f"{st.value}*", 'self': f"{st.value}*", 'this': f"{st.value}*"}
                self._infer_block(m.body, m_env, record=True)
        for fn in self.function_nodes.values():
            params = dict(self.function_params.get(fn.value, {}))
            self.function_envs[fn.value] = self._infer_block(fn.body, params, record=True)

    @staticmethod
    def _contains_value_return(stmt):
        if stmt.kind == 'return' and stmt.exprs: return True
        return any(Generator._contains_value_return(child) for child in stmt.body + stmt.otherwise)

    def _c_type(self, typ, line, name):
        if not typ:
            raise CompileError(f"cannot safely infer a C type for {name!r}; initialize it with an integer, decimal, string, or Boolean in the supported subset", line, 'generation')
        if typ.endswith('*'):
            base = self._c_type(typ[:-1], line, name)
            return f"{base} *"
        if typ.startswith('struct '): return typ
        if typ in self.structs: return typ
        result = {'int': 'int', 'double': 'double', 'float': 'float', 'char': 'char', 'bool': 'bool',
                  'string': 'char *', 'const char *': 'const char *', 'int[]': 'int *', 'void': 'void'}.get(typ)
        if result: return result
        raise CompileError(f"cannot safely infer a C type for {name!r}; initialize it with an integer, decimal, string, or Boolean in the supported subset", line, 'generation')

    def _type_for(self, e, s):
        env = self.statement_envs.get(id(s), self.global_env)
        typ = self._explicit_type(s.declared_type) if getattr(s, 'declared_type', None) else None
        if s.kind == 'array_decl': return 'int[]'
        if not typ and s.exprs: typ = self._expr_type(s.exprs[0], env)
        if not typ: typ = env.get(s.value)
        if not typ:
            candidates = {scope[s.value] for scope in self.function_envs.values() if s.value in scope}
            if len(candidates) == 1: typ = candidates.pop()
        return typ

    def emit(self, text):
        self.lines.append('    ' * self.level + text)

    def _is_pointer(self, expr_node):
        if not hasattr(expr_node, 'kind'): return False
        if expr_node.kind == 'address_of': return True
        if expr_node.kind == 'cast' and '*' in (expr_node.value or ''): return True
        if expr_node.kind == 'binary' and expr_node.value == '+': return self._is_pointer(expr_node.children[0])
        if expr_node.kind == 'name':
            if expr_node.value in self.ref_params: return True
            env = getattr(self, '_active_env', {})
            t = env.get(expr_node.value, '')
            return '*' in t or t.endswith('*')
        return False

    def expr(self, e):
        if not hasattr(e, 'kind'):
            return str(e)
        if e.kind in ('literal', 'char'):
            if e.kind == 'char':
                value = self._literal_value(e.value)
                if not isinstance(value, str) or len(value) != 1:
                    raise CompileError('character literals must contain exactly one character', e.line, 'generation')
                if self.lang == 'c': return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"
                return json.dumps(value)
            v = e.value
            if v in ('True', 'true'): return 'True' if self.lang == 'python' else 'true'
            if v in ('False', 'false'): return 'False' if self.lang == 'python' else 'false'
            if v in ('None', 'null', 'NULL'): return 'None' if self.lang == 'python' else ('null' if self.lang == 'javascript' else 'NULL')
            if isinstance(v, str) and v[:1] in ('"', "'"):
                value = self._literal_value(v)
                if isinstance(value, str): return json.dumps(value, ensure_ascii=False)
            return v
        if e.kind == 'name':
            if self.lang == 'c' and e.value in ('self', 'this'):
                return 's'
            if self.lang == 'javascript' and e.value == 'self':
                return 'this'
            if self.lang == 'python' and e.value == 'this':
                return 'self'
            if self.lang != 'c' and e.value in self.ref_vars and not getattr(self, '_in_call_arg', False):
                return f"{e.value}.value"
            return e.value
        if e.kind == 'index':
            arr = self.expr(e.value) if hasattr(e.value, 'kind') else e.value
            return f'{arr}[{self.expr(e.children[0])}]'
        if e.kind == 'array':
            return '[' + ', '.join(self.expr(x) for x in e.children) + ']'
        if e.kind == 'construct':
            clean_name = e.value.replace('struct ', '').rstrip('*')
            args = [self.expr(x) for x in e.children]
            if self.lang == 'python':
                return f"{clean_name}({', '.join(args)})"
            if self.lang == 'javascript':
                return f"new {clean_name}({', '.join(args)})"
            return f"({clean_name}){{{', '.join(args)}}}"
        if e.kind == 'member':
            target_node = e.children[0]
            member = e.value
            # If target is IntReference / { value: ... } and accessing .value in C:
            if self.lang == 'c' and member == 'value' and target_node.kind == 'name' and target_node.value in self.ref_vars:
                return target_node.value
            if self.lang == 'c' and member == 'value' and target_node.kind == 'name' and target_node.value in self.ref_params:
                return f"(*{target_node.value})"
            if self.lang != 'c' and target_node.kind == 'binary' and target_node.value == '+':
                ptr_expr = self.expr(target_node.children[0])
                idx_expr = self.expr(target_node.children[1])
                return f"{ptr_expr}[{idx_expr}].{member}"
            target = self.expr(target_node)
            if self.lang == 'c':
                sep = '->' if (self._is_pointer(target_node) or (target_node.kind == 'name' and target_node.value in ('s', 'self', 'p', 'this'))) else '.'
                return f"{target}{sep}{member}"
            return f"{target}.{member}"
        if e.kind == 'type':
            if self.lang == 'c': return e.value
            return e.value.replace('struct ', '').rstrip('*').strip()
        if e.kind == 'method_call':
            target_node = e.children[0]
            method = e.value
            args = [self.expr(x) for x in e.children[1:]]
            if target_node.kind == 'name' and target_node.value in ('math', 'Math'):
                self.needs_math = True
                if self.lang == 'c': return f"{method}({', '.join(args)})"
                if self.lang == 'python': return f"math.{method}({', '.join(args)})"
                if self.lang == 'javascript': return f"Math.{method}({', '.join(args)})"
            if self.lang == 'c':
                if target_node.kind == 'call' and target_node.value == 'super':
                    current_st = self.structs.get(getattr(self, '_current_struct', None))
                    base_class = getattr(current_st, 'declared_type', None)
                    if base_class:
                        fn_name = self.struct_method_names.get((base_class, method), f"{base_class}_{method}")
                        call_args = [f"({base_class} *)s"] + args
                        return f"{fn_name}({', '.join(call_args)})"
                ref_target = self.expr(target_node)
                target_type = None
                if target_node.kind == 'name':
                    target_type = getattr(self, '_active_env', {}).get(target_node.value)
                if not target_type:
                    target_type = self._expr_type(target_node, getattr(self, '_active_env', {}))
                struct_name = target_type.rstrip('*').replace('struct ', '').strip() if target_type else None
                fn_name = method
                if struct_name and (struct_name, method) in self.struct_method_names:
                    fn_name = self.struct_method_names[(struct_name, method)]
                elif (getattr(self, '_current_struct', None), method) in self.struct_method_names:
                    fn_name = self.struct_method_names[(self._current_struct, method)]
                if not self._is_pointer(target_node):
                    ref_target = f"&{ref_target}"
                call_args = [ref_target] + args
                return f"{fn_name}({', '.join(call_args)})"
            if target_node.kind == 'call' and target_node.value == 'super':
                if self.lang == 'python':
                    return f"super().{method}({', '.join(args)})"
                return f"super.{method}({', '.join(args)})"
            target = self.expr(target_node)
            return f"{target}.{method}({', '.join(args)})"
        if e.kind == 'address_of':
            operand = e.children[0]
            if self.lang != 'c':
                return self.expr(operand)
            return f"&{self.expr(operand)}"
        if e.kind == 'deref':
            operand = e.children[0]
            if self.lang != 'c':
                return f"{self.expr(operand)}.value"
            return f"(*{self.expr(operand)})"
        if e.kind == 'dict':
            entries = [f'{c.value}: {self.expr(c.children[0])}' if self.lang == 'javascript' else f'"{c.value}": {self.expr(c.children[0])}' for c in e.children]
            return '{' + ', '.join(entries) + '}'
        if e.kind == 'cast':
            target = self.expr(e.children[0])
            if self.lang == 'c': return f"({e.value})({target})"
            return target
        if e.kind == 'unary':
            op = 'not ' if self.lang == 'python' and e.value in ('!', 'not') else e.value
            return op + self.expr(e.children[0])
        if e.kind == 'binary':
            op = e.value
            if self.lang == 'python': op = {'&&': 'and', '||': 'or'}.get(op, op)
            else: op = {'and': '&&', 'or': '||'}.get(op, op)
            left = self.expr(e.children[0])
            right = self.expr(e.children[1])
            env = getattr(self, '_active_env', self.global_env if hasattr(self, 'global_env') else {})
            left_type = self._expr_type(e.children[0], env)
            right_type = self._expr_type(e.children[1], env)
            if e.value == '/' and self.source == 'c' and self.lang == 'python' and left_type == 'int' and right_type == 'int':
                return f'int(({left}) / ({right}))'
            if e.value == '/' and self.source == 'c' and self.lang == 'javascript' and left_type == 'int' and right_type == 'int':
                return f'Math.trunc(({left}) / ({right}))'
            if e.value == '/' and self.lang == 'c' and self.source in ('python', 'javascript') and left_type == 'int' and right_type == 'int':
                left = f'((double)({left}))'
            return f'({left} {op} {right})'
        if e.kind == 'call':
            if e.value in ('sqrt', 'pow', 'sin', 'cos', 'tan', 'floor', 'ceil'):
                self.needs_math = True
                if self.lang == 'python': return f"math.{e.value}({', '.join(self.expr(x) for x in e.children)})"
                if self.lang == 'javascript': return f"Math.{e.value}({', '.join(self.expr(x) for x in e.children)})"
                return f"{e.value}({', '.join(self.expr(x) for x in e.children)})"
            if e.value == 'abs':
                if self.lang == 'javascript': return f"Math.abs({', '.join(self.expr(x) for x in e.children)})"
                return f"abs({', '.join(self.expr(x) for x in e.children)})"
            if e.value == 'malloc':
                if self.lang == 'python':
                    elem_type = None
                    count_node = None
                    arg = e.children[0]
                    if arg.kind == 'binary' and arg.value == '*':
                        for child in arg.children:
                            if child.kind == 'call' and child.value == 'sizeof':
                                sizeof_arg = child.children[0]
                                elem_type = (sizeof_arg.value or '').replace('struct ', '').rstrip('*').strip()
                            else:
                                count_node = child
                    elif arg.kind == 'call' and arg.value == 'sizeof':
                        sizeof_arg = arg.children[0]
                        elem_type = (sizeof_arg.value or '').replace('struct ', '').rstrip('*').strip()
                        count_node = Expr('literal', '1')
                    if elem_type and elem_type in self.structs:
                        count_str = self.expr(count_node) if count_node else '1'
                        return f"[{elem_type}() for _ in range({count_str})]"
                    elif count_node:
                        return f"[0 for _ in range({self.expr(count_node)})]"
                    return "[]"
                elif self.lang == 'javascript':
                    elem_type = None
                    count_node = None
                    arg = e.children[0]
                    if arg.kind == 'binary' and arg.value == '*':
                        for child in arg.children:
                            if child.kind == 'call' and child.value == 'sizeof':
                                sizeof_arg = child.children[0]
                                elem_type = (sizeof_arg.value or '').replace('struct ', '').rstrip('*').strip()
                            else:
                                count_node = child
                    elif arg.kind == 'call' and arg.value == 'sizeof':
                        sizeof_arg = arg.children[0]
                        elem_type = (sizeof_arg.value or '').replace('struct ', '').rstrip('*').strip()
                        count_node = Expr('literal', '1')
                    if elem_type and elem_type in self.structs:
                        count_str = self.expr(count_node) if count_node else '1'
                        return f"Array.from({{ length: {count_str} }}, () => new {elem_type}())"
                    elif count_node:
                        return f"new Array({self.expr(count_node)}).fill(0)"
                    return "[]"
            if e.value == 'realloc':
                if self.lang == 'python':
                    ptr_str = self.expr(e.children[0])
                    size_arg = e.children[1]
                    elem_type = None
                    count_node = None
                    if size_arg.kind == 'binary' and size_arg.value == '*':
                        for child in size_arg.children:
                            if child.kind == 'call' and child.value == 'sizeof':
                                sizeof_arg = child.children[0]
                                elem_type = (sizeof_arg.value or '').replace('struct ', '').rstrip('*').strip()
                            else:
                                count_node = child
                    count_str = self.expr(count_node) if count_node else '0'
                    if elem_type and elem_type in self.structs:
                        return f"({ptr_str} + [{elem_type}() for _ in range(max(0, ({count_str}) - len({ptr_str})))])"
                    return f"({ptr_str} + [0 for _ in range(max(0, ({count_str}) - len({ptr_str})))])"
                elif self.lang == 'javascript':
                    ptr_str = self.expr(e.children[0])
                    size_arg = e.children[1]
                    elem_type = None
                    count_node = None
                    if size_arg.kind == 'binary' and size_arg.value == '*':
                        for child in size_arg.children:
                            if child.kind == 'call' and child.value == 'sizeof':
                                sizeof_arg = child.children[0]
                                elem_type = (sizeof_arg.value or '').replace('struct ', '').rstrip('*').strip()
                            else:
                                count_node = child
                    count_str = self.expr(count_node) if count_node else '0'
                    if elem_type and elem_type in self.structs:
                        return f"{ptr_str}.concat(Array.from({{ length: Math.max(0, ({count_str}) - {ptr_str}.length) }}, () => new {elem_type}()))"
                    return f"{ptr_str}.concat(new Array(Math.max(0, ({count_str}) - {ptr_str}.length)).fill(0))"
            if e.value == 'sizeof':
                if self.lang == 'c':
                    return f"sizeof({self.expr(e.children[0])})"
                return '1'
            call_name = self.function_name_map.get(e.value, e.value)
            # When calling a function in C with a pointer parameter where argument is in ref_vars:
            old_in_call = getattr(self, '_in_call_arg', False)
            self._in_call_arg = True
            rendered_args = []
            for arg in e.children:
                if self.lang == 'c' and arg.kind == 'name' and arg.value in self.ref_vars:
                    rendered_args.append(f"&{arg.value}")
                else:
                    rendered_args.append(self.expr(arg))
            self._in_call_arg = old_in_call
            return f"{call_name}({', '.join(rendered_args)})"
        return 'None'

    def _format_data(self, format_expr, args, line):
        raw = self._literal_value(format_expr.value) if format_expr.kind == 'literal' else None
        if not isinstance(raw, str): raise CompileError('printf requires a literal format string', line, 'generation')
        specs = []
        index = 0
        while index < len(raw):
            if raw[index] != '%': index += 1; continue
            if index + 1 < len(raw) and raw[index + 1] == '%': index += 2; continue
            start = index
            index += 1
            while index < len(raw) and raw[index] in '-+0 #0123456789.': index += 1
            if index >= len(raw): raise CompileError('printf format ends with an incomplete % conversion', line, 'syntax')
            specifier = raw[index]
            index += 1
            if specifier not in 'disfc':
                raise CompileError(f'printf conversion %{specifier} is unsupported; use %d, %i, %f, %s, or %c', line, 'generation')
            full = raw[start:index]
            if len(full) > 2 and not re.match(r'^%[-+0 #]*\d*(?:\.\d+)?[disfc]$', full):
                raise CompileError('printf flags and field widths are outside the portable subset', line, 'generation')
            specs.append(full)
        if len(specs) != len(args):
            raise CompileError(f'printf format has {len(specs)} supported conversion specifier(s) but {len(args)} value argument(s)', line, 'semantic')
        env = self.statement_envs.get(getattr(self, '_current_print_id', -1), getattr(self, '_active_env', self.global_env))
        for spec, arg in zip(specs, args):
            typ = self._expr_type(arg, env)
            code = spec[-1]
            valid = (code in 'di' and typ in ('int', None)) or (code == 'f' and typ in ('int', 'double', 'float', None)) or (code == 's' and typ in ('string', 'char', None)) or (code == 'c' and typ in ('char', 'int', None))
            if typ and not valid and typ not in self.structs:
                raise CompileError(f'printf {spec!r} does not match the inferred {typ} argument type', arg.line, 'semantic')
        return raw, specs

    def _printf(self, s):
        self._current_print_id = id(s)
        fmt_expr, *args = s.exprs
        raw, specs = self._format_data(fmt_expr, args, s.line)
        if self.lang == 'c':
            return f'printf({json.dumps(raw, ensure_ascii=False)}' + (', ' + ', '.join(self.expr(a) for a in args) if args else '') + ')'
        if self.lang == 'python':
            if not args: return json.dumps(raw.replace('%%', '%'), ensure_ascii=False)
            values = self.expr(args[0]) if len(args) == 1 else '(' + ', '.join(self.expr(a) for a in args) + ')'
            if len(args) == 1 and isinstance(args[0], Expr) and args[0].kind == 'array': values += ','
            return f'({json.dumps(raw, ensure_ascii=False)} % {values})'
        js_raw = raw.replace('%%', '%')
        js_args = []
        for spec, arg in zip(specs, args):
            value = self.expr(arg)
            if spec[-1] == 'c' and self._expr_type(arg, self.statement_envs.get(id(s), self.global_env)) == 'int': value = f'String.fromCharCode({value})'
            js_args.append(value)
        js_raw = re.sub(r'%(?:[-+0 #]*\d*(?:\.\d+)?)c', '%s', js_raw)
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
        env = self.statement_envs.get(id(s), getattr(self, '_active_env', self.global_env))
        formats = []
        values = []
        for arg in args:
            typ = self._expr_type(arg, env)
            if typ == 'string': formats.append('%s'); values.append(self.expr(arg))
            elif typ == 'char': formats.append('%c'); values.append(self.expr(arg))
            elif typ == 'int': formats.append('%d'); values.append(self.expr(arg))
            elif typ == 'double': formats.append('%g'); values.append(self.expr(arg))
            elif typ == 'bool':
                formats.append('%s')
                value = self.expr(arg)
                words = ('True', 'False') if self.source == 'python' else ('true', 'false')
                values.append(f'({value} ? "{words[0]}" : "{words[1]}")')
            elif typ in self.structs:
                formats.append('%p')
                values.append(f"&{self.expr(arg)}")
            else:
                name = arg.value if arg.kind == 'name' else 'expression'
                raise CompileError(f"cannot safely print {name!r} as C because its type cannot be inferred", arg.line, 'generation')
        self.emit('printf(' + json.dumps(" ".join(formats) + "\n") + ', ' + ', '.join(values) + ');')

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
        if self.source != 'c' or self.lang not in ('python', 'javascript'): return expression
        target_type = self._explicit_type(s.declared_type) or self.statement_envs.get(id(s), {}).get(s.value)
        if not target_type and s.exprs: target_type = self._expr_type(s.exprs[0], self.statement_envs.get(id(s), {}))
        value_type = self._expr_type(s.exprs[0], self.statement_envs.get(id(s), {})) if s.exprs else None
        if target_type == 'int' and value_type in ('double', 'bool'):
            return f'int({expression})' if self.lang == 'python' else f'Math.trunc({expression})'
        if target_type == 'bool' and value_type in ('int', 'double'):
            return f'bool({expression})' if self.lang == 'python' else f'Boolean({expression})'
        return expression

    def stmt(self, s):
        L = self.lang
        self._active_env = self.statement_envs.get(id(s), getattr(self, 'global_env', {}))

        if s.kind == 'group':
            for child in s.body: self.stmt(child)
            return

        if s.kind == 'import':
            mod = s.value
            if L == 'c':
                if mod in ('<math.h>', 'math.h', 'math'):
                    self.needs_math = True
                elif mod in ('<stdio.h>', '<stdlib.h>', '<stdbool.h>', 'stdio.h', 'stdlib.h', 'stdbool.h'):
                    pass
                elif mod.startswith('<') or mod.startswith('"'):
                    self.user_includes.append(f"#include {mod}")
                else:
                    self.user_includes.append(f'#include "{mod}.h"')
            elif L == 'python':
                if mod in ('<stdio.h>', '<stdlib.h>', '<stdbool.h>', 'stdio.h', 'stdlib.h', 'stdbool.h'):
                    pass
                elif mod in ('<math.h>', 'math.h', 'math'):
                    self.needs_math = True
                else:
                    clean = mod.replace('<', '').replace('>', '').replace('.h', '').strip('"\'')
                    if s.exprs:
                        items = ', '.join(c.value for c in s.exprs)
                        self.emit(f"from {clean} import {items}")
                    else:
                        self.emit(f"import {clean}")
            elif L == 'javascript':
                if mod not in ('<stdio.h>', '<stdlib.h>', '<stdbool.h>', '<math.h>', 'stdio.h', 'stdlib.h', 'stdbool.h', 'math.h', 'math'):
                    clean = mod.replace('<', '').replace('>', '').replace('.h', '').strip('"\'')
                    if s.exprs:
                        items = ', '.join(c.value for c in s.exprs)
                        self.emit(f"import {{ {items} }} from './{clean}.js';")
                    else:
                        self.emit(f"import * as {clean} from './{clean}.js';")
            return

        if s.kind in ('struct', 'class'):
            name = s.value
            fields = s.exprs
            methods = s.body
            if L == 'c':
                self.emit('typedef struct {')
                self.level += 1
                for f in fields:
                    f_name = f.value
                    f_type = f.declared_type or 'int'
                    if '[' in f_type:
                        base = f_type[:f_type.index('[')]
                        bracket = f_type[f_type.index('['):]
                        self.emit(f"{self._c_type(base, f.line, f_name)} {f_name}{bracket};")
                    else:
                        self.emit(f"{self._c_type(f_type, f.line, f_name)} {f_name};")
                self.level -= 1
                self.emit(f"}} {name};\n")
                # Methods become companion functions in C
                for m in methods:
                    m_name = m.value
                    orig_params = m.exprs[0].children if m.exprs else []
                    orig_types = m.exprs[0].value or []
                    # Filter out 'self' / 'this' if present, replace with (Student *s)
                    self_name = 's'
                    rest_params = orig_params[1:] if (orig_params and orig_params[0] in ('self', 'this')) else orig_params
                    rest_types = orig_types[1:] if (orig_types and orig_params and orig_params[0] in ('self', 'this')) else orig_types

                    rendered = [f"{name} *s"]
                    for idx, p_n in enumerate(rest_params):
                        p_t = rest_types[idx] if idx < len(rest_types) and rest_types[idx] else 'int'
                        rendered.append(f"{self._c_type(p_t, m.line, p_n)} {p_n}")
                    ret_type = self._c_type(m.declared_type or 'void', m.line, m_name)
                    c_fn_name = self.struct_method_names.get((name, m.value), m_name)
                    self.emit(f"{ret_type} {c_fn_name}({', '.join(rendered)}) {{")
                    old_env = getattr(self, '_active_env', {})
                    old_struct = getattr(self, '_current_struct', None)
                    self._current_struct = name
                    self._active_env = {'s': f"{name}*", 'self': f"{name}*", 'this': f"{name}*"}
                    self.suite(m.body)
                    self._active_env = old_env
                    self._current_struct = old_struct
                    self.emit('}\n')
            elif L == 'python':
                if not methods and getattr(s, 'declared_type', None) == 'dataclass':
                    self.emit('@dataclass')
                    self.emit(f'class {name}:')
                    self.level += 1
                    if not fields:
                        self.emit('pass')
                    for f in fields:
                        f_type = 'int' if not f.declared_type or 'int' in f.declared_type else ('str' if 'char' in f.declared_type or 'string' in f.declared_type else 'float')
                        self.emit(f"{f.value}: {f_type}")
                    self.level -= 1
                    self.emit('')
                else:
                    base_str = f"({s.declared_type})" if getattr(s, 'declared_type', None) else ""
                    self.emit(f'class {name}{base_str}:')
                    self.level += 1
                    field_names = [f.value for f in fields]
                    init_args = ['self']
                    for f in fields:
                        t = f.declared_type or ''
                        default_val = '0' if 'int' in t else ('0.0' if 'float' in t or 'double' in t else ('""' if 'char' in t or 'str' in t else 'None'))
                        init_args.append(f"{f.value}={default_val}")
                    self.emit(f"def __init__({', '.join(init_args)}):")
                    self.level += 1
                    base_name = getattr(s, 'declared_type', None)
                    if base_name and base_name in self.structs:
                        base_fields = [f.value for f in self.structs[base_name].exprs]
                        self.emit(f"super().__init__({', '.join(base_fields)})")
                        for f_name in field_names:
                            if f_name not in base_fields:
                                self.emit(f"self.{f_name} = {f_name}")
                    else:
                        if not field_names:
                            self.emit('pass')
                        for f_name in field_names:
                            self.emit(f"self.{f_name} = {f_name}")
                    self.level -= 1
                    self.emit('')
                    for m in methods:
                        m_name = m.value
                        m_params = ['self'] + [p for p in m.exprs[0].children if p not in ('self', 'this')]
                        self.emit(f"def {m_name}({', '.join(m_params)}):")
                        self.suite(m.body)
                        self.emit('')
                    self.level -= 1
            else:
                base_str = f" extends {s.declared_type}" if getattr(s, 'declared_type', None) else ""
                self.emit(f'class {name}{base_str} {{')
                self.level += 1
                field_names = [f.value for f in fields]
                init_args = []
                for f in fields:
                    t = f.declared_type or ''
                    default_val = '0' if 'int' in t else ('0.0' if 'float' in t or 'double' in t else ('""' if 'char' in t or 'str' in t else 'null'))
                    init_args.append(f"{f.value} = {default_val}")
                self.emit(f"constructor({', '.join(init_args)}) {{")
                self.level += 1
                base_name = getattr(s, 'declared_type', None)
                if base_name and base_name in self.structs:
                    base_fields = [f.value for f in self.structs[base_name].exprs]
                    self.emit(f"super({', '.join(base_fields)});")
                    for f_name in field_names:
                        if f_name not in base_fields:
                            self.emit(f"this.{f_name} = {f_name};")
                else:
                    for f_name in field_names:
                        self.emit(f"this.{f_name} = {f_name};")
                self.level -= 1
                self.emit('}')
                for m in methods:
                    m_name = m.value
                    m_params = [p for p in m.exprs[0].children if p not in ('self', 'this')]
                    self.emit(f"{m_name}({', '.join(m_params)}) {{")
                    self.suite(m.body)
                    self.emit('}')
                self.level -= 1
                self.emit('}\n')
            return

        if s.kind == 'member_assign':
            target_node = s.exprs[0]
            member = s.value
            op = s.declared_type or '='
            val = self.expr(s.exprs[1])
            if L == 'c':
                sep = '->' if (self._is_pointer(target_node) or (target_node.kind == 'name' and target_node.value in ('s', 'self', 'p', 'this'))) else '.'
                self.emit(f"{self.expr(target_node)}{sep}{member} {op} {val};")
            elif L == 'python':
                if target_node.kind == 'binary' and target_node.value == '+':
                    ptr_expr = self.expr(target_node.children[0])
                    idx_expr = self.expr(target_node.children[1])
                    self.emit(f"{ptr_expr}[{idx_expr}].{member} {op} {val}")
                else:
                    self.emit(f"{self.expr(target_node)}.{member} {op} {val}")
            else:
                if target_node.kind == 'binary' and target_node.value == '+':
                    ptr_expr = self.expr(target_node.children[0])
                    idx_expr = self.expr(target_node.children[1])
                    self.emit(f"{ptr_expr}[{idx_expr}].{member} {op} {val};")
                else:
                    self.emit(f"{self.expr(target_node)}.{member} {op} {val};")
            return

        if s.kind == 'deref_assign':
            target_node = s.exprs[0]
            val = self.expr(s.exprs[1])
            op = s.value or '='
            if L == 'c':
                if op in ('+=', '-=') and val == '1':
                    self.emit(f"(*{self.expr(target_node)})++;" if op == '+=' else f"(*{self.expr(target_node)})--;")
                else:
                    self.emit(f"*{self.expr(target_node)} {op} {val};")
            elif L == 'python':
                self.emit(f"{self.expr(target_node)}.value {op} {val}")
            else:
                if op in ('+=', '-=') and val == '1':
                    self.emit(f"{self.expr(target_node)}.value++;")
                else:
                    self.emit(f"{self.expr(target_node)}.value {op} {val};")
            return

        if s.kind == 'method_call':
            target_node = s.exprs[0]
            method = s.value
            args = [self.expr(x) for x in s.exprs[1:]]
            if L == 'c':
                if target_node.kind == 'call' and target_node.value == 'super':
                    current_st = self.structs.get(getattr(self, '_current_struct', None))
                    base_class = getattr(current_st, 'declared_type', None)
                    if base_class:
                        fn_name = self.struct_method_names.get((base_class, method), f"{base_class}_{method}")
                        call_args = [f"({base_class} *)s"] + args
                        self.emit(f"{fn_name}({', '.join(call_args)});")
                    return
                ref_target = self.expr(target_node)
                target_type = None
                if target_node.kind == 'name':
                    target_type = getattr(self, '_active_env', {}).get(target_node.value)
                if not target_type:
                    target_type = self._expr_type(target_node, getattr(self, '_active_env', {}))
                struct_name = target_type.rstrip('*').replace('struct ', '').strip() if target_type else None
                fn_name = method
                if struct_name and (struct_name, method) in self.struct_method_names:
                    fn_name = self.struct_method_names[(struct_name, method)]
                elif (getattr(self, '_current_struct', None), method) in self.struct_method_names:
                    fn_name = self.struct_method_names[(self._current_struct, method)]
                if not self._is_pointer(target_node):
                    ref_target = f"&{ref_target}"
                call_args = [ref_target] + args
                self.emit(f"{fn_name}({', '.join(call_args)});")
            elif L == 'python':
                if target_node.kind == 'call' and target_node.value == 'super':
                    self.emit(f"super().{method}({', '.join(args)})")
                else:
                    self.emit(f"{self.expr(target_node)}.{method}({', '.join(args)})")
            else:
                if target_node.kind == 'call' and target_node.value == 'super':
                    if method in ('__init__', 'constructor'):
                        self.emit(f"super({', '.join(args)});")
                    else:
                        self.emit(f"super.{method}({', '.join(args)});")
                else:
                    self.emit(f"{self.expr(target_node)}.{method}({', '.join(args)});")
            return

        if s.kind == 'decl':
            self.declared_in_scope.add(s.value)
            # Check if this variable is a scalar pointer-reference target
            if s.value in self.ref_vars:
                init_val = self.expr(s.exprs[0]) if s.exprs else '0'
                if L == 'python':
                    self.emit(f"{s.value} = IntReference({init_val})")
                elif L == 'javascript':
                    self.emit(f"let {s.value} = {{ value: {init_val} }};")
                else:
                    self.emit(f"int {s.value} = {init_val};")
                return

            # Struct declaration
            clean_type = (s.declared_type or '').replace('struct ', '').strip()
            is_struct = clean_type in self.structs or clean_type.rstrip('*') in self.structs
            if is_struct:
                is_ptr = '*' in clean_type
                struct_name = clean_type.rstrip('*')
                if L == 'c':
                    qualifier = 'const ' if s.declared_type == 'const' else ''
                    val = f' = {self.expr(s.exprs[0])}' if s.exprs else ''
                    ptr_star = ' *' if is_ptr else ' '
                    self.emit(f"{qualifier}{struct_name}{ptr_star}{s.value}{val};")
                elif L == 'python':
                    if is_ptr:
                        val = f' = {self.expr(s.exprs[0])}' if s.exprs else ' = None'
                    else:
                        val = f' = {self.expr(s.exprs[0])}' if s.exprs else f' = {struct_name}()'
                    self.emit(f"{s.value}{val}")
                else:
                    if is_ptr:
                        val = f' = {self.expr(s.exprs[0])}' if s.exprs else ' = null'
                    else:
                        val = f' = {self.expr(s.exprs[0])}' if s.exprs else f' = new {struct_name}()'
                    self.emit(f"let {s.value}{val};")
                return

            if L == 'python' and not s.exprs:
                self.emit(f'{s.value} = 0' if (s.declared_type in ('int', 'float', 'double')) else f'{s.value} = None')
                return
            val = f' = {self._assignment_value(s, self.expr(s.exprs[0]))}' if s.exprs else ''
            if L == 'python':
                self.emit(f'{s.value}{val}')
            elif L == 'c':
                qualifier = 'const ' if s.declared_type == 'const' else ''
                c_t = self._c_type(self._type_for(s.exprs[0] if s.exprs else None, s), s.line, s.value)
                self.emit(f'{qualifier}{c_t} {s.value}{val};')
            else:
                self.emit(("const" if s.declared_type == 'const' else "let") + f' {s.value}{val};')
            return

        elif s.kind == 'array_decl':
            self.declared_in_scope.add(s.value)
            arr = s.exprs[0]
            if not hasattr(self, '_array_literal_values'):
                self._array_literal_values = {}
            self._array_literal_values[s.value] = arr.children
            if L == 'c' and any(self._expr_type(child, getattr(self, '_active_env', {})) in self.structs or (child.kind == 'name' and getattr(self, '_active_env', {}).get(child.value) in self.structs) for child in arr.children):
                self.emit(f"/* {s.value} = [{', '.join(self.expr(x) for x in arr.children)}] */")
                return
            size = arr.value if arr.value is not None else len(arr.children)
            values_list = [self.expr(x) for x in arr.children]
            if L != 'c' and arr.value is not None: values_list.extend('0' for _ in range(max(0, size - len(values_list))))
            values = ', '.join(values_list)
            if L == 'c': self.emit(f'int {s.value}[{size}] = {{{values}}};' if values else f'int {s.value}[{size}] = {{0}};')
            else:
                prefix = '' if L == 'python' else ('const ' if s.declared_type == 'const' else 'let ')
                self.emit(prefix + f'{s.value} = [{values}]' + (';' if L != 'python' else ''))
        elif s.kind == 'assign':
            if s.exprs and hasattr(s.exprs[0], 'kind') and s.exprs[0].kind == 'array':
                if not hasattr(self, '_array_literal_values'):
                    self._array_literal_values = {}
                self._array_literal_values[s.value] = s.exprs[0].children
                if L == 'c' and any(self._expr_type(child, getattr(self, '_active_env', {})) in self.structs or (child.kind == 'name' and getattr(self, '_active_env', {}).get(child.value) in self.structs) for child in s.exprs[0].children):
                    self.emit(f"/* {s.value} = [{', '.join(self.expr(x) for x in s.exprs[0].children)}] */")
                    return
            value = self._assignment_value(s, self.expr(s.exprs[0]))
            target = s.value
            if L != 'c' and s.value in self.ref_vars:
                target = f"{s.value}.value"
            if L == 'c' and s.value not in self.declared_in_scope and s.value not in self.ref_params and s.value not in getattr(self, '_current_fn_params', set()):
                env = self.statement_envs.get(id(s), getattr(self, 'global_env', {}))
                typ = env.get(s.value) or self._expr_type(s.exprs[0], env)
                if typ:
                    self.declared_in_scope.add(s.value)
                    self.emit(f'{self._c_type(typ, s.line, s.value)} {target} = {value};')
                    return
            self.declared_in_scope.add(s.value)
            self.emit(f'{target} = {value}' + (';' if L != 'python' else ''))
        elif s.kind == 'array_assign':
            self.emit(f'{s.value}[{self.expr(s.exprs[0])}] = {self.expr(s.exprs[1])}' + (';' if L != 'python' else ''))
        elif s.kind == 'compound_assign':
            target = s.value
            if L != 'c' and s.value in self.ref_vars:
                target = f"{s.value}.value"
            self.emit(f'{target} {s.exprs[0].value} {self.expr(s.exprs[1])}' + (';' if L != 'python' else ''))
        elif s.kind == 'print':
            if L == 'c': self._c_print(s)
            elif s.value == 'printf':
                expression = self._printf(s)
                if L == 'python': self.emit(f'print({expression}, end="")')
                else: self.emit(expression + ';')
            elif L == 'python': self.emit('print(' + ', '.join(self.expr(x) for x in s.exprs) + ')')
            else: self.emit('console.log(' + ', '.join(self.expr(x) for x in s.exprs) + ');')
        elif s.kind in ('if', 'while'):
            self.blockhead(f'{s.kind} {"(" if L != "python" else ""}{self.expr(s.exprs[0])}{")" if L != "python" else ""}', s.body)
            if s.otherwise: self.blockhead('else', s.otherwise)
        elif s.kind == 'for':
            init, cond, step = s.exprs
            initval = self.expr(init.children[0])
            update = self.update(step)
            if L == 'python':
                self.emit(f'{s.value} = {initval}')
                body = list(s.body) + [self.update_stmt(s.value, step)]
                self.blockhead(f'while {self.expr(cond)}', body)
            else:
                prefix = ('let ' if L == 'javascript' and init.value is True else ('int ' if L == 'c' and init.value is True else ''))
                self.blockhead(f'for ({prefix}{s.value} = {initval}; {self.expr(cond)}; {update})', s.body)
        elif s.kind == 'for_in':
            var_name = s.value
            target = s.exprs[0]
            if L == 'python':
                self.blockhead(f"for {var_name} in {self.expr(target)}", s.body)
            elif L == 'javascript':
                self.blockhead(f"for (const {var_name} of {self.expr(target)})", s.body)
            else:
                elements = None
                if target.kind == 'name' and hasattr(self, '_array_literal_values') and target.value in self._array_literal_values:
                    elements = self._array_literal_values[target.value]
                elif target.kind == 'array':
                    elements = target.children
                if elements:
                    for elem in elements:
                        for b_stmt in s.body:
                            cloned = self._subst_node(b_stmt, var_name, elem)
                            self.stmt(cloned)
                else:
                    t_name = self.expr(target)
                    self.emit(f"for (int _i = 0; _i < sizeof({t_name}) / sizeof({t_name}[0]); _i++) {{")
                    self.level += 1
                    self.emit(f"int {var_name} = {t_name}[_i];")
                    for b_stmt in s.body:
                        self.stmt(b_stmt)
                    self.level -= 1
                    self.emit("}")
        elif s.kind == 'return':
            self.emit('return' + (' ' + self.expr(s.exprs[0]) if s.exprs else '') + (';' if L != 'python' else ''))
        elif s.kind == 'call':
            if s.value in ('free',):
                if L == 'c': self.emit(f"free({self.expr(s.exprs[0])});")
                return
            if s.value == 'scanf':
                if L == 'c':
                    rendered_args = [self.expr(a) for a in s.exprs]
                    self.emit(f"scanf({', '.join(rendered_args)});")
                    return
                elif L == 'python':
                    fmt = self.expr(s.exprs[0]) if s.exprs else '""'
                    for arg in s.exprs[1:]:
                        dest_node = arg.children[0] if arg.kind == 'address_of' else arg
                        dest_str = self.expr(dest_node)
                        if 'f' in fmt:
                            self.emit(f"{dest_str} = float(input())")
                        elif 'd' in fmt or 'i' in fmt:
                            self.emit(f"{dest_str} = int(input())")
                        else:
                            self.emit(f"{dest_str} = input()")
                    return
                else:
                    fmt = self.expr(s.exprs[0]) if s.exprs else '""'
                    for arg in s.exprs[1:]:
                        dest_node = arg.children[0] if arg.kind == 'address_of' else arg
                        dest_str = self.expr(dest_node)
                        if 'f' in fmt:
                            self.emit(f"{dest_str} = parseFloat(prompt() || '0');")
                        elif 'd' in fmt or 'i' in fmt:
                            self.emit(f"{dest_str} = parseInt(prompt() || '0', 10);")
                        else:
                            self.emit(f"{dest_str} = prompt() || '';")
                    return
            old_in_call = getattr(self, '_in_call_arg', False)
            self._in_call_arg = True
            rendered_args = []
            target_fn = self.function_nodes.get(s.value)
            fn_param_names = target_fn.exprs[0].children if target_fn else []
            fn_params = self.function_params.get(s.value, {})
            for idx, arg in enumerate(s.exprs):
                p_name = fn_param_names[idx] if idx < len(fn_param_names) else None
                expected_type = fn_params.get(p_name, '') if p_name else ''
                if L == 'c' and arg.kind == 'name' and (arg.value in self.ref_vars or (expected_type.endswith('*') and not self._is_pointer(arg))):
                    rendered_args.append(f"&{arg.value}")
                else:
                    rendered_args.append(self.expr(arg))
            self._in_call_arg = old_in_call
            self.emit(f"{self.function_name_map.get(s.value, s.value)}({', '.join(rendered_args)})" + (';' if L != 'python' else ''))
        elif s.kind == 'function':
            function_name = self.function_name_map.get(s.value, s.value)
            args = ', '.join(s.exprs[0].children)
            old_fn_params = getattr(self, '_current_fn_params', set())
            old_declared = set(self.declared_in_scope)
            self._current_fn_params = set(s.exprs[0].children)
            self.declared_in_scope = set(s.exprs[0].children)
            if L == 'python':
                self.blockhead(f'def {function_name}({args})', s.body)
            elif L == 'javascript':
                self.blockhead(f'function {function_name}({args})', s.body)
            else:
                param_types = s.exprs[0].value or []
                rendered = []
                for index, name in enumerate(s.exprs[0].children):
                    typ = self._explicit_type(param_types[index]) if index < len(param_types) else None
                    if not typ and (name in self.ref_params or name.startswith('p') or name == 'p'):
                        typ = 'int*'
                    typ = typ or self.function_params.get(s.value, {}).get(name)
                    rendered.append(f'{self._c_type(typ, s.line, name)} {name}')
                ret = self._explicit_type(s.declared_type) or self.function_returns.get(s.value)
                if s.value == 'main': ret = 'int'
                if not ret and any(self._contains_value_return(child) for child in s.body):
                    raise CompileError(f"cannot infer the return type of function {s.value!r} for C output", s.line, 'generation')
                if not ret: ret = 'void'
                c_return = 'void' if ret == 'void' else self._c_type(ret, s.line, s.value + ' return value')
                self.emit(f'{c_return} {function_name}({", ".join(rendered) if rendered else "void"}) {{')
                self.suite(s.body)
                if s.value == 'main' and not any(child.kind == 'return' for child in s.body): self.emit('    ' * (self.level + 1) + 'return 0;')
                self.emit('}')
            self._current_fn_params = old_fn_params
            self.declared_in_scope = old_declared

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
        c_functions = [s for s in p.body if s.kind == 'function']
        c_structs = [s for s in p.body if s.kind in ('struct', 'class')]
        has_c_entry = any(s.value == 'main' for s in c_functions)

        if self.lang == 'c':
            if self.source != 'c' and has_c_entry:
                self.function_name_map['main'] = 'multilang_main'

            # Emit structs and methods first
            for struct in c_structs:
                self.stmt(struct)

            if self.source == 'c' and has_c_entry:
                for stmt in p.body:
                    if stmt.kind not in ('struct', 'class'):
                        self.stmt(stmt)
                headers = ['#include <stdio.h>', '#include <stdbool.h>']
                if self.needs_stdlib or any(s.kind == 'decl' and s.declared_type and '*' in s.declared_type for s in p.body):
                    headers.append('#include <stdlib.h>')
                if self.needs_string or any(s.kind in ('struct', 'class') for s in p.body):
                    headers.append('#include <string.h>')
                if self.needs_math:
                    headers.append('#include <math.h>')
                headers.extend(self.user_includes)
                hdr_str = '\n'.join(dict.fromkeys(headers)) + '\n\n'
                return hdr_str + '\n'.join(self.lines) + '\n'

            # Non-C source translated to C: functions first, then main() wrapper
            for function in c_functions:
                self.stmt(function)
            helper_source = '\n'.join(self.lines)
            self.lines = []
            self.level = 1
            self.declared_in_scope = set()
            self._current_fn_params = set()
            for statement in p.body:
                if statement.kind not in ('function', 'struct', 'class'):
                    self.stmt(statement)
            body = '\n'.join(self.lines) + '\n'
            body += '    return 0;\n'

            headers = ['#include <stdio.h>', '#include <stdbool.h>']
            if self.needs_stdlib:
                headers.append('#include <stdlib.h>')
            if self.needs_string or c_structs:
                headers.append('#include <string.h>')
            if self.needs_math:
                headers.append('#include <math.h>')
            headers.extend(self.user_includes)
            hdr_str = '\n'.join(dict.fromkeys(headers)) + '\n\n'
            return hdr_str + (helper_source + '\n\n' if helper_source else '') + 'int main(void) {\n' + body + '}\n'

        # Target is Python or JavaScript
        prefix_lines = []
        if self.lang == 'python':
            if any(s.kind in ('struct', 'class') and getattr(s, 'declared_type', None) == 'dataclass' for s in p.body):
                prefix_lines.append('from dataclasses import dataclass')
            if self.needs_math:
                prefix_lines.append('import math')
            if self.ref_vars or self.ref_params:
                prefix_lines.append('class IntReference:\n    def __init__(self, value):\n        self.value = value\n')
            if prefix_lines:
                prefix_lines.append('')
        elif self.lang == 'javascript':
            pass

        self.lines = list(prefix_lines)
        for stmt in p.body:
            self.stmt(stmt)

        if self.source == 'c' and has_c_entry:
            if self.lang == 'python':
                self.emit('raise SystemExit(main())')
            else:
                self.emit('process.exitCode = main();')
        return '\n'.join(self.lines) + '\n'
