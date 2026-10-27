import re
from dataclasses import dataclass
from .errors import CompileError

@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int

_PATTERN = re.compile(r'''(?P<SPACE>[ \t]+)|(?P<BLOCK_COMMENT>/\*[\s\S]*?\*/)|(?P<COMMENT>//[^\n]*|\#[^\n]*)|(?P<STRING>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(?P<NUMBER>\d+(?:\.\d+)?)|(?P<ID>[A-Za-z_$][A-Za-z0-9_$]*)|(?P<OP>==|!=|<=|>=|\+=|-=|\*=|/=|\+\+|--|&&|\|\||->|[+*/%<>=!&|^-])|(?P<PUNCT>[(){}\[\],;:.])|(?P<NEWLINE>\n)|(?P<BAD>.)''')
KEYWORDS = set('int float double char bool void string let const var if else elif while for function def return print println True False true false null None and or not struct class typedef new this self import from as export sizeof malloc free try catch except finally throw raise pass'.split())

def tokenize(source: str, language='c'):
    out=[]; line=1; at_start=True; indents=[0]
    for m in _PATTERN.finditer(source):
        k,v=m.lastgroup,m.group()
        if language=='python' and at_start and k not in ('SPACE','NEWLINE','COMMENT'):
            col=0
            while len(indents)>1 and col<indents[-1]: indents.pop(); out.append(Token('DEDENT','',line))
            if col!=indents[-1]: raise CompileError('inconsistent indentation',line,'lexical')
            at_start=False
        if k=='NEWLINE': out.append(Token('NEWLINE','\n',line)); line+=1; at_start=True
        elif k=='SPACE':
            if language=='python' and at_start:
                # Tabs are rejected to keep indentation deterministic.
                if '\t' in v: raise CompileError('tabs are not supported for indentation',line,'lexical')
                remainder=source[m.end():source.find('\n',m.end()) if source.find('\n',m.end())!=-1 else len(source)]
                if not remainder.strip() or remainder.lstrip().startswith('#'): continue
                col=len(v)
                if col>indents[-1]: indents.append(col); out.append(Token('INDENT','',line))
                elif col<indents[-1]:
                    while len(indents)>1 and col<indents[-1]: indents.pop(); out.append(Token('DEDENT','',line))
                    if col!=indents[-1]: raise CompileError('inconsistent indentation',line,'lexical')
                at_start=False
            continue
        elif k=='COMMENT': continue
        elif k=='BLOCK_COMMENT':
            line += v.count('\n')
        elif k == 'BAD':
            if language == 'python' and v == '@':
                out.append(Token('PUNCT', '@', line))
                at_start = False
                continue
            raise CompileError(f"unexpected character {v!r}", line, 'lexical')
        elif k=='ID': out.append(Token('KEYWORD' if v in KEYWORDS else 'IDENT',v,line)); at_start=False
        else: out.append(Token(k,v,line)); at_start=False
    while len(indents)>1: indents.pop(); out.append(Token('DEDENT','',line))
    out.append(Token('EOF','',line)); return out
