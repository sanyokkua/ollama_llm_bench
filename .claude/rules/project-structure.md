---
description: "Project structure rules — src/ layout, package organization, layer dependencies, import rules"
globs: "src/**/*.py,pyproject.toml"
alwaysApply: false
---

# Project Structure

## Critical Rules

- MUST use the `src/` layout: all importable code under `src/ollama_llm_bench/`
- MUST NOT import any Qt module (`PySide6`, `PyQt6`) in `core/` — it MUST be pure Python
- Business logic MUST live in `core/` — MUST NOT place business logic in UI widgets or controllers
- Dependencies MUST point inward: `ui/widgets/` → `ui/controllers/` → `backend/services/` → `backend/core/`
- Tests MUST live in `tests/` at the project root — MUST NOT place tests inside `src/`
- MUST use `pyproject.toml` as the single configuration source

## Layer Architecture

This project uses a layered architecture with controller-mediated UI:

```
┌─────────────────────────┐
│     ui/widgets/          │   PySide6 widgets — UI rendering
│  (views, panels, tabs)   │
└──────────┬──────────────┘
           │ calls
           ▼
┌─────────────────────────┐
│     ui/controllers/      │   Widget controllers — mediate UI↔services
│  (business flow logic)   │
└──────────┬──────────────┘
           │ uses
           ▼
┌─────────────────────────┐
│     backend/services/    │   Concrete service implementations
│  (providers, evaluators) │
└──────────┬──────────────┘
           │ implements
           ▼
┌─────────────────────────┐
│     backend/core/        │   Pure Python — ABCs, models, constants
│  (interfaces, models)    │
└─────────────────────────┘
```

### Qt Infrastructure Layer

`ui/qt_classes/` sits alongside but bridges `backend/core/` and `ui/`:
- Contains Qt threading infrastructure (`QRunnable`, `QThreadPool`)
- Contains `EventBus` (pub/sub via Qt signals)
- Contains `MetaQObjectABC` metaclass for combining `QObject` + `ABC`

## Package Responsibilities

| Package | Allowed Imports | Role |
|---|---|---|
| `backend/core/` | stdlib only | Domain models, ABCs, constants, SQL schema |
| `backend/services/` | stdlib, third-party, `backend/core/` | Concrete service implementations |
| `ui/qt_classes/` | stdlib, PySide6, `backend/core/`, `backend/services/` | Qt threading, EventBus |
| `ui/controllers/` | stdlib, `backend/core/`, `backend/services/`, `ui/qt_classes/` | Business flow mediation |
| `ui/widgets/` | stdlib, PySide6, `backend/core/`, `ui/controllers/` | UI rendering |
| `backend/utils/` | stdlib, `backend/core/` | Pure utility functions |
| `dataset/` | — | YAML benchmark task files |

## Import Rules

- MUST use absolute imports from root package: `from ollama_llm_bench.backend.core.models import BenchmarkRun`
- MUST NOT use relative imports (`.models`, `..utils`)
- MUST organize imports: standard library → third-party → local, alphabetically within groups

## import-linter Configuration (Target)

```toml
[tool.importlinter]
root_packages = ["ollama_llm_bench"]

[[tool.importlinter.contracts]]
name = "Core must not import Qt modules"
type = "forbidden"
source_modules = ["ollama_llm_bench.backend.core"]
forbidden_modules = ["PySide6", "PyQt6"]

[[tool.importlinter.contracts]]
name = "Layer dependency direction"
type = "layers"
layers = [
    "ollama_llm_bench.ui",
    "ollama_llm_bench.backend.services",
    "ollama_llm_bench.backend.core",
]
```

## File Placement

| Component | Location |
|---|---|
| Source code | `src/ollama_llm_bench/` |
| Business logic, models, ABCs | `src/ollama_llm_bench/backend/core/` |
| Service implementations | `src/ollama_llm_bench/backend/services/` |
| Qt infrastructure | `src/ollama_llm_bench/ui/qt_classes/` |
| Widget controllers | `src/ollama_llm_bench/ui/controllers/` |
| UI widgets | `src/ollama_llm_bench/ui/widgets/` |
| Utilities | `src/ollama_llm_bench/backend/utils/` |
| Benchmark tasks | `src/ollama_llm_bench/dataset/` |
| Tests | `tests/` |
| Documentation | `docs/` |
| ADRs | `docs/adr/` |

## Testing Structure

```
tests/
├── conftest.py
├── unit/
│   ├── core/
│   │   ├── test_models.py
│   │   └── test_interfaces.py
│   ├── services/
│   │   └── test_app_result_api.py
│   └── utils/
│       └── test_text_utils.py
└── integration/
    └── test_sq_lite_data_api.py
```

## Anti-Patterns

- MUST NOT create a "God" `MainWindow` with database access and business logic — use controllers
- MUST NOT import Qt in `core/` — Core MUST be usable outside the GUI context
- MUST NOT place tests inside `src/` — they get packaged with the application
- MUST NOT mix architectural patterns at the same directory level
