"""Run only the committed regression programs and write actual conversion results."""
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from multilang_transpiler.codegen import generate
from multilang_transpiler.ir import lower
from multilang_transpiler.parser import parse
from multilang_transpiler.semantic import analyze
from webapp.compiler_service import _syntax_validate

EXT = {"c": "c", "python": "py", "javascript": "js"}
SOURCES = {language: (ROOT / "samples" / f"regression.{suffix}").read_text(encoding="utf-8")
           for language, suffix in EXT.items()}
COMPILER = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
NODE = shutil.which("node")


def run_program(language, code):
    with tempfile.TemporaryDirectory(prefix="multilang-matrix-") as folder:
        folder = Path(folder)
        if language == "python":
            command = [sys.executable, "-c", code]
        elif language == "javascript":
            if not NODE: return {"status": "unavailable", "detail": "Node.js not installed."}
            command = [NODE, "-e", code]
        else:
            if not COMPILER: return {"status": "unavailable", "detail": "No C compiler installed."}
            source = folder / "program.c"
            executable = folder / "program"
            source.write_text(code, encoding="utf-8")
            build = subprocess.run([COMPILER, str(source), "-o", str(executable)], capture_output=True,
                                   text=True, timeout=15, check=False)
            if build.returncode:
                return {"status": "failed", "compile_exit": build.returncode,
                        "compile_stderr": build.stderr.strip(), "detail": "C compile failed."}
            command = [str(executable)]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        except subprocess.TimeoutExpired:
            return {"status": "failed", "detail": "Program timed out after 10 seconds."}
        return {"status": "passed" if result.returncode == 0 else "failed",
                "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def syntax_check(language, code):
    result = _syntax_validate(language, code)
    return result["status"], result.get("tool") or "unavailable", result.get("message", "")


def main():
    rows=[]
    for source_language, source_code in SOURCES.items():
        for target_language in SOURCES:
            row={"source": source_language, "target": target_language,
                 "program": f"Regression ({source_language})", "parse": "pass", "ir": "pass", "generation": "pass",
                 "syntax": "not run", "runtime": "not run", "equivalence": "not checked", "status": "fail", "detail": ""}
            try:
                program=parse(source_code, source_language)
                analyze(program, source_language)
                ir=lower(program)
                generated=generate(ir, target_language)
            except Exception as exc:
                row["parse"]="fail" if getattr(exc,"phase","") in ("lexical","syntax","preprocessing","semantic") else "pass"
                row["generation"]="fail" if row["parse"]=="pass" else "not reached"
                row["detail"]=str(exc)
                rows.append(row)
                continue
            syntax, tool, message=syntax_check(target_language, generated)
            row["syntax"]=f"{syntax} ({tool})"
            original=run_program(source_language,source_code)
            translated=run_program(target_language,generated)
            row["runtime"]=f"source {original['status']}; target {translated['status']}"
            row["source_run"]=original
            row["target_run"]=translated
            if original["status"]==translated["status"]=="passed":
                equivalent=(original.get("stdout")==translated.get("stdout") and
                            original.get("stderr")==translated.get("stderr") and
                            original.get("exit_code")==translated.get("exit_code"))
                row["equivalence"]="yes" if equivalent else "no"
            elif original["status"]=="unavailable" or translated["status"]=="unavailable":
                row["equivalence"]="unavailable"
            else:
                row["equivalence"]="no"
            row["status"]="pass" if syntax=="passed" and row["equivalence"]=="yes" else ("unverified" if syntax=="unavailable" or row["equivalence"]=="unavailable" else "fail")
            if row["status"]!="pass":
                row["detail"]="; ".join(part for part in (message, str(original.get("detail", "")), str(translated.get("detail", ""))) if part)
            rows.append(row)

    passed=sum(row["status"]=="pass" for row in rows)
    failed=sum(row["status"]=="fail" for row in rows)
    unverified=sum(row["status"]=="unverified" for row in rows)
    lines=["# Cross-language conversion matrix report", "",
           f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", "",
           "This report was produced by `python tools/build_matrix_report.py`. It parses, analyzes, lowers through the shared IR, generates each target, syntax-checks it, and runs only the committed regression programs in temporary directories.", "",
           f"**Actual result: {passed}/9 passed, {failed} failed, {unverified} unverified.**", "",
           "| Source | Target | Test program | Parse | IR lowering | Code generation | Syntax validation | Runtime / compilation | Output equivalent | Status |", "|---|---|---|---|---|---|---|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['source']} | {row['target']} | {row['program']} | {row['parse']} | {row['ir']} | {row['generation']} | {row['syntax']} | {row['runtime']} | {row['equivalence']} | **{row['status'].upper()}** |")
    lines += ["", "## Captured runtime evidence", "", "Stdout is shown with escaped newlines. Source and target exit codes and stderr are compared as well as stdout.", ""]
    for row in rows:
        if "source_run" not in row: continue
        def shown(run):
            if run["status"] != "passed": return run.get("detail", run["status"])
            return f"exit {run['exit_code']}; stdout `{run['stdout']!r}`; stderr `{run['stderr']!r}`"
        lines.append(f"- **{row['source']} → {row['target']} ({row['status'].upper()}):** source {shown(row['source_run'])}; target {shown(row['target_run'])}.")
        if row["detail"]: lines.append(f"  - Details: {row['detail']}")
    lines += ["", "## Regression output", "", "Expected and observed output for each supplied language variant:", "", "```text", "Sum = 30", "Greater than 25", "Program completed", "```", "", "The dashboard itself never executes user-submitted programs. Runtime runs in this report are limited to the three checked-in regression files.", ""]
    destination=ROOT / "docs" / "CONVERSION_MATRIX.md"
    destination.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {destination}")
    print(f"{passed}/9 passed, {failed} failed, {unverified} unverified")
    return 0 if failed==0 and unverified==0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
