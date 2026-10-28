"""Lower the source AST into a small, operation-oriented, language-neutral IR."""
from .ast_nodes import Expr, Stmt, Program


def _expr(node):
    if node.kind in ('literal', 'char'):
        return {'op': 'CONSTANT', 'literal_kind': node.kind, 'value': node.value, 'line': node.line}
    if node.kind == 'name':
        return {'op': 'READ_VARIABLE', 'name': node.value, 'line': node.line}
    if node.kind == 'binary':
        return {'op': 'BINARY_OPERATION', 'operator': node.value,
                'left': _expr(node.children[0]), 'right': _expr(node.children[1]), 'line': node.line}
    if node.kind == 'unary':
        return {'op': 'UNARY_OPERATION', 'operator': node.value,
                'operand': _expr(node.children[0]), 'line': node.line}
    if node.kind == 'call':
        return {'op': 'CALL', 'function': node.value,
                'arguments': [_expr(child) for child in node.children], 'line': node.line}
    if node.kind == 'array':
        return {'op': 'ARRAY_LITERAL', 'size': node.value,
                'elements': [_expr(child) for child in node.children], 'line': node.line}
    if node.kind == 'index':
        return {'op': 'READ_INDEX', 'array': node.value,
                'index': _expr(node.children[0]), 'line': node.line}
    if node.kind == 'update':
        return {'op': 'UPDATE', 'operator': node.value,
                'operands': [_expr(child) for child in node.children], 'line': node.line}
    if node.kind == 'for_init':
        return {'op': 'INITIALIZE_LOOP_VARIABLE', 'declares_variable': bool(node.value),
                'value': _expr(node.children[0]), 'line': node.line}
    if node.kind == 'operator':
        return {'op': 'OPERATOR', 'operator': node.value, 'line': node.line}
    if node.kind == 'params':
        return {'op': 'PARAMETERS', 'names': list(node.children),
                'types': list(node.value or []), 'line': node.line}
    if node.kind == 'member':
        return {'op': 'READ_MEMBER', 'target': _expr(node.children[0]), 'member': node.value, 'line': node.line}
    if node.kind == 'method_call':
        return {'op': 'METHOD_CALL', 'target': _expr(node.children[0]), 'method': node.value,
                'arguments': [_expr(child) for child in node.children[1:]], 'line': node.line}
    if node.kind == 'address_of':
        return {'op': 'ADDRESS_OF', 'operand': _expr(node.children[0]), 'line': node.line}
    if node.kind == 'deref':
        return {'op': 'DEREFERENCE', 'operand': _expr(node.children[0]), 'line': node.line}
    if node.kind == 'construct':
        return {'op': 'CONSTRUCT_OBJECT', 'class_name': node.value,
                'arguments': [_expr(child) for child in node.children], 'line': node.line}
    if node.kind == 'dict':
        return {'op': 'DICT_LITERAL',
                'entries': [{'key': child.value, 'value': _expr(child.children[0])} for child in node.children], 'line': node.line}
    if node.kind == 'pair':
        return {'op': 'PAIR', 'key': node.value, 'value': _expr(node.children[0]), 'line': node.line}
    if node.kind == 'cast':
        return {'op': 'CAST', 'type': node.value, 'operand': _expr(node.children[0]), 'line': node.line}
    if node.kind == 'type':
        return {'op': 'TYPE', 'value': node.value, 'line': node.line}
    return {'op': node.kind.upper(), 'value': node.value,
            'children': [_expr(child) for child in node.children if isinstance(child, Expr)], 'line': node.line}


