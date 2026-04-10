# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Ollama LLM Bench** is a PySide6 desktop application that benchmarks local LLMs served by Ollama.
It automates inference across multiple models, judges responses using a user-selected judge model, and stores results in SQLite for comparison.

| Component | Technology |
|-----------|-----------|
| Language | Python 3.13+ |
| UI Framework | PySide6 |
| Package Manager | UV with hatchling |
| Database | SQLite via stdlib `sqlite3` |
| LLM Client | ollama-python |
| Dataset | YAML benchmark tasks |
| Linter/Formatter | Ruff |
| Type Checker | Mypy (migrating from pyright) |
| Testing | pytest + pytest-mock + pytest-cov |

## Commands

> **Active package manager is UV with hatchling build backend.**

```bash
# Install
uv sync -q

# Run application
uv run ollama_llm_bench
uv run ollama_llm_bench --log-level info
uv run ollama_llm_bench -d /path/to/dataset_folder

# Lint (sequential order — ruff first, then types, then tests)
uv run ruff check --output-format=concise src/ tests/
uv run ruff format --check src/ tests/
uv run pyright src/
uv run mypy src/

# Tests
uv run pytest -q --tb=short --no-header          # all tests
uv run pytest -q --tb=short tests/path/test.py::test_name  # single test

# Full check (use /check skill or scripts/ai-check.sh)
./scripts/ai-check.sh
```

**Check order is mandatory:** ruff → ruff format → pyright → mypy → pytest. If Mypy and Pyright disagree, **Mypy is authoritative**.

## Important

- **Never read files under `.venv/`** — use `uv run python -c 'import pkg; help(pkg.fn)'` to inspect APIs
- **Never use `pip install`** — always `uv add <pkg> -q` to maintain `uv.lock` integrity
- **Never use `print()`** — use `logging.getLogger(__name__)`
- All code: PySide6 exclusively.
- New interfaces: prefer `Protocol`. Existing: keep `ABC` (`core/interfaces.py`)

## Context Management

When compacting, preserve: list of all modified file paths, any outstanding Mypy errors by file, current pytest failure count and test names, any temporary `# type: ignore` decisions made.

## Architecture

See [architecture.md](.claude/architecture.md) for the full architecture reference.

### Layer Architecture

```
core/ ← services/ ← qt_classes/ ← ui/controllers/ ← ui/widgets/
```

| Package | Responsibility |
|---------|---------------|
| `core/` | Frozen dataclasses, ABCs (`interfaces.py`), StrEnums, constants, SQL schema |
| `services/` | Concrete implementations: `OllamaApi`, `SqLiteDataApi`, `YamlBenchmarkTaskApi`, `SimplePromptBuilderApi`, `AppResultApi`, `TableSerializer` |
| `qt_classes/` | Qt infrastructure: `QtEventBus` (pub/sub), `BenchmarkExecutionTask` (QRunnable), `QtBenchmarkFlowApi` (lifecycle), `MetaQObjectABC` |
| `ui/controllers/` | Controllers mediating UI ↔ services: `NewRunWidgetController`, `PreviousRunWidgetController`, `ResultWidgetController`, `LogWidgetController`, `StatusListener` |
| `ui/widgets/` | PySide6 widgets: `MainWindow` → `CentralWidget` (QSplitter) → panels |
| `utils/` | Pure utility functions: text parsing, time formatting, run sorting |

### Dependency Injection

- `ContextProvider` — thread-safe singleton using `QMutex`
- `ApplicationContext` — immutable holder of all service and controller instances
- `_create_app_context()` — factory function that wires all components
- Constructor injection with keyword-only args: `def __init__(self, *, dep: DepApi)`

### EventBus

`QtEventBus` is the central pub/sub hub using `Signal` (PySide6). All background-to-UI communication goes through EventBus signals for thread safety. Key signal categories: run lifecycle, model lists, log output, table data, progress updates, global messages.

### Benchmark Pipeline

Runs in `BenchmarkExecutionTask(QRunnable)` on `QThreadPool`:
1. **Initialize** — load tasks from YAML, create run + results in SQLite
2. **Benchmark** — warm up model → inference per task → store responses
3. **Judge** — warm up judge model → evaluate responses → store scores
4. **Results** — compute averages → emit to UI via EventBus

Pipeline **never throws** — errors captured in `BenchmarkResult.error_message`.

## Coding Rules

### Python & Typing
- Python 3.13+. Strict type hints on every function, method, and variable.
- `@dataclass(frozen=True)` for all data-holder classes. `StrEnum` for string enums.
- `@override` on all overridden methods.
- No magic numbers — use named constants. No repeated string literals.
- `Optional[T]` or `T | None` for nullable types.

### Architecture & Imports
- Every service has an ABC in `core/interfaces.py`; concrete classes subclass the ABC.
- **Absolute imports only**: `from ollama_llm_bench.core.models import BenchmarkRun`.
- All external dependencies injected via constructor with keyword-only args.
- No cyclic dependencies — insert an ABC to break cycles.
- New interfaces: prefer `Protocol` (structural typing). Existing: keep `ABC`.

### Visibility
- All attributes and methods private by default (leading `_`).
- Expose public attributes via `@property`.
- Only interact with other objects through their public APIs.

