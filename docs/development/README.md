# Development

This directory holds contributor-facing development documentation (local setup detail beyond
the `README.md` quick start, debugging notes, and workflow guides) written as the implementation
proceeds.

For now:

- Toolchain and dependency policy: [`docs/v3_specification/16_Engineering_Standards/02_TOOLCHAIN.md`](../v3_specification/16_Engineering_Standards/02_TOOLCHAIN.md).
- Repository layout and module framework: [`docs/v3_specification/16_Engineering_Standards/01_PROJECT_STRUCTURE.md`](../v3_specification/16_Engineering_Standards/01_PROJECT_STRUCTURE.md).
- Coding, testing, and CI/CD standards: the remaining files under [`docs/v3_specification/16_Engineering_Standards/`](../v3_specification/16_Engineering_Standards/).
- Local task runner: the repository-root `justfile` (`just check` mirrors the full CI gate).
- Story and traceability workflow: [`docs/v3_specification/14_Process_and_Traceability/`](../v3_specification/14_Process_and_Traceability/).

This directory starts empty at Phase 0; see
`docs/v3_specification/16_Engineering_Standards/01_PROJECT_STRUCTURE.md` Section 2 for its place
in the `docs/` tree.
