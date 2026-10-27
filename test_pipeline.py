"""Standalone End-to-End Transpiler Pipeline Verification Script.

Tests the complete 3x3 bidirectional translation pipeline (C <-> Python <-> JavaScript)
using dynamic root discovery (no hardcoded paths), verifying semantic logic preservation,
pointer/reference handling, structs/classes, imports, and execution equivalence across
Python, GCC, and Node.js.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

# Dynamically locate project root (works regardless of directory or clone location)
CURRENT_FILE = pathlib.Path(__file__).resolve()
ROOT = CURRENT_FILE.parent
if not (ROOT / "multilang_transpiler").exists():
    ROOT = CURRENT_FILE.parents[1]
sys.path.insert(0, str(ROOT))

try:
    from multilang_transpiler.parser import parse
    from multilang_transpiler.semantic import analyze
    from multilang_transpiler.ir import lower
    from multilang_transpiler.codegen import generate
    from multilang_transpiler.transpiler_cli import main as cli_main
except ImportError as err:
    print(f"Error importing multilang_transpiler from {ROOT}: {err}", file=sys.stderr)
    sys.exit(1)

GCC = shutil.which("gcc") or shutil.which("cc") or shutil.which("clang")
NODE = shutil.which("node")
PYTHON = sys.executable


def transpile(source_code: str, source_lang: str, target_lang: str) -> str:
    """Run full pipeline: Source -> Parse -> AST -> Analyze -> Lower -> IR -> Generate -> Target."""
    ast = parse(source_code, source_lang)
    analyze(ast, source_lang)
    ir = lower(ast)
    return generate(ir, target_lang)


def run_python(code: str) -> str:
    res = subprocess.run([PYTHON, "-c", code], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Python execution failed:\n{res.stderr}\nCode:\n{code}")
    return res.stdout.strip()


def run_node(code: str) -> str:
    if not NODE:
        return "[NODE_UNAVAILABLE]"
    res = subprocess.run([NODE, "-e", code], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Node execution failed:\n{res.stderr}\nCode:\n{code}")
    return res.stdout.strip()


def run_c(code: str) -> str:
    if not GCC:
        return "[GCC_UNAVAILABLE]"
    with tempfile.TemporaryDirectory() as d:
        c_file = pathlib.Path(d) / "prog.c"
        exe_file = pathlib.Path(d) / ("prog.exe" if os.name == "nt" else "prog")
        c_file.write_text(code, encoding="utf-8")
        build = subprocess.run([GCC, str(c_file), "-o", str(exe_file)], capture_output=True, text=True)
        if build.returncode != 0:
            raise RuntimeError(f"GCC compilation failed:\n{build.stderr}\nCode:\n{code}")
        run = subprocess.run([str(exe_file)], capture_output=True, text=True)
        if run.returncode != 0:
            raise RuntimeError(f"C binary execution failed with code {run.returncode}:\n{run.stderr}")
        return run.stdout.strip()


def test_stage(name: str, fn):
    print(f"[*] Testing {name}...", end=" ", flush=True)
    try:
        fn()
        print("PASSED")
        return True
    except Exception as e:
        print("FAILED")
        print(f"    Error: {e}\n")
        return False


def main():
    print("=" * 65)
    print("MultiLang 3x3 Transpiler: Pipeline Verification")
    print(f"Project Root: {ROOT}")
    print(f"Python:       {PYTHON}")
    print(f"C Compiler:   {GCC or 'None (skipped runtime validation)'}")
    print(f"Node.js:      {NODE or 'None (skipped runtime validation)'}")
    print("=" * 65)

    all_passed = True

    # 1. Pointer & Mutation Pipeline
    def test_pointers():
        c_src = """#include <stdio.h>
void increment(int *p) {
    (*p)++;
}
int main() {
    int x = 10;
    increment(&x);
    printf("%d\\n", x);
    return 0;
}
"""
        c_out = run_c(c_src) if GCC else "11"
        py_code = transpile(c_src, "c", "python")
        js_code = transpile(c_src, "c", "javascript")

        py_out = run_python(py_code)
        assert py_out == "11", f"Python output mismatch: {py_out} != 11"

        if NODE:
            js_out = run_node(js_code)
            assert js_out == "11", f"JS output mismatch: {js_out} != 11"

    all_passed &= test_stage("Pointer & Mutation Translation (C -> Python -> JS)", test_pointers)

    # 2. Struct / Class & Member Access Pipeline
    def test_structs():
        c_src = """#include <stdio.h>
struct Student {
    int id;
    char name[50];
};
int main() {
    struct Student s = {101, "Anish"};
    printf("%d %s\\n", s.id, s.name);
    return 0;
}
"""
        py_code = transpile(c_src, "c", "python")
        js_code = transpile(c_src, "c", "javascript")

        py_out = run_python(py_code)
        assert py_out == "101 Anish", f"Python output mismatch: {py_out} != '101 Anish'"

        if NODE:
            js_out = run_node(js_code)
            assert js_out == "101 Anish", f"JS output mismatch: {js_out} != '101 Anish'"

    all_passed &= test_stage("Struct to Class Translation (C -> Python -> JS)", test_structs)

    # 3. JS Class with Methods to Python and C
    def test_js_class():
        js_src = """class Student {
    constructor(id, name) {
        this.id = id;
        this.name = name;
    }
    display() {
        console.log(this.id, this.name);
    }
}
let s = new Student(101, "Anish");
s.display();
"""
        py_code = transpile(js_src, "javascript", "python")
        c_code = transpile(js_src, "javascript", "c")

        py_out = run_python(py_code)
        assert py_out == "101 Anish", f"Python output mismatch: {py_out} != '101 Anish'"

        if GCC:
            c_out = run_c(c_code)
            assert c_out == "101 Anish", f"C output mismatch: {c_out} != '101 Anish'"

    all_passed &= test_stage("Class & Methods Translation (JS -> Python -> C)", test_js_class)

    # 4. Standard Library Imports (math / <math.h>)
    def test_imports():
        py_src = """import math
x = 16
root = math.sqrt(x)
print(root)
"""
        js_code = transpile(py_src, "python", "javascript")
        c_code = transpile(py_src, "python", "c")

        py_out = run_python(py_src)
        assert float(py_out) == 4.0

        if NODE:
            js_out = run_node(js_code)
            assert float(js_out) == 4.0

        if GCC:
            c_out = run_c(c_code)
            assert float(c_out) == 4.0

    all_passed &= test_stage("Standard Library Imports (Python -> JS -> C)", test_imports)

    # 5. CLI Verification
    def test_cli():
        with tempfile.TemporaryDirectory() as d:
            test_c = pathlib.Path(d) / "main.c"
            test_py = pathlib.Path(d) / "main.py"
            test_c.write_text('#include <stdio.h>\nint main() { printf("OK\\n"); return 0; }\n', encoding="utf-8")
            assert cli_main(["--version"]) == 0
            assert cli_main(["languages"]) == 0
            assert cli_main(["check", str(test_c)]) == 0
            assert cli_main(["inspect", str(test_c), "--ir"]) == 0
            assert cli_main(["translate", str(test_c), "--to", "python", "-o", str(test_py)]) == 0
            assert test_py.exists()
            assert "print" in test_py.read_text(encoding="utf-8")

    all_passed &= test_stage("CLI Pipeline Subcommands (--version, check, inspect, translate)", test_cli)

    print("=" * 65)
    if all_passed:
        print("[SUCCESS] All pipeline stages passed successfully!")
        sys.exit(0)
    else:
        print("[FAILURE] One or more pipeline stages failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
