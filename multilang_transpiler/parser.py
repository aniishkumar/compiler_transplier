"""Parser for the documented shared subset. C/JS use braces; Python uses indentation."""
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

    @property
    def t(self): return self.ts[self.i]

    def take(self, v=None):
        t = self.t
        if v is not None and ((v in ('INDENT', 'DEDENT') and t.kind != v) or (v not in ('INDENT', 'DEDENT') and t.value != v)):
            raise CompileError(f"expected {v!r}, got {t.value!r}", t.line, 'syntax')
        self.i += 1
        return t

    def accept(self, v):
        if (self.t.kind == v if v in ('INDENT', 'DEDENT') else self.t.value == v): return self.take()
        return None

    def skipnl(self):
        while self.t.kind == 'NEWLINE' or self.t.value == ';': self.take()

    def program(self):
        body=[]; self.skipnl()
        while self.t.kind != 'EOF':
            body.append(self.stmt()); self.skipnl()
        return Program(body, source_language=self.lang)

    def block(self):
        if self.lang == 'python':
            self.take(':'); self.skipnl(); self.take('INDENT'); body=[]
            while self.t.kind not in ('DEDENT', 'EOF'):
                body.append(self.stmt()); self.skipnl()
            self.accept('DEDENT'); return body
        self.take('{'); self.skipnl(); body=[]
        while self.t.value != '}' and self.t.kind != 'EOF': body.append(self.stmt()); self.skipnl()
        self.take('}'); return body

    def _array_decl(self, name, line, declared_type='int'):
        if declared_type not in ('int', 'let', 'const', 'var'):
            raise CompileError('only integer arrays are supported', line, 'syntax')
        self.take('[')
        size_tok = self.take()
        if size_tok.kind != 'NUMBER' or '.' in size_tok.value:
            raise CompileError('array size must be a non-negative integer literal', size_tok.line, 'syntax')
        size = int(size_tok.value)
        self.take(']')
        values=[]
        if self.accept('='):
            self.take('{')
            if self.t.value != '}':
                while True:
                    values.append(self.expr())
                    if not self.accept(','): break
            self.take('}')
        self.accept(';')
        if values and len(values) > size: raise CompileError('array initializer has more values than its declared size', line, 'syntax')
        return Stmt('array_decl', name, [Expr('array', size, values, line)], line=line, declared_type=declared_type)

    def parse_arguments(self, closing):
        args=[]
        if self.t.value==closing: return args
        while True:
            args.append(self.expr())
            if not self.accept(','): break
            if self.t.value==closing: break  # Python and JavaScript allow a trailing comma.
        return args

    def stmt(self):
        t=self.t; v=t.value
        if v in ('def','function') or (v in ('int','void','float','double','char','bool') and self.i+2 < len(self.ts) and self.ts[self.i+2].value == '('):
            return_type = v if v not in ('def','function') else None
            self.take(); name=self.take().value; self.take('('); params=[]; param_types=[]
            while self.t.value != ')':
                if self.t.value == 'void' and self.ts[self.i+1].value == ')':
                    self.take(); break
                param_type=None
                if self.t.value in ('int','float','double','string','char','bool'):
                    param_type=self.take().value
                params.append(self.take().value); param_types.append(param_type)
                if not self.accept(','): break
            self.take(')'); body=self.block()
            return Stmt('function', name, [Expr('params', value=param_types, children=params, line=t.line)], body, line=t.line, declared_type=return_type)
        if v in ('int','float','double','char','bool','string','let','const','var'):
            declared_type=self.take().value; declarations=[]
            while True:
                name=self.take().value
                if self.t.value == '[':
                    if declarations: raise CompileError('array declarations cannot be combined with other declarators',t.line,'syntax')
                    return self._array_decl(name,t.line,declared_type)
                exprs=[]
                if self.accept('='):
                    e=self.expr(); exprs=[e]
                    kind='array_decl' if e.kind=='array' else 'decl'
                else:
                    if declared_type=='const' and self.lang=='javascript':
                        raise CompileError('const declarations require an initializer',t.line,'syntax')
                    kind='decl'
                declarations.append(Stmt(kind,name,exprs,line=t.line,declared_type=declared_type))
                if not self.accept(','): break
            self.accept(';')
            return declarations[0] if len(declarations)==1 else Stmt('group',body=declarations,line=t.line)
        if v == 'for':
            if self.lang == 'python': return self.python_for()
            return self.for_stmt()
        if v in ('print','println','console'):
            self.take(); style='println' if v=='println' else ('console.log' if v=='console' else 'print')
            if v=='console': self.take('.'); self.take('log')
            self.take('('); args=self.parse_arguments(')')
            self.take(')'); self.accept(';')
            return Stmt('print',value=style,exprs=args,line=t.line)
        if v == 'printf':
            self.take(); self.take('(')
            if self.t.value == ')': raise CompileError('printf requires a format string argument',t.line,'syntax')
            fmt=self.take()
            if fmt.kind != 'STRING': raise CompileError('printf format must be a string literal',fmt.line,'syntax')
            args=[Expr('literal',fmt.value,line=fmt.line)]
            if self.accept(','):
                if self.t.value==')': raise CompileError('printf has a trailing comma without an argument',self.t.line,'syntax')
                args.extend(self.parse_arguments(')'))
            self.take(')'); self.accept(';'); return Stmt('print',value='printf',exprs=args,line=t.line)
        if v in ('if','while'):
            self.take(); par=bool(self.accept('(')); cond=self.expr()
            if par: self.take(')')
            body=self.block(); other=[]
            if v=='if':
                if self.lang!='python': self.skipnl()
                if self.accept('elif'):
                    elif_token=self.ts[self.i-1]; elif_cond=self.expr(); elif_body=self.block()
                    nested=Stmt('if',exprs=[elif_cond],body=elif_body,line=elif_token.line)
                    other=[nested]
                    if self.lang!='python': self.skipnl()
                    if self.accept('else'): nested.otherwise=self.block()
                elif self.accept('else'):
                    if self.t.value=='if': other=[self.stmt()]
                    else: other=self.block()
            return Stmt(v,exprs=[cond],body=body,otherwise=other,line=t.line)
        if v == 'return':
            self.take(); exprs=[] if self.t.value in (';','}') or self.t.kind in ('NEWLINE','DEDENT','EOF') else [self.expr()]
            self.accept(';'); return Stmt('return',exprs=exprs,line=t.line)
        if self.t.kind in ('IDENT','KEYWORD'):
            name=self.take().value
            if self.t.value == '[':
                self.take(); idx=self.expr(); self.take(']')
                op=self.take()
                if op.value not in ('=','+=','-=','*=','/='): raise CompileError('expected assignment after array index',op.line,'syntax')
                rhs=self.expr(); self.accept(';')
                if op.value != '=': rhs=Expr('binary',op.value[0],[Expr('index',name,[idx],t.line),rhs],op.line)
                return Stmt('array_assign',name,[idx,rhs],line=t.line)
            op=self.t.value
            if op in ('=','+=','-=','*=','/='):
                self.take(); rhs=self.expr(); self.accept(';')
                return Stmt('assign' if op=='=' else 'compound_assign',name,[rhs] if op=='=' else [Expr('operator',op,line=t.line),rhs],line=t.line)
            if self.accept('('):
                args=self.parse_arguments(')')
                self.take(')'); self.accept(';'); return Stmt('call',name,args,line=t.line)
            raise CompileError('expected assignment or function call',t.line,'syntax')
        raise CompileError(f"unsupported statement starting with {v!r}",t.line,'syntax')

    def for_stmt(self):
        t=self.take('for'); self.take('(')
        declared = self.t.value in ('int','float','double','let','const','var')
        if declared: self.take()
        name=self.take().value; self.take('='); init=self.expr(); self.take(';')
        cond=self.expr(); self.take(';')
        step_name=self.take().value
        if self.t.value in ('++','--'):
            op=self.take().value; step=Expr('update',op,[Expr('name',step_name,line=t.line)],t.line)
        elif self.t.value in ('+=','-='):
            op=self.take().value; amount=self.expr(); step=Expr('update',op,[Expr('name',step_name,line=t.line),amount],t.line)
        else:
            self.take('='); value=self.expr(); step=Expr('update','=',[Expr('name',step_name,line=t.line),value],t.line)
        if step_name != name: raise CompileError('for-loop initializer and update must use the same variable',t.line,'syntax')
        self.take(')'); body=self.block()
        return Stmt('for',name,[Expr('for_init',declared,[init],t.line),cond,step],body,line=t.line)

    def python_for(self):
        self.take('for'); t=self.take(); name=t.value; self.take('in'); self.take('range'); self.take('('); args=[]
        if self.t.value != ')':
            while True:
                args.append(self.expr())
                if not self.accept(','): break
        self.take(')')
        if len(args)==1: start=Expr('literal','0',line=t.line); stop=args[0]
        elif len(args)==2: start,stop=args
        else: raise CompileError('range() supports one or two arguments in this subset',t.line,'syntax')
        body=self.block()
        return Stmt('for',name,[Expr('for_init',True,[start],t.line),Expr('binary','<',[Expr('name',name,line=t.line),stop],t.line),Expr('update','++',[Expr('name',name,line=t.line)],t.line)],body,line=t.line)

    def expr(self,minp=0):
        t=self.take()
        if t.value in ('-','!','not'): left=Expr('unary',t.value,[self.expr(7)],t.line)
        elif t.value=='(': left=self.expr(); self.take(')')
        elif t.value=='[':
            items=[]
            if self.t.value != ']':
                while True:
                    items.append(self.expr())
                    if not self.accept(','): break
            self.take(']'); left=Expr('array',None,items,t.line)
        elif t.kind == 'NUMBER' or t.value in ('True','False','true','false','null','None'): left=Expr('literal',t.value,line=t.line)
        elif t.kind == 'STRING': left=Expr('char' if self.lang=='c' and t.value.startswith("'") else 'literal',t.value,line=t.line)
        elif t.kind in ('IDENT','KEYWORD'):
            if self.accept('('):
                args=self.parse_arguments(')')
                self.take(')'); left=Expr('call',t.value,args,t.line)
            else:left=Expr('name',t.value,line=t.line)
        else: raise CompileError(f"expected expression, got {t.value!r}",t.line,'syntax')
        while self.t.value == '[':
            self.take(); index=self.expr(); self.take(']')
            if left.kind != 'name': raise CompileError('only named one-dimensional arrays are supported',t.line,'syntax')
            left=Expr('index',left.value,[index],t.line)
        prec={'or':0,'||':0,'and':1,'&&':1,'==':2,'!=':2,'<':2,'>':2,'<=':2,'>=':2,'+':3,'-':3,'*':4,'/':4,'%':4}
        while self.t.value in prec and prec[self.t.value]>=minp:
            op=self.take(); p=prec[op.value]; right=self.expr(p+1); left=Expr('binary',op.value,[left,right],op.line)
        return left


def parse(source,language):
    if language not in ('c','python','javascript'): raise CompileError(f'unknown language {language!r}')
    return Parser(source,language).program()
