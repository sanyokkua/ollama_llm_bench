# Technical Debt & Migration Status

This document catalogues known technical debt, discrepancies between `CLAUDE.md` / rules and the actual code, and missing infrastructure.
It is maintained alongside the code and should be updated whenever debt is added or paid down.

## Summary

| Category | Status |
|---|---|
| Qt framework migration (PyQt6 → PySide6) | Not started — 100% PyQt6 |
| Interface style migration (ABC → Protocol) | Not started — 100% ABC |
| Logging migration (stdlib → structlog) | Not started — 100% stdlib `logging` |
| Test suite | **Absent** — `tests/` directory does not exist |
| CHANGELOG | Absent |
| CODEOWNERS | Absent |
| CI configuration | Absent |
| Pre-commit hooks | Absent |
| ADR directory | Absent |
| `# TODO` / `# FIXME` / `# HACK` comments in source | **Zero** — code is clean from in-line debt markers |

## 1. Documentation vs Reality Discrepancies

The authoritative `CLAUDE.md` (project instructions at the repository root) describes several things as the target state or as "in progress" that are not reflected in the current codebase.
New contributors should treat the code as ground truth and update these discrepancies as migrations land.

| CLAUDE.md / rules claim | Actual state in code | Evidence |
|---|---|---|
| "PySide6 desktop application (migrating from PyQt6)" | All Qt imports are `PyQt6`; zero `PySide6` imports | `pyproject.toml` line 12: `"pyqt6>=6.9.1,<7.0.0"`. Grep of `src/` for `from PySide6` returns zero matches. |
| "New code: PySide6. Existing code: PyQt6" | There is no "new code" written in PySide6 anywhere | 18 source files import `PyQt6.QtCore` or `PyQt6.QtWidgets` |
| "Prefer `Protocol` for new interfaces" | All 9 interfaces in `core/interfaces.py` use `ABC` | `src/ollama_llm_bench/core/interfaces.py` — search for `class .*ABC` vs `class .*Protocol` |
| "structlog wrapping standard `logging`" (logging rule) | Every module uses stdlib `logging.getLogger(__name__)` only | No `import structlog` anywhere |
| "Type Checker: Mypy (migrating from pyright)" | Both `mypy` and `pyright` are configured as dev dependencies; mypy has `strict = true` | `pyproject.toml` `[tool.mypy]` and `[dependency-groups].dev` |
| "Testing: pytest + pytest-mock + pytest-cov" | No tests exist; `tests/` directory is absent | `pyproject.toml` sets `testpaths = ["tests"]` but directory is missing |
| ".claude/architecture.md" references "migrate opportunistically to PySide6 when touching files" | The migration has never been started | Git log + grep |
| "`raise NewError(...) from original`" (coding rule) | `new_run_widget_controller.py` and `qt_benchmark_flow.py` use `raise ValueError(...) from e` correctly | Consistent — no debt here |
| "`@override` on all overridden methods" (coding rule) | Most Qt classes and services use `@override`; `SqLiteDataApi` methods all use it | Consistent |
| Line in `ollama_llm_api.py` signature: `def get_models_list(self) -> List[dict]` | Body actually returns a sorted `list[str]`; annotation is wrong | `src/ollama_llm_bench/services/ollama_llm_api.py:30` |

## 2. Qt Framework Audit

Every Qt-using source file uses `PyQt6`. There are no `PySide6` imports anywhere in `src/`.

### PyQt6 Files (18 total)

