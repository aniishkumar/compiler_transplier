"""Safe, per-file project migration built on the shared compiler pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import fnmatch
import os
from pathlib import Path
import shutil
import tempfile
import uuid
import zipfile

from .errors import CompileError
from .transpiler import transpile_source
from .validation import validate_generated

LANGUAGES = ("c", "python", "javascript")
SOURCE_EXTENSIONS = {
    "c": {".c", ".h"},
    "python": {".py"},
    "javascript": {".js", ".mjs"},
}
TARGET_EXTENSION = {"c": ".c", "python": ".py", "javascript": ".js"}
KNOWN_SOURCE_EXTENSIONS = {
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".py", ".pyw", ".js", ".mjs", ".jsx",
    ".ts", ".tsx", ".java", ".kt", ".go", ".rs", ".rb", ".php", ".cs", ".swift", ".dart",
    ".scala", ".sh", ".sql", ".r", ".lua", ".pl",
}
DEFAULT_IGNORED_DIRECTORIES = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".idea", ".vscode",
    "build", "dist", "target", "coverage", ".next", ".cache", ".gradle", ".turbo",
    ".parcel-cache", "bower_components", "bin", "obj",
}
IGNORED_FILES = {".DS_Store", "Thumbs.db", ".coverage", "coverage.xml", "npm-debug.log", "yarn-error.log"}
IGNORED_FILE_PATTERNS = ("*.pyc", "*.pyo", "*.swp", "*.swo", "*~", "*.tmp")
CONFIG_FILES = {
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "Pipfile.lock",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Cargo.toml", "go.mod",
    "Makefile", "CMakeLists.txt", "Dockerfile", "docker-compose.yml", "tox.ini", ".env.example",
}


class MigrationError(Exception):
    """Fatal input, destination, or packaging error suitable for CLI display."""


@dataclass
class MigrationPlan:
    root: Path
    discovered: list[Path] = field(default_factory=list)
    source_files: list[Path] = field(default_factory=list)
    resources: list[Path] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    ignored_directories: list[str] = field(default_factory=list)


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _destination(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_symlink():
        raise MigrationError(f"Destination must not be a symbolic link: {path}")
    return path.parent.resolve() / path.name


def _excluded(relative: Path, patterns: tuple[str, ...]) -> bool:
    path = relative.as_posix()
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        if pattern.endswith("/**"):
            directory = pattern[:-3]
            if path == directory or path.startswith(directory + "/"):
                return True
    return False


def _ignored_file(filename: str) -> bool:
    if filename in IGNORED_FILES or any(fnmatch.fnmatch(filename, pattern) for pattern in IGNORED_FILE_PATTERNS):
        return True
    if filename == ".env":
        return True
    return filename.startswith(".env.") and filename not in {".env.example", ".env.sample"}


def _discover(root: Path, language: str, patterns: tuple[str, ...]) -> MigrationPlan:
    plan = MigrationPlan(root)
    accepted = SOURCE_EXTENSIONS[language]
    for current, dirs, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs.sort()
        kept_dirs = []
        for name in dirs:
            path = current_path / name
            relative = path.relative_to(root)
            if path.is_symlink():
                plan.skipped.append({"path": relative.as_posix(), "reason": "symbolic-link directory was not followed"})
            elif name in DEFAULT_IGNORED_DIRECTORIES:
                plan.ignored_directories.append(relative.as_posix())
            elif _excluded(relative, patterns):
                plan.ignored_directories.append(relative.as_posix())
            else:
                kept_dirs.append(name)
        dirs[:] = kept_dirs
        for filename in sorted(filenames):
            path = current_path / filename
            relative = path.relative_to(root)
            if _ignored_file(filename) or _excluded(relative, patterns):
                plan.skipped.append({"path": relative.as_posix(), "reason": "matched a default or custom ignore rule"})
                continue
            if path.is_symlink():
                plan.skipped.append({"path": relative.as_posix(), "reason": "symbolic link was not copied"})
                continue
            if not path.is_file():
                continue
            plan.discovered.append(relative)
            suffix = path.suffix.lower()
            if suffix in accepted:
                plan.source_files.append(relative)
            elif suffix in KNOWN_SOURCE_EXTENSIONS:
                plan.skipped.append({
                    "path": relative.as_posix(),
                    "reason": f"source extension {suffix or '(none)'} is not enabled for {language}",
                })
            else:
                plan.resources.append(relative)
    return plan


def _default_destinations(root: Path) -> tuple[Path, Path]:
    base = root.parent / f"{root.name}_migrated"
    candidate = base
    index = 2
    while candidate.exists() or Path(str(candidate) + ".zip").exists():
        candidate = base.with_name(f"{base.name}_{index}")
        index += 1
    return candidate, Path(str(candidate) + ".zip")


def _target_paths(plan: MigrationPlan, target: str) -> dict[Path, Path]:
    extension = TARGET_EXTENSION[target]
    candidate_counts: dict[Path, int] = {}
    for relative in plan.source_files:
        base = relative.with_suffix(extension)
        candidate_counts[base] = candidate_counts.get(base, 0) + 1
    reserved: set[Path] = set()
    resource_paths = set(plan.resources)
    resource_ancestors = {parent for path in resource_paths for parent in path.parents if parent != Path(".")}
    results = {}
    for relative in plan.source_files:
        base = relative.with_suffix(extension)
        if candidate_counts[base] > 1:
            base = relative.with_name(relative.name + extension)
        candidate = base
        number = 2
        while candidate in reserved or candidate in resource_paths or candidate in resource_ancestors:
            candidate = base.with_name(f"{base.stem}_{number}{base.suffix}")
            number += 1
        reserved.add(candidate)
        results[relative] = candidate
    return results


def _translate(source: str, source_language: str, target_language: str) -> str:
    return transpile_source(source, source_language, target_language)


def _migration_readme(name: str, source_language: str, target_language: str) -> str:
    requirements = {
        "python": "Python 3.10 or newer.",
        "javascript": "Node.js for running JavaScript files.",
        "c": "A C compiler such as clang or gcc.",
    }
    return f"""# {name} — migrated project

