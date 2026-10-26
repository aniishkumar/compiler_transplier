# Project Migration Report

- **Status:** SUCCESS
- **Source project:** `demo_project` (absolute path intentionally omitted)
- **From:** python
- **To:** javascript
- **Migrated at (UTC):** 2026-10-25T18:58:44+00:00
- **Files discovered:** 3
- **Translated successfully:** 1
- **Skipped:** 0
- **Failed:** 0
- **Non-source files copied:** 2
- **Ignored directories:** 0
- **Project output:** `demo_project_migrated/`
- **ZIP archive:** `demo_project_migrated.zip`
- **Runtime equivalence:** NOT TESTED — migration never executes project code.

## Translated files

- `src/main.py` → `src/main.js` — validation: **SUCCESS** (Generated javascript syntax is valid; program was not executed.)

## Skipped files

- None

## Failed files

- None

## Copied non-source files

- `assets/message.txt`
- `README.original.md`

## Ignored directories

- None

## Dependency and project limitations

Files are compiled independently. The compiler does not resolve imports, translate modules, link multiple files, migrate project dependencies, or rewrite build configuration. Headers are processed as standalone C-subset files; user-defined include relationships are not resolved.

## Configuration files

Copied unchanged when present. Inspect source-language manifests and update them manually for the target runtime; no target dependency manifest is fabricated.
- No recognized dependency/build manifests were copied.

## Manual completion steps

1. Review every failed or skipped source file and adapt unsupported syntax manually.
2. Resolve imports, module references, cross-file declarations, and project linking.
3. Review copied configuration and dependency files and create target-language equivalents.
4. Run the target project’s tests in a controlled environment; runtime equivalence was not tested here.

## Status definitions

- **SUCCESS:** Every discovered eligible source file translated and passed syntax validation; no unsupported source files were skipped.
- **PARTIAL SUCCESS:** At least one source file translated, but some source files were skipped or failed, or validation was unavailable.
- **FAILED:** No source file was successfully translated, or a fatal migration/packaging error occurred.
- **NOT VALIDATED:** Translation succeeded but the target syntax checker was unavailable.
