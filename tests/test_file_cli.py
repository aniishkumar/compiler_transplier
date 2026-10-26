"""Single-file CLI tests use isolated temporary input and output paths."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from multilang_transpiler.file_conversion import ConversionError, choose_output_path, convert_file, infer_language
from multilang_transpiler.errors import CompileError
from multilang_transpiler.validation import validate_generated

SAMPLES = {
    "c": '#include <stdio.h>\nint main(void) { int n = 2; printf("%d\\n", n + 3); return 0; }\n',
    "python": "n = 2\nprint(n + 3)\n",
    "javascript": "let n = 2; console.log(n + 3);\n",
}
EXTENSIONS = {"c": ".c", "python": ".py", "javascript": ".js"}


class FileConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def input_file(self, name="main.py", content=None):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if content is not None else SAMPLES["python"], encoding="utf-8")
        return path

    def test_language_inference_and_unknown_extension(self):
        self.assertEqual(infer_language("HELLO.PYW"), "python")
        self.assertEqual(infer_language("some.mjs"), "javascript")
        with self.assertRaisesRegex(ConversionError, "cannot infer"):
            infer_language("program.txt")

    def test_all_nine_routes_write_correct_code_and_extension(self):
        for source_language, source in SAMPLES.items():
            input_path = self.input_file(f"{source_language}/calculator{EXTENSIONS[source_language]}", source)
            for target in SAMPLES:
                with self.subTest(source=source_language, target=target):
                    result = convert_file(input_path, target,
                                          output_dir=str(self.root / "out" / source_language / target))
                    expected = self.root / "out" / source_language / target / f"calculator{EXTENSIONS[target]}"
                    self.assertEqual(result["output"], expected.absolute())
                    self.assertTrue(expected.is_file())
                    self.assertTrue(expected.read_text(encoding="utf-8").strip())

    def test_explicit_from_custom_output_and_unicode_filename(self):
        source = self.input_file("my code/計算 機.txt", SAMPLES["python"])
        target = self.root / "custom output" / "converted.js"
        target.parent.mkdir()
        result = convert_file(source, "javascript", source_language="python", output=str(target))
        self.assertEqual(result["output"], target.absolute())
        self.assertIn("console.log", target.read_text(encoding="utf-8"))

    def test_output_dir_created_and_stem_preserved(self):
        source = self.input_file("my calculator.py")
        result = convert_file(source, "javascript", output_dir=str(self.root / "created" / "dir"))
        self.assertEqual(result["output"].name, "my calculator.js")
        self.assertTrue(result["output"].exists())

    def test_missing_file_unsupported_language_and_compiler_error(self):
        with self.assertRaisesRegex(ConversionError, "does not exist"):
            convert_file(self.root / "missing.py", "c")
        unknown = self.input_file("source.txt")
        with self.assertRaisesRegex(ConversionError, "cannot infer"):
            convert_file(unknown, "c")
        invalid = self.input_file("broken.py", "print(unknown + )\n")
        with self.assertRaises(CompileError):
            convert_file(invalid, "javascript")

    def test_generated_syntax_validates_on_each_route(self):
        for source_language, source in SAMPLES.items():
            input_path = self.input_file(f"syntax-{source_language}{EXTENSIONS[source_language]}", source)
            for target in SAMPLES:
                with self.subTest(source=source_language, target=target):
                    generated = convert_file(input_path, target,
                                             output_dir=str(self.root / "syntax" / source_language / target))["code"]
                    checked = validate_generated(target, generated)
                    self.assertNotEqual(checked["status"], "failed", checked)

    def test_existing_output_force_and_source_protection(self):
        source = self.input_file("main.py")
        saved = source.read_bytes()
        destination = self.root / "main.js"
        destination.write_text("old data", encoding="utf-8")
        with self.assertRaisesRegex(ConversionError, "already exists"):
            convert_file(source, "javascript", cwd=self.root)
        convert_file(source, "javascript", cwd=self.root, force=True)
        self.assertNotEqual(destination.read_text(encoding="utf-8"), "old data")
        self.assertEqual(source.read_bytes(), saved)
        same_language = convert_file(source, "python", cwd=self.root)
        self.assertEqual(same_language["output"].name, "main_converted.py")
        with self.assertRaisesRegex(ConversionError, "input file"):
            convert_file(source, "javascript", output=str(source), force=True)

    def test_cli_prints_written_output_and_check_status(self):
        source = self.input_file("cli demo.py")
        result = subprocess.run([sys.executable, "-m", "multilang_transpiler.project_cli", "convert",
                                 str(source), "--to", "javascript", "--check",
                                 "--output-dir", str(self.root / "cli-output")], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Conversion successful", result.stdout)
        self.assertTrue((self.root / "cli-output" / "cli demo.js").exists())

    def test_empty_source_uses_compilers_actual_behavior(self):
        source = self.input_file("empty.py", "")
        result = convert_file(source, "javascript", cwd=self.root)
        self.assertEqual(result["code"], "\n")
        self.assertTrue(result["output"].exists())


if __name__ == "__main__":
    unittest.main()