| File | Qt modules used |
|---|---|
| `src/ollama_llm_bench/main.py` | `QtWidgets.QApplication` |
| `src/ollama_llm_bench/app_context.py` | `QtCore.QMutex`, `QMutexLocker`, `QThreadPool` |
| `src/ollama_llm_bench/qt_classes/meta_class.py` | `QtCore.QObject` |
| `src/ollama_llm_bench/qt_classes/qt_event_bus.py` | `QtCore.QObject`, `pyqtSignal` |
| `src/ollama_llm_bench/qt_classes/qt_benchmark_execution_task.py` | `QtCore.QObject`, `QRunnable`, `pyqtSignal` |
| `src/ollama_llm_bench/qt_classes/qt_benchmark_flow.py` | `QtCore.QObject`, `QThreadPool`, `pyqtSignal` |
| `src/ollama_llm_bench/ui/main_window.py` | `QtCore.Qt`, `QtWidgets.QMainWindow`, `QApplication`, `QMessageBox` |
| `src/ollama_llm_bench/ui/widgets/central_widget.py` | `QtCore.Qt`, `QtWidgets.QSplitter`, `QVBoxLayout`, `QWidget` |
| `src/ollama_llm_bench/ui/widgets/panels/control_panel.py` | `QtWidgets.*` |
| `src/ollama_llm_bench/ui/widgets/panels/control/control_tab_widget.py` | `QtWidgets.QTabWidget` |
| `src/ollama_llm_bench/ui/widgets/panels/control/new_run_widget.py` | `QtWidgets.*` |
| `src/ollama_llm_bench/ui/widgets/panels/control/previous_run_widget.py` | `QtWidgets.*` |
| `src/ollama_llm_bench/ui/widgets/panels/results_panel.py` | `QtWidgets.*` |
| `src/ollama_llm_bench/ui/widgets/panels/result/result_tab_widget.py` | `QtWidgets.QTabWidget` |
| `src/ollama_llm_bench/ui/widgets/panels/result/log_widget.py` | `QtWidgets.*` |
| `src/ollama_llm_bench/ui/widgets/panels/result/result_widget.py` | `QtWidgets.QTableWidget`, `QTableWidgetItem`, etc. |
| `src/ollama_llm_bench/utils/widget_utils.py` | `QtWidgets.QComboBox` |

### PySide6 Files

**None.** A PyQt6 → PySide6 migration has not been started.

Recommended migration order when the work begins:

1. `meta_class.py` (smallest surface) — confirm the metaclass idiom works under PySide6's `shiboken`.
2. `qt_event_bus.py` — replace `pyqtSignal` → `Signal`.
3. `qt_benchmark_flow.py`, `qt_benchmark_execution_task.py`.
4. `utils/widget_utils.py`.
5. Leaf widgets in `ui/widgets/panels/**`.
6. Container widgets (`central_widget.py`, `control_panel.py`, `results_panel.py`).
7. `ui/main_window.py`.
8. `main.py` and `app_context.py` last (they transitively use Qt types in their constructor signatures).

## 3. Missing Project Infrastructure

### Tests

The `tests/` directory **does not exist**.
`pyproject.toml` is configured as though tests were present:

- `testpaths = ["tests"]`
- `pythonpath = ["src"]`
- `markers = ["unit", "integration", "slow"]`
- Coverage `fail_under = 80`

Running `uv run pytest` currently collects zero tests.
See [testing-guide.md](testing-guide.md) for the target layout and fixture patterns to adopt when tests are added.

### CI / CD

- No `.github/workflows/` directory.
- No pre-commit config (`.pre-commit-config.yaml`).
- No GitLab CI, CircleCI, or any other CI configuration file.

The only quality-gate automation available is the local shell script `scripts/ai-check.sh` (ruff → ruff format → pyright → mypy → pytest).
Nothing enforces the pipeline on pull requests.

### Governance Files

- No `CHANGELOG.md` at the repository root.
- No `CODEOWNERS` file.
- No `CONTRIBUTING.md`.
- No `docs/adr/` or `docs/architecture/adrs/` directory for Architecture Decision Records.

## 4. Code-Level Observations

The source tree is clean of `TODO`, `FIXME`, `HACK`, and `XXX` comments, so there are no in-line debt markers to track.

A few implementation details worth noting when touching the relevant files:

