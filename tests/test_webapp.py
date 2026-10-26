import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from webapp.app import create_app


class DashboardApiTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app({"TESTING": True}).test_client()

    def test_health_and_dashboard(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertTrue(health.json["available"])
        self.assertEqual(set(health.json["languages"]), {"c", "python", "javascript"})
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Transpile Code", page.data)
        self.assertIn(b'id="phase-description"', page.data)
        self.assertIn(b'id="generated-code"', page.data)
        self.assertNotIn(b"Conversion details", page.data)
        self.assertNotIn(b"data-tab=", page.data)
        self.assertIn(b"/static/css/style.css", page.data)
        self.assertIn(b"/static/js/app.js", page.data)
        js = self.client.get("/static/js/app.js")
        css = self.client.get("/static/css/style.css")
        self.assertEqual(js.status_code, 200)
        self.assertEqual(css.status_code, 200)
        js.close(); css.close()

    def test_examples_endpoint_loads_three_real_samples(self):
        response = self.client.get("/api/examples")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({item["language"] for item in response.json}, {"c", "python", "javascript"})
        self.assertEqual(len(response.json), 15)
        self.assertTrue(all(item["source_code"] for item in response.json))

    def test_feature_examples_generate_valid_targets(self):
        examples = self.client.get("/api/examples").json
        for example in examples:
            if example["id"].startswith("hello-"):
                continue
            for target in ("c", "python", "javascript"):
                with self.subTest(example=example["id"], target=target):
                    result = self.client.post("/api/transpile", json={"source_language": example["language"], "target_language": target, "source_code": example["source_code"]})
                    self.assertTrue(result.json["success"], result.json)
                    validation = result.json["phases"][-1]["output"]
                    self.assertEqual(validation["status"], "passed", result.json)

    def test_all_nine_api_routes(self):
        samples = {
            "c": '#include <stdio.h>\nint main() { int count = 2; printf("%d\\n", count + 3); return 0; }',
            "python": "count = 2\nprint(count + 3)\n",
            "javascript": "let count = 2; console.log(count + 3);",
        }
        for source in samples:
            for target in samples:
                with self.subTest(source=source, target=target):
                    response = self.client.post("/api/transpile", json={"source_language": source, "target_language": target, "source_code": samples[source]})
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.json["success"], response.json)
                    self.assertTrue(response.json["generated_code"])
                    self.assertEqual([phase["status"] for phase in response.json["phases"]], ["completed"] * 8)
                    self.assertTrue(response.json["tokens"])
                    self.assertTrue(response.json["ir"])
                    phases = {phase["id"]: phase for phase in response.json["phases"]}
                    self.assertEqual(phases["ast"]["output"]["tree"], response.json["ast"])
                    self.assertEqual(phases["ir"]["output"], response.json["ir"])
                    self.assertIn("checks", phases["semantic"]["output"])
                    self.assertNotEqual(phases["ast"]["output"]["tree"]["body"][0].get("kind"), response.json["ir"]["body"][0].get("op"))
                    self.assertTrue(all(phase["description"] for phase in response.json["phases"]))

    def test_invalid_source_returns_diagnostic_and_cleared_output(self):
        response = self.client.post("/api/transpile", json={"source_language": "c", "target_language": "python", "source_code": "int n = ;"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["success"])
        self.assertIsNone(response.json["generated_code"])
        self.assertEqual(response.json["error"]["phase"], "syntax")
        self.assertEqual(response.json["phases"][2]["status"], "failed")
        self.assertTrue(all(phase["status"] == "not_reached" for phase in response.json["phases"][3:]))

    def test_c_println_alias_translates_to_python_print(self):
        response = self.client.post("/api/transpile", json={"source_language": "c", "target_language": "python", "source_code": 'println("Hello");'})
        self.assertTrue(response.json["success"], response.json)
        self.assertIn('print("Hello")', response.json["generated_code"])
        self.assertTrue(response.json["warnings"])

    @patch("webapp.compiler_service._syntax_validate", return_value={"status": "failed", "tool": "test", "message": "synthetic syntax diagnostic"})
    def test_failed_target_validation_clears_usable_output(self, _mock_validation):
        response = self.client.post("/api/transpile", json={"source_language": "python", "target_language": "python", "source_code": "print(1)"})
        self.assertFalse(response.json["success"])
        self.assertIsNone(response.json["generated_code"])
        generation = next(phase for phase in response.json["phases"] if phase["id"] == "generation")
        self.assertEqual(generation["status"], "completed")
        self.assertTrue(generation["output"])
        self.assertEqual(response.json["error"]["phase"], "validation")

    def test_unknown_function_does_not_return_false_success(self):
        response = self.client.post("/api/transpile", json={"source_language": "c", "target_language": "python", "source_code": "mystery(1);"})
        self.assertFalse(response.json["success"])
        self.assertEqual(response.json["error"]["phase"], "semantic")

    def test_request_validation_and_source_limit(self):
        self.assertEqual(self.client.post("/api/transpile", json={"source_language": [], "target_language": "python", "source_code": ""}).status_code, 400)
        self.assertEqual(self.client.post("/api/transpile", json={"source_language": "c", "target_language": "rust", "source_code": ""}).status_code, 400)
        self.assertEqual(self.client.post("/api/transpile", json={"source_language": "c", "target_language": "python", "source_code": "x" * 50_001}).status_code, 413)

    def test_controlled_matrix_check_does_not_execute_programs(self):
        response = self.client.post("/api/test-matrix")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["checks"]), 9)
        self.assertEqual(response.json["passed"], 9, response.json)
        self.assertEqual(response.json["failed"], 0)
        self.assertIn("were executed", response.json["execution"])


if __name__ == "__main__":
    unittest.main()
