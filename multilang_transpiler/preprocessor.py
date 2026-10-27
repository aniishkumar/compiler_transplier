"""Minimal C preprocessing: preserve supported standard includes and reject directives."""
import re
from .errors import CompileError

_INCLUDE = re.compile(r'^\s*#\s*include\s*[<"]([a-zA-Z0-9_./\-]+)[>"]\s*(?://.*)?$')

def preprocess(source, language):
    for n, line in enumerate(source.splitlines(), 1):
        if line.lstrip().startswith('```'):
            raise CompileError('Markdown code fences are not source code; remove the opening and closing ``` lines and paste only the program', n, 'preprocessing')
    if language != 'c':
        return source
    lines = []
    for n, line in enumerate(source.splitlines(), 1):
        if line.lstrip().startswith('#'):
            if not _INCLUDE.match(line):
                raise CompileError('only standard header #include directives are supported', n, 'preprocessing')
            lines.append('')  # preserve subsequent source line numbers
        else:
            lines.append(line)
    return '\n'.join(lines) + ('\n' if source.endswith('\n') else '')
