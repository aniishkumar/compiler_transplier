"""Flask dashboard/API. The service compiles but never executes submitted programs."""
from pathlib import Path
from flask import Flask, jsonify, render_template, request

from webapp.compiler_service import LANGUAGES, MAX_SOURCE_CHARS, run_matrix_checks, transpile

ROOT = Path(__file__).resolve().parents[1]

def create_app(test_config=None):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(MAX_CONTENT_LENGTH=MAX_SOURCE_CHARS * 6 + 8192, JSON_SORT_KEYS=False)
    if test_config:
        app.config.update(test_config)

    @app.get("/")
    def dashboard():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        return jsonify({"available": True, "compiler": "MultiLang Transpiler", "languages": sorted(LANGUAGES), "max_source_characters": MAX_SOURCE_CHARS})

    @app.get("/api/examples")
    def examples():
        result = []
        definitions = [
            ("hello", "Arithmetic output", "Declare a value, add 3, and print the result 5."),
            ("if_else", "Comparison and if/else", "Use comparisons and a Boolean condition to select output."),
            ("while_loop", "While loop", "Repeat an update until the loop condition becomes false."),
            ("function", "Function and return", "Call a function that returns a computed integer."),
            ("arrays", "Arrays, loops, and functions", "Initialize an integer array, index it in a counted loop, call a helper, and accumulate a result."),
        ]
        extensions = {"c": "c", "python": "py", "javascript": "js"}
        for stem, title, description in definitions:
            for language in ("c", "python", "javascript"):
                path = ROOT / "samples" / f"{stem}.{extensions[language]}"
                result.append({"id": f"{stem}-{language}", "name": f"{title} ({language})", "language": language, "description": description, "source_code": path.read_text(encoding="utf-8")})
        return jsonify(result)

    @app.post("/api/transpile")
    def api_transpile():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"success": False, "error": {"category": "request", "phase": "request", "message": "Request body must be a JSON object.", "line": None, "column": None}}), 400
        source_language = payload.get("source_language")
        target_language = payload.get("target_language")
        source_code = payload.get("source_code")
        if not isinstance(source_language, str) or not isinstance(target_language, str) or source_language not in LANGUAGES or target_language not in LANGUAGES:
            return jsonify({"success": False, "error": {"category": "request", "phase": "request", "message": "source_language and target_language must be c, python, or javascript.", "line": None, "column": None}}), 400
        if not isinstance(source_code, str):
            return jsonify({"success": False, "error": {"category": "request", "phase": "request", "message": "source_code must be a string.", "line": None, "column": None}}), 400
        if len(source_code) > MAX_SOURCE_CHARS:
            return jsonify({"success": False, "error": {"category": "request", "phase": "request", "message": f"Source exceeds the {MAX_SOURCE_CHARS:,} character limit.", "line": None, "column": None}}), 413
        return jsonify(transpile(source_language, target_language, source_code))

    @app.post("/api/test-conversion")
    def api_test_conversion():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"success": False, "error": {"category": "request", "phase": "request", "message": "Request body must be a JSON object."}}), 400
        source_language, target_language = payload.get("source_language"), payload.get("target_language")
        source_code = payload.get("source_code")
        if not isinstance(source_language, str) or not isinstance(target_language, str) or source_language not in LANGUAGES or target_language not in LANGUAGES or not isinstance(source_code, str):
            return jsonify({"success": False, "error": {"category": "request", "phase": "request", "message": "Provide supported source_language, target_language, and string source_code fields."}}), 400
        if len(source_code) > MAX_SOURCE_CHARS:
            return jsonify({"success": False, "error": {"category": "request", "phase": "request", "message": f"Source exceeds the {MAX_SOURCE_CHARS:,} character limit."}}), 413
        converted = transpile(source_language, target_language, source_code)
        validation = next((p["output"] for p in converted["phases"] if p["id"] == "validation"), None)
        checks = [{"name": "Translation", "status": "passed" if converted["success"] else "failed", "passed": converted["success"], "message": "Translation completed." if converted["success"] else converted.get("error", {}).get("message", "Translation failed.")}, {"name": "Target syntax validation", "status": "passed" if validation and validation.get("status") == "passed" else ("failed" if validation and validation.get("status") == "failed" else ("skipped" if converted["success"] else "not_reached")), "passed": bool(validation and validation.get("status") == "passed"), "message": validation.get("message", "Not reached") if validation else "Not reached"}]
        return jsonify({"success": converted["success"], "passed": sum(c["status"] == "passed" for c in checks), "failed": sum(c["status"] == "failed" for c in checks), "skipped": sum(c["status"] == "skipped" for c in checks), "checks": checks, "execution": "No source or generated programs were executed."})

    @app.post("/api/test-matrix")
    def api_test_matrix():
        return jsonify(run_matrix_checks())

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify({"success": False, "error": {"category": "request", "phase": "request", "message": "Request body exceeds the configured size limit.", "line": None, "column": None}}), 413

    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
