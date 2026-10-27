from .errors import CompileError


def analyze(program, language='c', detailed=False):
    functions = {}
    function_details = []
    symbols = []
    warnings = []
    arrays = set()
    pointers = set()
    classes = set()
    std_funcs = {'printf', 'println', 'malloc', 'realloc', 'free', 'sizeof', 'scanf', 'sqrt', 'pow', 'abs',
                 'sin', 'cos', 'tan', 'floor', 'ceil', 'len', 'range', 'int', 'float', 'str', 'math', 'Math', 'super'}

    def inferred_type(expression):
        if expression.kind == 'char': return 'char'
        if expression.kind == 'literal':
            value = expression.value
            if value in ('True', 'False', 'true', 'false'): return 'bool'
            if value in ('None', 'null', 'NULL'): return 'unknown'
            if isinstance(value, str) and value[:1] in ('"', "'"): return 'string'
            if isinstance(value, str) and value.replace('.', '', 1).isdigit(): return 'float' if '.' in value else 'int'
        if expression.kind == 'array': return 'int[]'
        if expression.kind == 'construct': return expression.value
        if expression.kind == 'dict': return 'dict'
        if expression.kind == 'binary':
            if expression.value in ('==', '!=', '<', '>', '<=', '>=', '&&', '||', 'and', 'or'): return 'bool'
            left = inferred_type(expression.children[0])
            right = inferred_type(expression.children[1])
            if expression.value == '+' and left == right == 'string': return 'string'
            if left in ('int', 'float') and right in ('int', 'float'):
                return 'float' if 'float' in (left, right) or expression.value == '/' else 'int'
        return None

    def record_symbol(name, declared_type, initializer, line, kind='variable'):
        if declared_type in ('let', 'var', 'const', None):
            inferred = inferred_type(initializer) if initializer else None
            shown_type = f'inferred {inferred}' if inferred else 'not inferred'
        else:
            shown_type = declared_type
        if kind == 'array': shown_type = 'int[]'
        symbols.append({'name': name, 'type': shown_type, 'kind': kind, 'line': line})

    def collect_declarations(stmts):
        for statement in stmts:
            if statement.kind == 'group':
                collect_declarations(statement.body)
            elif statement.kind in ('struct', 'class'):
                classes.add(statement.value)
                for method in statement.body:
                    if method.kind == 'function':
                        m_name = f"{statement.value}.{method.value}"
                        params = method.exprs[0].children if method.exprs else []
                        functions[m_name] = (len(params), method.line)
                continue
            elif statement.kind == 'function':
                if statement.value in functions:
                    raise CompileError(f"duplicate function definition {statement.value!r}", statement.line, 'semantic')
                parameters = statement.exprs[0].children if statement.exprs else []
                functions[statement.value] = (len(parameters), statement.line)
                parameter_types = statement.exprs[0].value or [] if statement.exprs else []
                function_details.append({
                    'name': statement.value,
                    'parameters': [{'name': name, 'type': parameter_types[index] if index < len(parameter_types) and parameter_types[index] else 'not declared in source'} for index, name in enumerate(parameters)],
                    'return_type': statement.declared_type or 'not declared in source',
                    'line': statement.line
                })
            collect_declarations(statement.body)
            collect_declarations(statement.otherwise)

    collect_declarations(program.body)

    def validate_call(name, argument_count, line):
        if name in std_funcs or name in classes:
            return
        if name not in functions:
            raise CompileError(f"call to unknown function {name!r}", line, 'semantic')
        expected, _ = functions[name]
        if argument_count != expected:
            raise CompileError(f"function {name!r} expects {expected} argument(s), got {argument_count}", line, 'semantic')

    def expr(e, scope):
        if not hasattr(e, 'kind'):
            return
        if e.kind == 'type':
            return
        if e.kind == 'name':
            if e.value not in scope and e.value not in ('self', 'this', 'NULL', 'null', 'None') and e.value not in classes and e.value not in std_funcs:
                raise CompileError(f"use of undeclared variable {e.value!r}", e.line, 'semantic')
        elif e.kind == 'index':
            if isinstance(e.value, str):
                if e.value not in scope and e.value not in ('self', 'this'):
                    raise CompileError(f"use of undeclared variable {e.value!r}", e.line, 'semantic')
                if e.value not in arrays and e.value not in pointers:
                    raise CompileError(f"variable {e.value!r} is not an array", e.line, 'semantic')
            elif hasattr(e.value, 'kind'):
                expr(e.value, scope)
        elif e.kind == 'call':
            validate_call(e.value, len(e.children), e.line)
        for c in e.children:
            if hasattr(c, 'kind'):
                expr(c, scope)

    def block(stmts, scope, consts=None):
        scope = set(scope)
        consts = set(consts or ())
        for s in stmts:
            if s.kind == 'import':
                scope.add(s.value)
                for item in s.exprs:
                    scope.add(item.value)
                continue
            if s.kind == 'group':
                block(s.body, scope, consts)
                scope.update(child.value for child in s.body if child.kind in ('decl', 'array_decl'))
                consts.update(child.value for child in s.body if child.declared_type == 'const')
                continue
            if s.kind in ('struct', 'class'):
                record_symbol(s.value, s.kind, None, s.line, kind='class')
                # analyze methods
                class_scope = {'self', 'this'}.union(f.value for f in s.exprs if f.kind == 'field')
                for m in s.body:
                    if m.kind == 'function':
                        m_scope = class_scope.union(m.exprs[0].children if m.exprs else [])
                        block(m.body, m_scope, set())
                continue
            if s.kind == 'field':
                continue
            if s.kind == 'print' and s.value == 'println':
                warnings.append(f"Line {s.line}: println is a MultiLang Transpiler output alias; use printf in standard C, print in Python, or console.log in JavaScript.")
            if s.kind in ('decl', 'array_decl'):
                if s.value in scope:
                    raise CompileError(f"redeclaration of {s.value!r}", s.line, 'semantic')
                scope.add(s.value)
                if s.kind == 'array_decl':
                    arrays.add(s.value)
                if s.declared_type and '*' in s.declared_type:
                    pointers.add(s.value)
                if s.declared_type == 'const':
                    consts.add(s.value)
                record_symbol(s.value, s.declared_type, s.exprs[0] if s.exprs else None, s.line, 'array' if s.kind == 'array_decl' else 'variable')
            elif s.kind == 'assign' and s.value in consts:
                raise CompileError(f"cannot assign to constant {s.value!r}", s.line, 'semantic')
            elif s.kind == 'assign' and s.value not in scope:
                if language == 'python':
                    scope.add(s.value)
                    if s.exprs and s.exprs[0].kind == 'array':
                        s.kind = 'array_decl'
                        arrays.add(s.value)
                    else:
                        s.kind = 'decl'
                    record_symbol(s.value, None, s.exprs[0] if s.exprs else None, s.line, 'array' if s.kind == 'array_decl' else 'variable')
                else:
                    raise CompileError(f"assignment to undeclared variable {s.value!r}", s.line, 'semantic')
            elif s.kind == 'array_assign':
                if s.value in consts:
                    raise CompileError(f"cannot assign to constant {s.value!r}", s.line, 'semantic')
                if s.value not in scope:
                    raise CompileError(f"assignment to undeclared variable {s.value!r}", s.line, 'semantic')
                if s.value not in arrays and s.value not in pointers:
                    raise CompileError(f"variable {s.value!r} is not an array", s.line, 'semantic')
            elif s.kind == 'member_assign':
                target = s.exprs[0]
                expr(target, scope)
                expr(s.exprs[1], scope)
                continue
            elif s.kind == 'deref_assign':
                target = s.exprs[0]
                expr(target, scope)
                expr(s.exprs[1], scope)
                continue
            elif s.kind == 'method_call':
                for e in s.exprs:
                    expr(e, scope)
                continue
            elif s.kind == 'compound_assign' and s.value in consts:
                raise CompileError(f"cannot assign to constant {s.value!r}", s.line, 'semantic')
            elif s.kind == 'compound_assign' and s.value not in scope:
                raise CompileError(f"assignment to undeclared variable {s.value!r}", s.line, 'semantic')
            if s.kind == 'for':
                init, condition, update = s.exprs
                loop_scope = set(scope)
                if init.value is True:
                    if s.value in loop_scope:
                        raise CompileError(f"redeclaration of {s.value!r}", s.line, 'semantic')
                    loop_scope.add(s.value)
                elif s.value not in loop_scope:
                    raise CompileError(f"assignment to undeclared variable {s.value!r}", s.line, 'semantic')
                for e in init.children:
                    expr(e, loop_scope)
                expr(condition, loop_scope)
                for e in update.children[1:]:
                    expr(e, loop_scope)
                block(s.body, loop_scope, consts)
                continue
            if s.kind == 'for_in':
                iter_target = s.exprs[0]
                expr(iter_target, scope)
                loop_scope = set(scope)
                loop_scope.add(s.value)
                block(s.body, loop_scope, consts)
                continue
            for e in s.exprs:
                expr(e, scope)
            if s.kind in ('if', 'while'):
                block(s.body, scope, consts)
                block(s.otherwise, scope, consts)
            elif s.kind == 'function':
                block(s.body, set(s.exprs[0].children), set())
            elif s.kind == 'call':
                validate_call(s.value, len(s.exprs), s.line)
                for e in s.exprs:
                    expr(e, scope)
        return scope

    block(program.body, set())
    if not detailed:
        return warnings
    return {
        'status': 'passed_with_warnings' if warnings else 'passed',
        'message': 'Supported name, declaration, array, constant, class, and function-call checks completed.',
        'checks': [
            'Variable reads and assignment targets follow the supported declaration rules.',
            'Duplicate declarations and duplicate function definitions are rejected.',
            'Array indexing is limited to variables recognized as arrays.',
            'Constant reassignment is rejected.',
            'Function calls must name a defined function and match its parameter count.',
        ],
        'symbols': symbols,
        'functions': function_details,
        'warnings': warnings,
        'not_checked': [
            'Complete type compatibility and implicit-conversion rules for each source language.',
            'Complete block-scope and data-flow analysis.',
            'Array bounds and function return-path completeness.',
        ],
    }
