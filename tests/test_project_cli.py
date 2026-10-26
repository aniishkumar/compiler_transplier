"""Temporary-fixture tests for the project-migration CLI."""
import pathlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from multilang_transpiler.project_migration import MigrationError, migrate_project


SAMPLES = {
    "c": '#include <stdio.h>\nint main(void) { int n = 2; printf("%d\\n", n + 3); return 0; }\n',
    "python": "n = 2\nprint(n + 3)\n",
    "javascript": "let n = 2; console.log(n + 3);\n",
}


class ProjectMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)
        self.project = self.base / "source project"
        self.project.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, content):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def migrate(self, source="python", target="javascript", **kwargs):
        return migrate_project(self.project, source, target, **kwargs)

    def test_cli_help_version_languages(self):
        for args, expected in [
            (["--help"], "migrate"), (["--version"], "multilang"), (["languages"], "all nine"),
            (["migrate", "--help"], "--dry-run"),
        ]:
            result = subprocess.run([sys.executable, "-m", "multilang_transpiler.project_cli", *args],
                                    cwd=ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(expected, result.stdout.lower())

    def test_cli_migration_exit_codes(self):
        self.write("main.py", SAMPLES["python"])
        output = self.base / "cli output"
        command = [sys.executable, "-m", "multilang_transpiler.project_cli", "migrate", str(self.project),
                   "--from", "python", "--to", "javascript", "--output", str(output)]
        success = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertIn("Migration completed: SUCCESS", success.stdout)

        partial_project = self.base / "partial"
        partial_project.mkdir()
        (partial_project / "main.py").write_text(SAMPLES["python"], encoding="utf-8")
        (partial_project / "unknown.ts").write_text("let value: number = 2", encoding="utf-8")
        partial_command = [sys.executable, "-m", "multilang_transpiler.project_cli", "migrate", str(partial_project),
                           "--from", "python", "--to", "javascript", "--output", str(self.base / "partial-output")]
        partial = subprocess.run(partial_command,
                                 cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(partial.returncode, 1, partial.stdout)

        invalid = subprocess.run([sys.executable, "-m", "multilang_transpiler.project_cli", "migrate", str(self.project),
                                  "--from", "ruby", "--to", "javascript"],
                                 cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(invalid.returncode, 2)

    def test_single_file_migration_and_zip_integrity(self):
        original = self.write("hello.py", SAMPLES["python"])
        original_bytes = original.read_bytes()
        result = self.migrate()
        output_file = result["output"] / "hello.js"
        self.assertTrue(output_file.exists())
        self.assertIn("console.log", output_file.read_text())
        self.assertEqual(original.read_bytes(), original_bytes)
        self.assertTrue((result["output"] / "migration-report.md").exists())
        with zipfile.ZipFile(result["archive"]) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn("hello.js", archive.namelist())
            self.assertNotIn("source project/hello.js", archive.namelist())

    def test_nested_unicode_paths_and_spaces_are_preserved(self):
        self.write("source folder/深い/hello world.py", SAMPLES["python"])
        result = self.migrate()
        self.assertTrue((result["output"] / "source folder/深い/hello world.js").exists())

    def test_non_source_assets_and_original_readme_are_preserved(self):
        self.write("hello.py", SAMPLES["python"])
        self.write("README.md", "Original instructions.\n")
        self.write("assets/data file.txt", "sample data\n")
        result = self.migrate()
        self.assertIn("Original instructions.", (result["output"] / "README.original.md").read_text())
        self.assertIn("migrated from **python**", (result["output"] / "README.md").read_text())
        self.assertEqual((result["output"] / "assets/data file.txt").read_text(), "sample data\n")
        self.assertEqual(len(result["copied"]), 2)

    def test_unsupported_source_is_skipped_and_migration_is_partial(self):
        self.write("ok.py", SAMPLES["python"])
        self.write("legacy.ts", "const x: number = 1;\n")
        result = self.migrate()
        self.assertEqual(result["status"], "PARTIAL SUCCESS")
        self.assertEqual(len(result["translated"]), 1)
        self.assertIn("legacy.ts", result["skipped"][0]["path"])
        self.assertIn("not enabled", result["skipped"][0]["reason"])

    def test_compiler_error_is_reported_and_other_files_continue(self):
        self.write("good.py", SAMPLES["python"])
        self.write("bad.py", "print(unknown + )\n")
        result = self.migrate()
        self.assertEqual(result["status"], "PARTIAL SUCCESS")
        self.assertEqual(len(result["translated"]), 1)
        self.assertEqual(result["failed"][0]["path"], "bad.py")
        self.assertTrue(result["failed"][0]["phase"])

    def test_dry_run_lists_work_without_writing(self):
        self.write("nested/one.py", SAMPLES["python"])
        self.write("notes.txt", "asset")
        result = self.migrate(dry_run=True)
        self.assertEqual(result["status"], "DRY RUN")
        self.assertEqual(len(result["translations"]), 1)
        self.assertEqual(len(result["resources"]), 1)
        self.assertFalse(result["output"].exists())
        self.assertFalse(result["archive"].exists())

    def test_custom_output_and_archive(self):
        self.write("main.py", SAMPLES["python"])
        output = self.base / "build" / "converted project"
        archive = self.base / "dist" / "converted.zip"
        result = self.migrate(output_dir=output, archive_path=archive)
        self.assertEqual(result["output"], output.resolve())
        self.assertEqual(result["archive"], archive.resolve())
        self.assertTrue(output.is_dir())
        self.assertTrue(archive.is_file())

    def test_existing_destinations_require_explicit_overwrite(self):
        self.write("main.py", SAMPLES["python"])
        output = self.base / "existing output"
        archive = self.base / "existing.zip"
        output.mkdir()
        (output / "keep.txt").write_text("old", encoding="utf-8")
        archive.write_text("old archive", encoding="utf-8")
        with self.assertRaisesRegex(MigrationError, "already exists"):
            self.migrate(output_dir=output, archive_path=archive)
        result = self.migrate(output_dir=output, archive_path=archive, overwrite=True)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertFalse((output / "keep.txt").exists())
        with zipfile.ZipFile(archive) as zf:
            self.assertIsNone(zf.testzip())

    def test_default_destination_uses_unique_name(self):
        self.write("main.py", SAMPLES["python"])
        (self.base / "source project_migrated").mkdir()
        result = self.migrate()
        self.assertTrue(result["output"].name.endswith("_2"))

    def test_invalid_and_empty_projects_are_rejected(self):
        with self.assertRaisesRegex(MigrationError, "Cannot access"):
            migrate_project(self.base / "missing", "python", "javascript")
        with self.assertRaisesRegex(MigrationError, "empty"):
            self.migrate()

    def test_no_matching_source_files_is_rejected(self):
        self.write("README.md", "only docs")
        with self.assertRaisesRegex(MigrationError, "No source files"):
            self.migrate()

    def test_output_and_archive_cannot_overlap_input_or_each_other(self):
        self.write("main.py", SAMPLES["python"])
        with self.assertRaisesRegex(MigrationError, "separate from the input"):
            self.migrate(output_dir=self.project / "out")
        with self.assertRaisesRegex(MigrationError, "outside the input"):
            self.migrate(archive_path=self.project / "inside.zip")
        with self.assertRaisesRegex(MigrationError, "outside the migrated project"):
            self.migrate(output_dir=self.base / "out", archive_path=self.base / "out" / "inside.zip")

    def test_custom_exclusion_and_default_cache_exclusions(self):
        self.write("main.py", SAMPLES["python"])
        self.write("excluded.py", SAMPLES["python"])
        self.write("vendor/ignore.py", SAMPLES["python"])
        self.write("__pycache__/cached.py", SAMPLES["python"])
        result = self.migrate(excludes=["vendor/**", "excluded.py"])
        self.assertEqual(result["status"], "PARTIAL SUCCESS")
        self.assertEqual([item["source"] for item in result["translated"]], ["main.py"])
        self.assertIn("excluded.py", {item["path"] for item in result["skipped"]})
        self.assertFalse((result["output"] / "__pycache__").exists())
        self.assertIn("vendor", result["ignored_directories"])
        with zipfile.ZipFile(result["archive"]) as archive:
            self.assertFalse(any("__pycache__" in name for name in archive.namelist()))

    def test_secret_environment_and_cache_files_are_not_copied(self):
        self.write("main.py", SAMPLES["python"])
        self.write(".env", "TOKEN=example-secret")
        self.write(".env.example", "TOKEN=replace-me")
        self.write("stale.pyc", "cache")
        result = self.migrate()
        self.assertFalse((result["output"] / ".env").exists())
        self.assertFalse((result["output"] / "stale.pyc").exists())
        self.assertTrue((result["output"] / ".env.example").exists())
        with zipfile.ZipFile(result["archive"]) as archive:
            self.assertNotIn(".env", archive.namelist())
            self.assertNotIn("stale.pyc", archive.namelist())

    def test_target_name_collisions_are_resolved(self):
        self.write("same.c", "int value = 2;\n")
        self.write("same.h", "int other = 3;\n")
        result = self.migrate("c", "javascript")
        outputs = {entry["output"] for entry in result["translated"]}
        self.assertEqual(outputs, {"same.c.js", "same.h.js"})

    def test_generated_filename_does_not_overwrite_resource_directory(self):
        self.write("main.py", SAMPLES["python"])
        self.write("main.js/assets/data.txt", "preserve me")
        result = self.migrate("python", "javascript")
        generated = result["translated"][0]["output"]
        self.assertNotEqual(generated, "main.js")
        self.assertTrue((result["output"] / "main.js/assets/data.txt").exists())
        self.assertTrue((result["output"] / generated).is_file())

    def test_cross_file_function_dependency_is_reported_as_not_resolved(self):
        self.write("main.py", "print(helper())\n")
        self.write("helper.py", "def helper():\n    return 7\n")
        result = self.migrate()
        self.assertEqual(result["status"], "PARTIAL SUCCESS")
        failed_paths = {item["path"] for item in result["failed"]}
        self.assertIn("main.py", failed_paths)
        report = (result["output"] / "migration-report.md").read_text(encoding="utf-8")
        self.assertIn("does not resolve imports", report)

    def test_all_nine_conversion_routes_use_compiler(self):
        for source_language, code in SAMPLES.items():
            for target_language in SAMPLES:
                with self.subTest(source=source_language, target=target_language):
                    project = self.base / f"{source_language}-{target_language}"
                    project.mkdir()
                    extension = {"c": ".c", "python": ".py", "javascript": ".js"}[source_language]
                    target_extension = {"c": ".c", "python": ".py", "javascript": ".js"}[target_language]
                    (project / f"main{extension}").write_text(code, encoding="utf-8")
                    result = migrate_project(project, source_language, target_language,
                                             output_dir=self.base / f"out-{source_language}-{target_language}")
                    self.assertEqual(len(result["translated"]), 1)
                    self.assertTrue((result["output"] / f"main{target_extension}").exists())
                    self.assertIn("NOT TESTED", result["runtime_equivalence"])

    def test_archive_failure_leaves_no_output_and_preserves_source(self):
        original = self.write("main.py", SAMPLES["python"])
        output = self.base / "atomic output"
        archive = self.base / "atomic.zip"
        with patch("multilang_transpiler.project_migration.zipfile.ZipFile", side_effect=OSError("simulated archive failure")):
            with self.assertRaisesRegex(MigrationError, "could not be completed safely"):
                self.migrate(output_dir=output, archive_path=archive)
        self.assertFalse(output.exists())
        self.assertFalse(archive.exists())
        self.assertEqual(original.read_text(encoding="utf-8"), SAMPLES["python"])
        self.assertFalse(any(self.base.glob(".multilang-migration-*")))


if __name__ == "__main__":
    unittest.main()