def _stmt(node):
    line = node.line
    if node.kind == 'group':
        return {'op': 'SEQUENCE', 'instructions': [_stmt(child) for child in node.body], 'line': line}
    if node.kind in ('decl', 'array_decl'):
        return {'op': 'DECLARE_ARRAY' if node.kind == 'array_decl' else 'DECLARE_VARIABLE',
                'name': node.value, 'type': node.declared_type,
                'initializer': _expr(node.exprs[0]) if node.exprs else None, 'line': line}
    if node.kind in ('struct', 'class'):
        fields = [_stmt(f) for f in node.exprs] if node.exprs else []
        methods = [_stmt(m) for m in node.body] if node.body else []
        return {'op': 'DECLARE_STRUCT', 'name': node.value, 'is_class': node.kind == 'class',
                'base_class': getattr(node, 'declared_type', None),
                'fields': fields, 'methods': methods, 'line': line}
    if node.kind == 'field':
        return {'op': 'FIELD', 'name': node.value, 'type': node.declared_type,
                'default': _expr(node.exprs[0]) if node.exprs else None, 'line': line}
    if node.kind == 'assign':
        return {'op': 'ASSIGN_VARIABLE', 'name': node.value, 'value': _expr(node.exprs[0]), 'line': line}
    if node.kind == 'compound_assign':
        return {'op': 'COMPOUND_ASSIGN', 'name': node.value,
                'operator': node.exprs[0].value, 'value': _expr(node.exprs[1]), 'line': line}
    if node.kind == 'member_assign':
        return {'op': 'WRITE_MEMBER', 'target': _expr(node.exprs[0]), 'member': node.value,
                'operator': node.declared_type or '=', 'value': _expr(node.exprs[1]), 'line': line}
    if node.kind == 'deref_assign':
        return {'op': 'WRITE_DEREF', 'target': _expr(node.exprs[0]),
                'operator': node.value or '=', 'value': _expr(node.exprs[1]), 'line': line}
    if node.kind == 'method_call':
        return {'op': 'METHOD_CALL_STATEMENT', 'target': _expr(node.exprs[0]), 'method': node.value,
                'arguments': [_expr(child) for child in node.exprs[1:]], 'line': line}
    if node.kind == 'import':
        return {'op': 'IMPORT', 'module': node.value,
                'names': [child.value for child in node.exprs] if node.exprs else [],
                'alias': node.declared_type, 'line': line}
    if node.kind == 'array_assign':
        return {'op': 'WRITE_INDEX', 'array': node.value, 'index': _expr(node.exprs[0]),
                'value': _expr(node.exprs[1]), 'line': line}
    if node.kind == 'print':
        return {'op': 'OUTPUT', 'style': node.value,
                'arguments': [_expr(child) for child in node.exprs], 'line': line}
    if node.kind == 'if':
        return {'op': 'BRANCH', 'condition': _expr(node.exprs[0]),
                'then': [_stmt(child) for child in node.body],
                'else': [_stmt(child) for child in node.otherwise], 'line': line}
    if node.kind == 'while':
        return {'op': 'LOOP_WHILE', 'condition': _expr(node.exprs[0]),
                'body': [_stmt(child) for child in node.body], 'line': line}
    if node.kind == 'for':
        return {'op': 'LOOP_FOR', 'variable': node.value,
                'initializer': _expr(node.exprs[0]), 'condition': _expr(node.exprs[1]),
                'update': _expr(node.exprs[2]), 'body': [_stmt(child) for child in node.body], 'line': line}
    if node.kind == 'for_in':
        return {'op': 'LOOP_FOR_IN', 'variable': node.value,
                'target': _expr(node.exprs[0]),
                'body': [_stmt(child) for child in node.body], 'line': line}
    if node.kind == 'function':
        params = node.exprs[0]
        types = list(params.value or [])
        return {'op': 'FUNCTION', 'name': node.value, 'return_type': node.declared_type,
                'parameters': [{'name': name, 'type': types[index] if index < len(types) else None}
                                for index, name in enumerate(params.children)],
                'body': [_stmt(child) for child in node.body], 'line': line}
    if node.kind == 'return':
        return {'op': 'RETURN', 'value': _expr(node.exprs[0]) if node.exprs else None, 'line': line}
    if node.kind == 'call':
        return {'op': 'CALL_STATEMENT', 'function': node.value,
                'arguments': [_expr(child) for child in node.exprs], 'line': line}
    return {'op': node.kind.upper(), 'value': node.value,
            'expressions': [_expr(child) for child in node.exprs],
            'body': [_stmt(child) for child in node.body],
            'otherwise': [_stmt(child) for child in node.otherwise], 'line': line}


