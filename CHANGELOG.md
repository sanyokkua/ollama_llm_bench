# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Breaking

- Full ground-up rewrite of the application against the v3 specification at
  `docs/v3_specification/`. The previous PySide6 codebase is removed in its entirety; there is
  no migration path from it and no backward compatibility with its data or configuration.
  Rebuilding starts from Phase 0 (repository governance and scaffold) — see
  `docs/reference_planning_docs/01_PHASE_BREAKDOWN.md`.

### Added

- Repository scaffold for the v3 rewrite: `pyproject.toml` (uv/ruff/mypy/import-linter/pytest
  configuration), `justfile` (local CI-parity task runner), the `src/ollama_llm_bench/`
  three-layer package tree (`backend/`, `adapters/`, `ui/`), the `tests/` tree, the
  traceability tooling (`scripts/trace.py`, `scripts/validate_traceability.py`), and the two
  GitHub Actions workflows (`pr-gate.yml`, `release.yml`).
- Three accepted Architecture Decision Records: `docs/adr/0001-programmatic-qt-widgets-theming.md`,
  `docs/adr/0002-scoped-reactive-stores-and-event-bus.md`,
  `docs/adr/0003-uv-build-and-unsigned-distribution.md`.
- Backend domain vocabulary (`backend/domain/`): 27 closed enumerations (`StrEnum`), 33
  cross-boundary `msgspec.Struct` records, 7 type aliases, 14 constrained types per
  `docs/v3_specification/10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, establishing the
  foundational Qt-free domain model for Phase 1.
