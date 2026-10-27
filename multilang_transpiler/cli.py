import argparse, json, pathlib, sys
from .parser import parse
from .semantic import analyze
from .ir import lower
from .codegen import generate
from .errors import CompileError
from .console import configure_console

def main(argv=None):
    configure_console()
    ap=argparse.ArgumentParser(prog='multilang-transpiler',description='Transpile the documented C/Python/JavaScript subset.')
    ap.add_argument('--from',dest='source',required=True,choices=['c','python','javascript'])
    ap.add_argument('--to',dest='target',required=True,choices=['c','python','javascript'])
    ap.add_argument('--input',required=True); ap.add_argument('--output',required=True)
    ap.add_argument('--dump',choices=['tokens','ast','ir'],help='print an intermediate representation to stderr')
    a=ap.parse_args(argv)
    try:
        source=pathlib.Path(a.input).read_text(encoding='utf-8'); p=parse(source,a.source); analyze(p,a.source)
        if a.dump=='tokens':
            from .lexer import tokenize
            print(json.dumps([t.__dict__ for t in tokenize(source,a.source)],indent=2),file=sys.stderr)
        elif a.dump=='ast': print(json.dumps(p,default=lambda x:x.__dict__,indent=2),file=sys.stderr)
        elif a.dump=='ir': print(json.dumps(lower(p),indent=2),file=sys.stderr)
        out=generate(lower(p),a.target); pathlib.Path(a.output).write_text(out,encoding='utf-8')
    except (OSError,CompileError,ValueError) as e:
        print(e,file=sys.stderr); return 1
    return 0

if __name__=='__main__': raise SystemExit(main())
