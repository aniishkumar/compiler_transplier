# demo_project — migrated project

This project was migrated from **python** to **javascript** by MultiLang Transpiler.

## Getting started

Target runtime/toolchain: Node.js for running JavaScript files.

Review `migration-report.md` before using this project. Translated files were syntax-checked when a validator was available. Source and target programs were not executed as part of migration, so runtime equivalence is **not verified**.

## Important limitations

- The compiler supports only the shared subset documented in `migration-report.md` and the MultiLang Transpiler grammar.
- Each source file is translated independently. Imports, cross-file symbol resolution, header/module dependencies, and project-wide linking are not migrated.
- Configuration and dependency files copied from the source project may describe the source language and may need manual replacement.
- Original project documentation is preserved as copied; verify that it still describes the migrated code.
