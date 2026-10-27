"""Comprehensive automated tests for 3x3 bidirectional transpiler (C, Python, JavaScript).
Verifies semantic logic preservation, execution flow, structs/classes, pointers/references,
imports, and all six translation directions with Python, GCC, and Node.js.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from multilang_transpiler.parser import parse
from multilang_transpiler.semantic import analyze
from multilang_transpiler.ir import lower
from multilang_transpiler.codegen import generate
from multilang_transpiler.transpiler_cli import main as cli_main

GCC = shutil.which("gcc") or shutil.which("cc")
NODE = shutil.which("node")


class BidirectionalTranspilerTests(unittest.TestCase):

    def transpile(self, source_code: str, source_lang: str, target_lang: str) -> str:
        program = parse(source_code, source_lang)
        analyze(program, source_lang)
        ir_payload = lower(program)
        return generate(ir_payload, target_lang)

    def execute_c(self, code: str) -> str:
        if not GCC:
            self.skipTest("GCC compiler not installed")
        with tempfile.TemporaryDirectory(prefix="transpiler_c_") as d:
            c_file = pathlib.Path(d) / "prog.c"
            exe_file = pathlib.Path(d) / "prog.exe"
            c_file.write_text(code, encoding="utf-8")
            build = subprocess.run([GCC, str(c_file), "-o", str(exe_file)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, f"GCC build failed:\n{build.stderr}\nCode:\n{code}")
            run = subprocess.run([str(exe_file)], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, f"Execution failed:\n{run.stderr}")
            return run.stdout.replace('\r\n', '\n')

    def execute_python(self, code: str) -> str:
        run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, f"Python execution failed:\n{run.stderr}\nCode:\n{code}")
        return run.stdout.replace('\r\n', '\n')

    def execute_js(self, code: str) -> str:
        if not NODE:
            self.skipTest("Node.js not installed")
        run = subprocess.run([NODE, "-e", code], capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, f"Node.js execution failed:\n{run.stderr}\nCode:\n{code}")
        return run.stdout.replace('\r\n', '\n')

    # =========================================================================
    # TEST 1: C Pointer -> Python Reference -> JS Object Reference (Section 9)
    # =========================================================================
    def test_1_c_pointer_mutation_to_python_and_javascript(self):
        c_source = """#include <stdio.h>

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
        c_output = self.execute_c(c_source)
        self.assertEqual(c_output.strip(), "11")

        # 1. Translate C -> Python
        py_code = self.transpile(c_source, "c", "python")
        self.assertIn("IntReference", py_code)
        self.assertIn("p.value += 1", py_code)
        py_output = self.execute_python(py_code)
        self.assertEqual(py_output.strip(), "11")

        # 2. Translate C -> JavaScript
        js_code = self.transpile(c_source, "c", "javascript")
        self.assertIn("value", js_code)
        js_output = self.execute_js(js_code)
        self.assertEqual(js_output.strip(), "11")

        # Verify semantic output equivalence
        self.assertEqual(c_output.strip(), py_output.strip())
        self.assertEqual(py_output.strip(), js_output.strip())

    # =========================================================================
    # TEST 2: C Struct -> Python Class/Dataclass -> JavaScript Class (Section 9)
    # =========================================================================
    def test_2_c_struct_to_python_and_javascript(self):
        c_source = """#include <stdio.h>

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
        c_output = self.execute_c(c_source)
        self.assertEqual(c_output.strip(), "101 Anish")

        # C -> Python
        py_code = self.transpile(c_source, "c", "python")
        self.assertIn("class Student", py_code)
        py_output = self.execute_python(py_code)
        self.assertEqual(py_output.strip(), "101 Anish")

        # C -> JavaScript
        js_code = self.transpile(c_source, "c", "javascript")
        self.assertIn("class Student", js_code)
        self.assertIn("constructor", js_code)
        js_output = self.execute_js(js_code)
        self.assertEqual(js_output.strip(), "101 Anish")

        self.assertEqual(c_output.strip(), py_output.strip())
        self.assertEqual(py_output.strip(), js_output.strip())

    # =========================================================================
    # TEST 3: JavaScript Class -> Python Class -> C Struct + Companion Functions
    # =========================================================================
    def test_3_javascript_class_to_python_and_c(self):
        js_source = """class Student {
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
        js_output = self.execute_js(js_source)
        self.assertEqual(js_output.strip(), "101 Anish")

        # JS -> Python
        py_code = self.transpile(js_source, "javascript", "python")
        self.assertIn("class Student", py_code)
        self.assertIn("def display", py_code)
        py_output = self.execute_python(py_code)
        self.assertEqual(py_output.strip(), "101 Anish")

        # JS -> C (struct + companion function display(Student *s))
        c_code = self.transpile(js_source, "javascript", "c")
        self.assertIn("typedef struct", c_code)
        self.assertIn("void display(Student *s)", c_code)
        self.assertIn("s->id", c_code)
        c_output = self.execute_c(c_code)
        self.assertEqual(c_output.strip(), "101 Anish")

        self.assertEqual(js_output.strip(), py_output.strip())
        self.assertEqual(py_output.strip(), c_output.strip())

    # =========================================================================
    # TEST 4: Python Class -> C Struct + Functions -> JavaScript Class
    # =========================================================================
    def test_4_python_class_to_c_and_javascript(self):
        py_source = """class Student:
    def __init__(self, id, name):
        self.id = id
        self.name = name

    def display(self):
        print(self.id, self.name)

s = Student(101, "Anish")
s.display()
"""
        py_output = self.execute_python(py_source)
        self.assertEqual(py_output.strip(), "101 Anish")

        # Python -> C
        c_code = self.transpile(py_source, "python", "c")
        self.assertIn("typedef struct", c_code)
        self.assertIn("void display(Student *s)", c_code)
        c_output = self.execute_c(c_code)
        self.assertEqual(c_output.strip(), "101 Anish")

        # Python -> JS
        js_code = self.transpile(py_source, "python", "javascript")
        self.assertIn("class Student", js_code)
        self.assertIn("this.id = id", js_code)
        js_output = self.execute_js(js_code)
        self.assertEqual(js_output.strip(), "101 Anish")

        self.assertEqual(py_output.strip(), c_output.strip())
        self.assertEqual(c_output.strip(), js_output.strip())

    # =========================================================================
    # TEST 5: Imports across all languages (math, sqrt, abs)
    # =========================================================================
    def test_5_imports_math_across_all_languages(self):
        py_source = """import math

x = 16
root = math.sqrt(x)
print(root)
"""
        py_output = self.execute_python(py_source)
        self.assertEqual(float(py_output.strip()), 4.0)

        # Python -> C (includes <math.h>)
        c_code = self.transpile(py_source, "python", "c")
        self.assertIn("#include <math.h>", c_code)
        self.assertIn("sqrt(x)", c_code)
        c_output = self.execute_c(c_code)
        self.assertEqual(float(c_output.strip()), 4.0)

        # Python -> JS (Math.sqrt)
        js_code = self.transpile(py_source, "python", "javascript")
        self.assertIn("Math.sqrt", js_code)
        js_output = self.execute_js(js_code)
        self.assertEqual(float(js_output.strip()), 4.0)

    # =========================================================================
    # TEST 6: All Six Translation Directions Matrix
    # =========================================================================
    def test_6_all_six_directions(self):
        routes = [
            ("c", "python"),
            ("c", "javascript"),
            ("python", "c"),
            ("python", "javascript"),
            ("javascript", "c"),
            ("javascript", "python"),
        ]

        c_base = "#include <stdio.h>\nint add(int a, int b) { return a + b; }\nint main() { printf(\"%d\\n\", add(7, 8)); return 0; }\n"
        py_base = "def add(a, b):\n    return a + b\nprint(add(7, 8))\n"
        js_base = "function add(a, b) { return a + b; }\nconsole.log(add(7, 8));\n"

        sources = {"c": c_base, "python": py_base, "javascript": js_base}

        for src_lang, tgt_lang in routes:
            with self.subTest(source=src_lang, target=tgt_lang):
                src_code = sources[src_lang]
                target_code = self.transpile(src_code, src_lang, tgt_lang)
                self.assertTrue(len(target_code.strip()) > 0)

                # Execute target and verify result is 15
                if tgt_lang == "python":
                    out = self.execute_python(target_code)
                elif tgt_lang == "javascript":
                    out = self.execute_js(target_code)
                else:
                    out = self.execute_c(target_code)

                self.assertEqual(out.strip(), "15", f"Failed route {src_lang} -> {tgt_lang}")

    # =========================================================================
    # TEST 7: Complex Mixed Program (Structs, Methods, Functions, Control Flow)
    # =========================================================================
    def test_7_complex_mixed_program(self):
        py_source = """class Account:
    def __init__(self, id, balance):
        self.id = id
        self.balance = balance

    def deposit(self, amount):
        self.balance = self.balance + amount

def process(a, bonus):
    a.deposit(bonus)

acc = Account(1001, 500)
process(acc, 250)
if acc.balance > 600:
    print(acc.id, acc.balance)
"""
        py_output = self.execute_python(py_source)
        self.assertEqual(py_output.strip(), "1001 750")

        # Translate to C
        c_code = self.transpile(py_source, "python", "c")
        c_output = self.execute_c(c_code)
        self.assertEqual(c_output.strip(), "1001 750")

        # Translate to JS
        js_code = self.transpile(py_source, "python", "javascript")
        js_output = self.execute_js(js_code)
        self.assertEqual(js_output.strip(), "1001 750")

    # =========================================================================
    # TEST 8: Professional CLI Subcommands
    # =========================================================================
    def test_8_cli_interface(self):
        with tempfile.TemporaryDirectory() as d:
            src_file = pathlib.Path(d) / "main.c"
            out_file = pathlib.Path(d) / "out.py"
            src_file.write_text("#include <stdio.h>\nint main() { printf(\"%d\\n\", 42); return 0; }\n", encoding="utf-8")

            # 1. Version
            ret = cli_main(["--version"])
            self.assertEqual(ret, 0)

            # 2. Languages
            ret = cli_main(["languages"])
            self.assertEqual(ret, 0)

            # 3. Check
            ret = cli_main(["check", str(src_file)])
            self.assertEqual(ret, 0)

            # 4. Inspect --ast
            ret = cli_main(["inspect", str(src_file), "--ast"])
            self.assertEqual(ret, 0)

            # 5. Inspect --ir
            ret = cli_main(["inspect", str(src_file), "--ir"])
            self.assertEqual(ret, 0)

            # 6. Translate
            ret = cli_main(["translate", str(src_file), "--to", "python", "-o", str(out_file)])
            self.assertEqual(ret, 0)
            self.assertTrue(out_file.exists())
            self.assertIn("print", out_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
