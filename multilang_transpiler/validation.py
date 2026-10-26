"""Static syntax validation for generated source; never execute programs."""
import ast
from pathlib import Path
import shutil
import subprocess
import tempfile


def validate_generated(target, code):
    """Return a structured syntax-check result for generated code."""
    if target == "python":
        try:
            ast.parse(code)
            return {"status": "passed", "tool": "Python AST parser", "message": "Generated Python syntax is valid."}
        except SyntaxError as exc:
            return {"status": "failed", "tool": "Python AST parser", "message": exc.msg, "line": exc.lineno, "column": exc.offset}

    tool = shutil.which("node") if target == "javascript" else (
        shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    )
    if not tool:
        return {"status": "unavailable", "tool": None,
                "message": f"No {target} syntax-check tool is installed; generated code was not executed."}

    suffix = ".js" if target == "javascript" else ".c"
    with tempfile.TemporaryDirectory(prefix="multilang-check-") as temp_dir:
        path = Path(temp_dir) / ("generated" + suffix)
        path.write_text(code, encoding="utf-8")
        command = [tool, "--check", str(path)] if target == "javascript" else [tool, "-fsyntax-only", str(path)]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
        except subprocess.TimeoutExpired:
            return {"status": "failed", "tool": Path(tool).name,
                    "message": "Syntax checker timed out after 8 seconds."}
        if result.returncode:
            message = (result.stderr or result.stdout).strip()[-2000:]
            return {"status": "failed", "tool": Path(tool).name, "message": message}
        return {"status": "passed", "tool": Path(tool).name,
                "message": f"Generated {target} syntax is valid; program was not executed."}