### PySide6
- PySide6 exclusively throughout the codebase.
- `MetaQObjectABC` metaclass when combining `QObject` + `ABC` (see `qt_classes/meta_class.py`).
- UI updates on main thread only. Background work via `QThreadPool` + `QRunnable`.
- `QRunnable` uses nested `Signals(QObject)` class for typed signal emission.

### Error Handling
- Pipeline methods (`run()`, `_execute_benchmark()`) never throw to callers.
- Capture errors in model fields: `BenchmarkResult.error_message`, `InferenceResponse.has_error`.
- One action per except: log OR reraise — never both.
- Use `logging.getLogger(__name__)` — never `print()`.

### Cleanup
- Remove unused imports, variables, and methods before committing.
- No `# noqa` without specific rule code. No `# type: ignore` without error code.

## Rules Reference

| Rule | Globs | Description |
|------|-------|-------------|
| [coding-style](rules/coding-style.md) | `src/**/*.py` | Type hints, naming, Protocol vs ABC, functions, classes, SOLID, DI |
| [code-documentation](rules/code-documentation.md) | `src/**/*.py` | Google-style docstrings, obligation levels, TODO format |
| [pyside6-app-development](rules/pyside6-app-development.md) | `qt_classes/**/*.py, ui/**/*.py` | Qt event loop, signals/slots, widgets, threading |
| [project-structure](rules/project-structure.md) | `src/**/*.py, pyproject.toml` | Layer architecture, package responsibilities, import rules |
| [logging](rules/logging.md) | `src/**/*.py` | structlog target, log levels, thread-safe Qt logging |
| [testing](rules/testing.md) | `tests/**/*.py` | Test pyramid, fixtures, mocking with spec=, coverage |
| [external-libraries](rules/external-libraries.md) | `pyproject.toml, src/**/*.py` | Approved/banned libraries, evaluation criteria |
| [formatting](rules/formatting.md) | `*.py, pyproject.toml` | Ruff two-step, editorconfig, import sorting |
| [linting](rules/linting.md) | `*.py, pyproject.toml` | Ruff + Mypy, noqa rules, architecture enforcement |
| [uv-project](rules/uv-project.md) | `pyproject.toml, uv.lock` | UV commands, dependency management, CI integration |
| [repository-documentation](rules/repository-documentation.md) | `*.md, docs/**/*.md` | README structure, ADR format, changelog, writing standards |

## Skills Reference

| Skill | Description | When to Use |
|-------|-------------|-------------|
| [python-developer](skills/python-developer/) | Coding standards, DI patterns, examples, logging, docstrings, dependencies | Writing or reviewing any Python code |
| [pyside6](skills/pyside6/) | Threading, signals/slots, MetaQObjectABC, EventBus patterns | Writing Qt/UI code in `qt_classes/` or `ui/` |
| [project-docs](skills/project-docs/) | README structure, ADR format, inline comments, documentation lifecycle | Writing or updating project documentation |
| [create-mermaid-diagrams](skills/create-mermaid-diagrams/) | Mermaid syntax rules, diagram types, validation checklist | Creating or updating architecture diagrams |
| [write-pytest-tests](skills/write-pytest-tests/) | Test pyramid, fixtures, mocking, coverage, GUI isolation | Writing or reviewing test code |

## Agents Reference

| Agent | Model | Description | Use After |
|-------|-------|-------------|-----------|
| [investigator](agents/investigator.md) | haiku | Read-only codebase mapping, data flow tracing, modification scope | Starting any new task |
| [architect](agents/architect.md) | sonnet | Technical design, trade-off analysis, PLAN.md creation | Investigation, before implementation |
| [coder](agents/coder.md) | sonnet | Surgical implementation of one PLAN.md step at a time | Architect produces approved plan |
| [debugger](agents/debugger.md) | sonnet | Root cause analysis, hypothesis-driven diagnosis, minimal fix | Test failure, runtime error |
| [tester](agents/tester.md) | sonnet | Comprehensive pytest tests, boundary conditions, regression tests | After implementation |
| [docs-writer](agents/docs-writer.md) | haiku | README, ADRs, docstrings, CHANGELOG, diagram updates | After feature completion |

**Recommended workflow:** investigator → architect → coder → tester → docs-writer. The debugger is invoked as needed when failures occur.

## Key Files

| File | Purpose |
|------|---------|
| `src/ollama_llm_bench/app_context.py` | DI wiring: `ContextProvider`, `ApplicationContext`, `_create_app_context()` |
| `src/ollama_llm_bench/core/interfaces.py` | All ABCs: `LLMApi`, `DataApi`, `EventBus`, `BenchmarkFlowApi`, etc. |
| `src/ollama_llm_bench/core/models.py` | Frozen dataclasses: `BenchmarkRun`, `BenchmarkResult`, `InferenceResponse`, etc. |
| `src/ollama_llm_bench/qt_classes/qt_event_bus.py` | `QtEventBus` — pub/sub via `Signal` (PySide6) |
| `src/ollama_llm_bench/qt_classes/qt_benchmark_execution_task.py` | `BenchmarkExecutionTask` — QRunnable background worker |
| `src/ollama_llm_bench/qt_classes/meta_class.py` | `MetaQObjectABC` — metaclass for QObject + ABC |
| `src/ollama_llm_bench/services/ollama_llm_api.py` | `OllamaApi` — Ollama client wrapper |
| `src/ollama_llm_bench/services/sq_lite_data_api.py` | `SqLiteDataApi` — SQLite CRUD operations |
| `docs/project_specification.md` | Full project specification with behavioral requirements |