def lower(program):
    """Build version 2 IR: named operations and operands, distinct from AST nodes."""
    return {'ir_version': 2, 'source_language': program.source_language,
            'body': [_stmt(statement) for statement in program.body]}


def _restore_expr(data):
    op = data['op']
    line = data.get('line', 1)
    if op == 'CONSTANT': return Expr(data.get('literal_kind', 'literal'), data.get('value'), line=line)
    if op == 'READ_VARIABLE': return Expr('name', data['name'], line=line)
    if op == 'BINARY_OPERATION': return Expr('binary', data['operator'], [_restore_expr(data['left']), _restore_expr(data['right'])], line)
    if op == 'UNARY_OPERATION': return Expr('unary', data['operator'], [_restore_expr(data['operand'])], line)
    if op == 'CALL': return Expr('call', data['function'], [_restore_expr(arg) for arg in data['arguments']], line)
    if op == 'ARRAY_LITERAL': return Expr('array', data.get('size'), [_restore_expr(arg) for arg in data['elements']], line)
    if op == 'READ_INDEX': return Expr('index', data['array'], [_restore_expr(data['index'])], line)
    if op == 'UPDATE': return Expr('update', data['operator'], [_restore_expr(arg) for arg in data['operands']], line)
    if op == 'INITIALIZE_LOOP_VARIABLE': return Expr('for_init', data['declares_variable'], [_restore_expr(data['value'])], line)
    if op == 'OPERATOR': return Expr('operator', data['operator'], line=line)
    if op == 'PARAMETERS': return Expr('params', data.get('types', []), list(data.get('names', [])), line)
    if op == 'READ_MEMBER': return Expr('member', data['member'], [_restore_expr(data['target'])], line)
    if op == 'METHOD_CALL': return Expr('method_call', data['method'], [_restore_expr(data['target'])] + [_restore_expr(a) for a in data['arguments']], line)
    if op == 'ADDRESS_OF': return Expr('address_of', None, [_restore_expr(data['operand'])], line)
    if op == 'DEREFERENCE': return Expr('deref', None, [_restore_expr(data['operand'])], line)
    if op == 'CONSTRUCT_OBJECT': return Expr('construct', data['class_name'], [_restore_expr(a) for a in data['arguments']], line)
    if op == 'DICT_LITERAL': return Expr('dict', None, [Expr('pair', e['key'], [_restore_expr(e['value'])], line) for e in data.get('entries', [])], line)
    if op == 'PAIR': return Expr('pair', data['key'], [_restore_expr(data['value'])], line)
    if op == 'CAST':
        operand = _restore_expr(data['operand']) if 'operand' in data else (_restore_expr(data['children'][0]) if data.get('children') else None)
        return Expr('cast', data.get('type') or data.get('value'), [operand] if operand else [], line)
    if op == 'TYPE': return Expr('type', data.get('value'), line=line)
    raise ValueError(f'unknown IR expression operation {op!r}')


