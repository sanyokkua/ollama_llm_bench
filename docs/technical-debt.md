# Technical Debt & Migration Status

This document catalogues known technical debt, discrepancies between guidance docs and the actual code, and missing infrastructure. It is maintained alongside the code and should be updated whenever debt is added or paid down.

Last reviewed: 2026-05-10 (V2 cleanup pass).

## Summary

| Category | Status |
|---|---|
| Qt framework migration (PyQt6 → PySide6) | **Complete** — 100% PySide6 |
| Multi-provider abstraction (`OllamaApi` → `ProviderRegistry`) | **Complete** — V1 `OllamaApi`/`LLMApi` ABC removed in cleanup pass |
| Build backend (Poetry → UV + hatchling) | **Complete** |
| Interface style (ABC → Protocol) | **Partial** — V2 services use `Protocol`; legacy `BenchmarkFlowApi`, `DataApi`, `EventBus`, `ResultApi`, `AppContext`, `TableSerializerApi` remain `ABC` |
| Logging facade (stdlib → structlog) | Not started — 100% stdlib `logging`. Lazy `%` formatting now enforced via Ruff `G` rule. |
| Test suite | **Live** — 1207 tests pass under `pytest` (~66s). Branch coverage target 80% in `pyproject.toml`. |
| CI configuration | Absent — only the local `scripts/ai-check.sh` |
| Pre-commit hooks | Absent |
| CHANGELOG | Absent |
| CODEOWNERS | Absent |
| ADR directory | Absent |
| `# TODO` / `# FIXME` / `# HACK` comments in source | **Zero** — clean |

## 1. Open Items

| Item | Why it matters | Where |
|---|---|---|
| ABC → Protocol migration | New code must `prefer Protocol`. Several large legacy ABCs (`DataApi`, `EventBus`, `BenchmarkFlowApi`, `ResultApi`, `AppContext`) are pure contract surfaces and could be `Protocol`. Refactoring them is non-trivial because some store constructor state. | `src/ollama_llm_bench/backend/core/interfaces.py` |
| `structlog` migration | Logging rule prescribes structlog; current code is stdlib `logging`. No active migration plan. Stay disciplined with lazy `%` formatting until then. | All `logger.getLogger(__name__)` sites |
| Foreign-key enforcement | SQLite schema declares `REFERENCES` but no `PRAGMA foreign_keys = ON` is issued on connection — cascades rely on application-level cleanup. | `backend/services/sq_lite_data_api.py` |
| `None`-as-`-1` event payload | `QtEventBus.emit_run_id_changed` emits `value or -1` because `Signal(int)` cannot transport `None`. Subscribers must treat `-1` as "no run selected". | `ui/qt_classes/qt_event_bus.py` |
| CHANGELOG.md | Project is versioned (`0.1.1`) but has no Keep-a-Changelog entries. | repo root |
| GitHub Actions workflow | `scripts/ai-check.sh` is the only quality gate; nothing enforces it on pull requests. | `.github/workflows/` (missing) |
| ADR directory | No `docs/adr/` to capture load-bearing decisions: serial QThreadPool, ContextProvider singleton, three-state `BenchmarkResultStatus` resumability. | `docs/adr/` (missing) |

## 2. Recently Resolved

| Item | Resolution | Date |
|---|---|---|
| `OllamaApi` / `LLMApi` ABC dead code | Deleted; benchmark execution uses `ProviderRegistry` exclusively. `ollama` runtime dependency dropped. | 2026-05-10 |
| `BenchmarkTaskApi` / `YamlBenchmarkTaskApi` V1 stack | Deleted; V2 `TaskFileLoader` is the only path. | 2026-05-10 |
| `PromptBuilderApi` / `SimplePromptBuilderApi` V1 stack | Deleted; `JudgePromptService` is canonical. | 2026-05-10 |
| `ITableSerializer` rename | Renamed to `TableSerializerApi` (no Hungarian `I`-prefix). | 2026-05-10 |
| Embedded fonts in `ui/style/fonts/` | Deleted (~2.3 MB) — never registered with `QFontDatabase.addApplicationFont`. | 2026-05-10 |
| Pylance unreachable warning in `app_paths.py` | Refactored platform dispatch to break literal narrowing. | 2026-05-10 |
| Magic stage strings | Converted to `StageName(StrEnum)` in `backend/core/stages_constants.py`. | 2026-05-10 |
| Undocumented Protocol/ABC members in `interfaces.py` and `ui_controllers.py` | Google-style docstrings added. | 2026-05-10 |
| f-string log calls (~70) | Converted to lazy `%` formatting; Ruff `G004` enforced. | 2026-05-10 |
| Stale plans (`PLAN.md`, `VALIDATION_REPORT.md`, `docs/v2_plans/`, `docs/v2_validation/`) | Archived to `.AdditionalDocs/archive/2026-05-10/`, removed from git. | 2026-05-10 |

## 3. Prioritized Next Steps

Ranked by impact-over-effort for a maintainer:

1. **GitHub Actions workflow** that runs `ruff check` + `ruff format --check` + `mypy` + `pytest` on every PR.
2. **Enable `PRAGMA foreign_keys = ON`** in `SqLiteDataApi._init_db` so delete cascades are enforced by the DB engine.
3. **Write ADRs** for: (a) serial `QThreadPool(maxThreadCount=1)`; (b) `ContextProvider` singleton via `QMutex`; (c) `BenchmarkResultStatus` three-state resumability; (d) provider plugin layout (OpenAI-compatible / Anthropic / Gemini).
4. **Add `CHANGELOG.md`** per Keep a Changelog. Cover at minimum: 0.1.1 release with multi-provider V2.
5. **ABC → Protocol** for `DataApi`, `EventBus`, and `AppContext` — these are pure contracts. `BenchmarkFlowApi` and `ResultApi` store DI state and need restructuring before migration.
6. **`structlog` migration** — stdlib `logging` works but the rule docs target structlog. Plan a single-PR sweep with QueueHandler + processors.

## Related Documents

- [architecture.md](architecture.md) — current architecture
- [testing-guide.md](testing-guide.md) — fixture patterns for the existing test suite
- [configuration.md](configuration.md) — authoritative config references