| Area | Observation | File |
|---|---|---|
| Type annotation bug | `OllamaApi.get_models_list` is annotated `-> List[dict]` but returns a sorted `list[str]` | `src/ollama_llm_bench/services/ollama_llm_api.py:30` |
| Scoring range mismatch | `parse_judge_response` docstring says `0.0-100.0` and validates `0 <= grade <= 100`, while the judge prompt (`SYSTEM_PROMPT`) instructs the model to emit a float `0.00–1.00`. In practice scores land on the 0.0–1.0 scale and are multiplied by 100 only in `TableSerializer` for display | `src/ollama_llm_bench/utils/text_utils.py:95`, `src/ollama_llm_bench/core/prompt_constants.py:6`, `src/ollama_llm_bench/services/table_serializer.py:43` |
| Foreign key not enforced | SQLite foreign keys are declared (`run_id INTEGER NOT NULL REFERENCES benchmark_runs(run_id)`) but no `PRAGMA foreign_keys = ON` is issued on connection, so cascading deletes are not enforced by the DB engine. Run deletion relies on application-level cleanup | `src/ollama_llm_bench/core/sql_constants.py:11`, `src/ollama_llm_bench/services/sq_lite_data_api.py:63` |
| `None` encoded as `-1` | `QtEventBus.emit_run_id_changed` emits `value or -1` because `pyqtSignal(int)` cannot transport `None`. Subscribers must treat `-1` as "no run selected" | `src/ollama_llm_bench/qt_classes/qt_event_bus.py:170` |
| Unused judge signal | `_models_judge_changed` is emitted during initialization but no widget subscribes to it | `src/ollama_llm_bench/qt_classes/qt_event_bus.py:26` |
| Warm-up sleep | `OllamaApi.warm_up` blocks the background thread for up to `5 × 30 s = 150 s` of `time.sleep` on full failure. Cancellation is not checked during sleep | `src/ollama_llm_bench/services/ollama_llm_api.py:60` |
| `print()` fallback in `main.py` | `main.py` uses `print(..., file=sys.stderr)` for fatal boot errors. This is the only `print()` in the codebase and is deliberate: logging may not be configured yet at the point of failure | `src/ollama_llm_bench/main.py:70` |
| `db.sqlite` committed to repo | A 53 KB `db.sqlite` file sits at the repo root. This is the default application database path (`Path.cwd() / db.sqlite`) and was likely committed accidentally | `git ls-files db.sqlite` |
| `.DS_Store` committed to repo | macOS metadata file is in the working tree | — |

## 5. Prioritized Improvements

Ranked by impact-over-effort for a new maintainer:

1. **Stand up a test suite.** Zero coverage is the single largest risk. Start with `utils/text_utils.py:parse_judge_response` and `services/app_result_api.py` — both are pure Python, no Qt, high value. See [testing-guide.md](testing-guide.md).
2. **Add a GitHub Actions workflow** that runs `scripts/ai-check.sh` on every PR. Mirror the script's `ruff → mypy → pytest` sequence.
3. **Fix `OllamaApi.get_models_list` annotation** to match the runtime return type (`list[str]`). One-line fix, catches a potential mypy strict failure.
4. **Decide and document the scoring scale.** Either rename `parse_judge_response` return to `score_0_to_1` and update the validator, or scale the judge prompt to emit 0–100. Discrepancy between prompt and parser is a trap waiting to spring.
5. **Remove `db.sqlite` and `.DS_Store`** from git and add them to `.gitignore`.
6. **Add `CHANGELOG.md`** per the Keep a Changelog format. The project is versioned (`0.1.1`) but no release notes exist.
7. **Start the PySide6 migration** in the order listed in §2. Pin-point any PySide6-vs-PyQt6 divergences (metaclass behaviour, `QStringList` translations, `exec_` → `exec`).
8. **Migrate `core/interfaces.py` to `Protocol`** where the ABC provides no shared state — `LLMApi`, `DataApi`, `EventBus`, `BenchmarkTaskApi` are pure contract surfaces. `ResultApi`, `PromptBuilderApi`, `BenchmarkFlowApi` currently store constructor state and must stay as ABCs (or be restructured).
9. **Enable `PRAGMA foreign_keys = ON`** in `SqLiteDataApi._init_db` so delete cascades are enforced by SQLite rather than by convention.
10. **Write ADRs** for the three load-bearing decisions already locked in: (a) `QThreadPool(maxThreadCount=1)` — serial execution; (b) `ContextProvider` singleton via `QMutex`; (c) resumability via three-state `BenchmarkResultStatus`.

## Related Documents

- [architecture.md](architecture.md) — target architecture these gaps relate to
- [testing-guide.md](testing-guide.md) — the test layout this repo does not yet have
- [configuration.md](configuration.md) — authoritative config references