This project was migrated from **{source_language}** to **{target_language}** by MultiLang Transpiler.

## Getting started

Target runtime/toolchain: {requirements[target_language]}

Review `migration-report.md` before using this project. Translated files were syntax-checked when a validator was available. Source and target programs were not executed as part of migration, so runtime equivalence is **not verified**.

## Important limitations

- The compiler supports only the shared subset documented in `migration-report.md` and the MultiLang Transpiler grammar.
- Each source file is translated independently. Imports, cross-file symbol resolution, header/module dependencies, and project-wide linking are not migrated.
- Configuration and dependency files copied from the source project may describe the source language and may need manual replacement.
- Original project documentation is preserved as copied; verify that it still describes the migrated code.
"""


def _render_report(*, source: Path, source_language: str, target_language: str,
                   plan: MigrationPlan, translated: list[dict], failures: list[dict],
                   copied: list[str], status: str, output: Path, archive: Path,
                   ignored_dirs: list[str]) -> str:
    entries = [
        ("Translated files", translated),
        ("Skipped files", plan.skipped),
        ("Failed files", failures),
    ]
    lines = [
        "# Project Migration Report", "",
        f"- **Status:** {status}",
        f"- **Source project:** `{source.name}` (absolute path intentionally omitted)",
        f"- **From:** {source_language}",
        f"- **To:** {target_language}",
        f"- **Migrated at (UTC):** {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- **Files discovered:** {len(plan.discovered)}",
        f"- **Translated successfully:** {len(translated)}",
        f"- **Skipped:** {len(plan.skipped)}",
        f"- **Failed:** {len(failures)}",
        f"- **Non-source files copied:** {len(copied)}",
        f"- **Ignored directories:** {len(ignored_dirs)}",
        f"- **Project output:** `{output.name}/`",
        f"- **ZIP archive:** `{archive.name}`",
        "- **Runtime equivalence:** NOT TESTED — migration never executes project code.",
        "", "## Translated files", "",
    ]
    if translated:
        lines.extend(f"- `{item['source']}` → `{item['output']}` — validation: **{item['validation_status']}** ({item['validation_message']})" for item in translated)
    else:
        lines.append("- None")
    for title, items in entries[1:]:
        lines.extend(["", f"## {title}", ""])
        if not items:
            lines.append("- None")
        elif title == "Skipped files":
            lines.extend(f"- `{item['path']}` — {item['reason']}" for item in items)
        else:
            lines.extend(f"- `{item['path']}` — phase: **{item.get('phase', 'copy')}**; {item['message']}" for item in items)
    lines.extend(["", "## Copied non-source files", ""])
    lines.extend(f"- `{path}`" for path in copied) if copied else lines.append("- None")
    lines.extend(["", "## Ignored directories", ""])
    lines.extend(f"- `{path}/`" for path in ignored_dirs) if ignored_dirs else lines.append("- None")
    lines.extend([
        "", "## Dependency and project limitations", "",
        "Files are compiled independently. The compiler does not resolve imports, translate modules, link multiple files, migrate project dependencies, or rewrite build configuration. Headers are processed as standalone C-subset files; user-defined include relationships are not resolved.",
        "", "## Configuration files", "",
        "Copied unchanged when present. Inspect source-language manifests and update them manually for the target runtime; no target dependency manifest is fabricated.",
    ])
    config_copies = [path for path in copied if Path(path).name in CONFIG_FILES]
    lines.extend(f"- `{path}` — copied unchanged; review for source-language assumptions." for path in config_copies) if config_copies else lines.append("- No recognized dependency/build manifests were copied.")
    lines.extend([
        "", "## Manual completion steps", "",
        "1. Review every failed or skipped source file and adapt unsupported syntax manually.",
        "2. Resolve imports, module references, cross-file declarations, and project linking.",
        "3. Review copied configuration and dependency files and create target-language equivalents.",
        "4. Run the target project’s tests in a controlled environment; runtime equivalence was not tested here.",
        "", "## Status definitions", "",
        "- **SUCCESS:** Every discovered eligible source file translated and passed syntax validation; no unsupported source files were skipped.",
        "- **PARTIAL SUCCESS:** At least one source file translated, but some source files were skipped or failed, or validation was unavailable.",
        "- **FAILED:** No source file was successfully translated, or a fatal migration/packaging error occurred.",
        "- **NOT VALIDATED:** Translation succeeded but the target syntax checker was unavailable.",
    ])
    return "\n".join(lines) + "\n"


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _commit(project_stage: Path, archive_stage: Path, output: Path, archive: Path, overwrite: bool) -> None:
    destinations = (output, archive)
    existing = [path for path in destinations if path.exists() or path.is_symlink()]
    if existing and not overwrite:
        raise MigrationError("Output already exists: " + ", ".join(str(path) for path in existing) + ". Choose a new destination or pass --overwrite.")

    backups: dict[Path, Path] = {}
    installed: list[Path] = []
    try:
        for path in existing:
            backup = path.with_name(f".{path.name}.backup-{uuid.uuid4().hex}")
            os.replace(path, backup)
            backups[path] = backup
        os.replace(project_stage, output)
        installed.append(output)
        os.replace(archive_stage, archive)
        installed.append(archive)
    except Exception as exc:
        for path in reversed(installed):
            _remove_path(path)
        for original, backup in backups.items():
            if backup.exists() or backup.is_symlink():
                os.replace(backup, original)
        raise MigrationError(f"Could not safely finalize the project and archive: {exc}") from exc
    else:
        for backup in backups.values():
            _remove_path(backup)


def migrate_project(project_dir: str | Path, source_language: str, target_language: str,
                    *, output_dir: str | Path | None = None, archive_path: str | Path | None = None,
                    dry_run: bool = False, overwrite: bool = False, excludes=(), progress=None) -> dict:
    """Migrate eligible files into a separate project directory and verified ZIP.

    The function never executes source or generated project code. It returns a plan
    in dry-run mode and raises MigrationError for fatal path, collision, or packaging errors.
    """
    if source_language not in LANGUAGES or target_language not in LANGUAGES:
        raise MigrationError("Languages must be c, python, or javascript.")
    try:
        root = Path(project_dir).expanduser().resolve(strict=True)
    except OSError as exc:
        raise MigrationError(f"Cannot access project path {project_dir!s}: {exc}") from exc
    if not root.is_dir():
        raise MigrationError(f"Project input must be a directory: {root}")

    if output_dir is None:
        output, archive = _default_destinations(root)
    else:
        output = _destination(output_dir)
        archive = _destination(archive_path) if archive_path else Path(str(output) + ".zip")
    if archive_path is not None and output_dir is None:
        archive = _destination(archive_path)
    if output == root or root in output.parents or output in root.parents:
        raise MigrationError("Output directory must be separate from the input project; choose a non-overlapping destination.")
    if output == archive or output in archive.parents or archive in output.parents:
        raise MigrationError("The ZIP archive must be outside the migrated project directory.")
    if archive.suffix.lower() != ".zip":
        raise MigrationError("Archive path must end in .zip.")
    if root == archive or root in archive.parents or archive in root.parents:
        raise MigrationError("Archive path must be outside the input project.")
    if not overwrite and (output.exists() or archive.exists()):
        existing = [str(path) for path in (output, archive) if path.exists()]
        raise MigrationError("Output already exists: " + ", ".join(existing) + ". Choose a new destination or pass --overwrite.")

    patterns = tuple(excludes)
    if progress:
        progress("Discovering project files")
    plan = _discover(root, source_language, patterns)
    if not plan.discovered and not plan.skipped:
        raise MigrationError("The project is empty after applying default and custom exclusions.")

    target_map = _target_paths(plan, target_language)
    if dry_run:
        return {
            "status": "DRY RUN", "source": root, "output": output, "archive": archive,
            "source_language": source_language, "target_language": target_language,
            "discovered": plan.discovered, "translations": target_map,
            "resources": plan.resources, "skipped": plan.skipped,
            "ignored_directories": plan.ignored_directories,
        }
    if not plan.source_files:
        raise MigrationError("No source files for the selected language were found; no project was created.")

    output.parent.mkdir(parents=True, exist_ok=True)
    archive.parent.mkdir(parents=True, exist_ok=True)
    stage_parent = Path(tempfile.mkdtemp(prefix=".multilang-migration-", dir=output.parent))
    project_stage = stage_parent / "project"
    project_stage.mkdir()
    archive_stage = archive.parent / f".{archive.name}.tmp-{uuid.uuid4().hex}"
    translated: list[dict] = []
    failures = []
    copied: list[str] = []
    source_readmes: list[tuple[str, str]] = []
    try:
        if progress:
            progress("Translating source files through the compiler")
        for relative in plan.source_files:
            source_path = root / relative
            destination_relative = target_map[relative]
            destination = project_stage / destination_relative
            try:
                source_text = source_path.read_text(encoding="utf-8")
                result = _translate(source_text, source_language, target_language)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(result, encoding="utf-8")
                translated.append({"source": relative.as_posix(), "output": destination_relative.as_posix(),
                                   "validation_status": "PENDING", "validation_message": ""})
            except CompileError as exc:
                failures.append({"path": relative.as_posix(), "phase": exc.phase,
                                 "message": f"line {exc.line}: {exc.message}" if exc.line else exc.message})
            except (OSError, ValueError, RecursionError) as exc:
                failures.append({"path": relative.as_posix(), "phase": "input/code generation", "message": str(exc)})
            except Exception as exc:
                failures.append({"path": relative.as_posix(), "phase": "compiler", "message": f"Unexpected compiler error: {exc}"})

        if progress:
            progress("Copying permitted non-source project files")
        for relative in plan.resources:
            source_path = root / relative
            destination = project_stage / relative
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, destination)
                copied.append(relative.as_posix())
                if relative.as_posix().lower() == "readme.md":
                    source_readmes.append((relative.as_posix(), destination.read_text(encoding="utf-8", errors="replace")))
            except OSError as exc:
                failures.append({"path": relative.as_posix(), "phase": "copy", "message": str(exc)})

        if progress:
            progress("Validating generated source syntax")
        validation_unavailable = False
        for item in translated[:]:
            generated = project_stage / item["output"]
            validation = validate_generated(target_language, generated.read_text(encoding="utf-8"))
            item["validation_status"] = {
                "passed": "SUCCESS", "failed": "FAILED", "unavailable": "NOT VALIDATED",
            }.get(validation["status"], "NOT VALIDATED")
            item["validation_message"] = validation["message"]
            if validation["status"] == "unavailable":
                validation_unavailable = True
            elif validation["status"] == "failed":
                failures.append({"path": item["source"], "phase": "validation", "message": validation["message"]})
                _remove_path(generated)
                translated.remove(item)

        source_extensions = set().union(*SOURCE_EXTENSIONS.values())
        source_skips = [item for item in plan.skipped if Path(item["path"]).suffix.lower() in source_extensions or "source extension" in item["reason"]]
        status = "SUCCESS"
        if not translated:
            status = "FAILED"
        elif failures or source_skips or validation_unavailable:
            status = "PARTIAL SUCCESS"

        readme_path = project_stage / "README.md"
        readme_content = _migration_readme(root.name, source_language, target_language)
        if source_readmes:
            original_path = project_stage / "README.original.md"
            index = 2
            while original_path.exists():
                original_path = project_stage / f"README.original-{index}.md"
                index += 1
            shutil.copy2(project_stage / source_readmes[0][0], original_path)
            copied.remove(source_readmes[0][0])
            copied.append(original_path.relative_to(project_stage).as_posix())
            original_readme = project_stage / source_readmes[0][0]
            if original_readme != readme_path:
                _remove_path(original_readme)
        readme_path.write_text(readme_content, encoding="utf-8")
        report = _render_report(source=root, source_language=source_language, target_language=target_language,
                                plan=plan, translated=translated, failures=failures, copied=copied,
                                status=status, output=output, archive=archive,
                                ignored_dirs=plan.ignored_directories)
        (project_stage / "migration-report.md").write_text(report, encoding="utf-8")

        if progress:
            progress("Creating and verifying ZIP archive")
        names = []
        with zipfile.ZipFile(archive_stage, "w", compression=zipfile.ZIP_DEFLATED) as archive_file:
            for path in sorted(project_stage.rglob("*")):
                if path.is_dir():
                    continue
                relative = path.relative_to(project_stage).as_posix()
                if any(part in DEFAULT_IGNORED_DIRECTORIES for part in Path(relative).parts) or path.name in IGNORED_FILES:
                    continue
                if relative in names:
                    raise MigrationError(f"Duplicate ZIP entry: {relative}")
                names.append(relative)
                archive_file.write(path, arcname=relative)
        with zipfile.ZipFile(archive_stage, "r") as archive_file:
            corrupt = archive_file.testzip()
            if corrupt:
                raise MigrationError(f"ZIP integrity check failed for {corrupt}.")
        if progress:
            progress("Finalizing output directory and archive")
        _commit(project_stage, archive_stage, output, archive, overwrite)
    except MigrationError:
        raise
    except Exception as exc:
        raise MigrationError(f"Migration could not be completed safely: {exc}") from exc
    finally:
        shutil.rmtree(stage_parent, ignore_errors=True)
        if archive_stage.exists():
            archive_stage.unlink(missing_ok=True)

    return {
        "status": status, "source": root, "output": output, "archive": archive,
        "discovered_count": len(plan.discovered), "translated": translated,
        "skipped": plan.skipped, "failed": failures, "copied": copied,
        "ignored_directories": plan.ignored_directories, "zip_entries": names,
        "runtime_equivalence": "NOT TESTED",
    }