def _restore_stmt(data):
    op = data['op']
    line = data.get('line', 1)
    if op == 'SEQUENCE': return Stmt('group', body=[_restore_stmt(child) for child in data['instructions']], line=line)
    if op in ('DECLARE_VARIABLE', 'DECLARE_ARRAY'):
        initializer = [_restore_expr(data['initializer'])] if data.get('initializer') is not None else []
        return Stmt('array_decl' if op == 'DECLARE_ARRAY' else 'decl', data['name'], initializer, line=line, declared_type=data.get('type'))
    if op == 'DECLARE_STRUCT':
        fields = [_restore_stmt(f) for f in data.get('fields', [])]
        methods = [_restore_stmt(m) for m in data.get('methods', [])]
        kind = 'class' if data.get('is_class') else 'struct'
        return Stmt(kind, data['name'], exprs=fields, body=methods, line=line, declared_type=data.get('base_class'))
    if op == 'FIELD':
        exprs = [_restore_expr(data['default'])] if data.get('default') is not None else []
        return Stmt('field', data['name'], exprs=exprs, line=line, declared_type=data.get('type'))
    if op == 'ASSIGN_VARIABLE': return Stmt('assign', data['name'], [_restore_expr(data['value'])], line=line)
    if op == 'COMPOUND_ASSIGN': return Stmt('compound_assign', data['name'], [Expr('operator', data['operator'], line=line), _restore_expr(data['value'])], line=line)
    if op == 'WRITE_MEMBER':
        return Stmt('member_assign', data['member'], [_restore_expr(data['target']), _restore_expr(data['value'])], line=line, declared_type=data.get('operator', '='))
    if op == 'WRITE_DEREF':
        return Stmt('deref_assign', data.get('operator', '='), [_restore_expr(data['target']), _restore_expr(data['value'])], line=line)
    if op == 'METHOD_CALL_STATEMENT':
        return Stmt('method_call', data['method'], [_restore_expr(data['target'])] + [_restore_expr(a) for a in data['arguments']], line=line)
    if op == 'IMPORT':
        names = [Expr('name', n, line=line) for n in data.get('names', [])]
        return Stmt('import', data['module'], exprs=names, line=line, declared_type=data.get('alias'))
    if op == 'WRITE_INDEX': return Stmt('array_assign', data['array'], [_restore_expr(data['index']), _restore_expr(data['value'])], line=line)
    if op == 'OUTPUT': return Stmt('print', data.get('style'), [_restore_expr(arg) for arg in data['arguments']], line=line)
    if op == 'BRANCH': return Stmt('if', exprs=[_restore_expr(data['condition'])], body=[_restore_stmt(child) for child in data['then']], otherwise=[_restore_stmt(child) for child in data['else']], line=line)
    if op == 'LOOP_WHILE': return Stmt('while', exprs=[_restore_expr(data['condition'])], body=[_restore_stmt(child) for child in data['body']], line=line)
    if op == 'LOOP_FOR': return Stmt('for', data['variable'], [_restore_expr(data['initializer']), _restore_expr(data['condition']), _restore_expr(data['update'])], [_restore_stmt(child) for child in data['body']], line=line)
    if op == 'LOOP_FOR_IN': return Stmt('for_in', data['variable'], [_restore_expr(data['target'])], [_restore_stmt(child) for child in data['body']], line=line)
    if op == 'FUNCTION':
        params = Expr('params', [param.get('type') for param in data['parameters']], [param['name'] for param in data['parameters']], line)
        return Stmt('function', data['name'], [params], [_restore_stmt(child) for child in data['body']], line=line, declared_type=data.get('return_type'))
    if op == 'RETURN': return Stmt('return', exprs=[_restore_expr(data['value'])] if data.get('value') is not None else [], line=line)
    if op == 'CALL_STATEMENT': return Stmt('call', data['function'], [_restore_expr(arg) for arg in data['arguments']], line=line)
    if op == 'TRY': return Stmt('try', None, body=[_restore_stmt(child) for child in data.get('body', [])], otherwise=[_restore_stmt(child) for child in data.get('otherwise', [])], line=line)
    raise ValueError(f'unknown IR statement operation {op!r}')


def restore(ir):
    """Reconstruct AST nodes for the existing target generators to consume."""
    if not isinstance(ir, dict): raise ValueError('IR must be an object')
    if ir.get('ir_version') == 1:
        # Retain compatibility for previously serialized AST-shaped IR payloads.
        def legacy_expr(data):
            children=[legacy_expr(child) if isinstance(child,dict) and 'kind' in child else child for child in data.get('children',[])]
            return Expr(data['kind'],data.get('value'),children,data.get('line',1))
        def legacy_stmt(data):
            return Stmt(data['kind'],data.get('value'),[legacy_expr(expr) for expr in data.get('exprs',[])],
                        [legacy_stmt(child) for child in data.get('body',[])],
                        [legacy_stmt(child) for child in data.get('otherwise',[])],data.get('line',1),data.get('declared_type'))
        return Program([legacy_stmt(statement) for statement in ir.get('body',[])],source_language=ir.get('source_language'))
    if ir.get('ir_version') != 2: raise ValueError('unsupported IR version')
    return Program([_restore_stmt(statement) for statement in ir.get('body', [])], source_language=ir.get('source_language'))
