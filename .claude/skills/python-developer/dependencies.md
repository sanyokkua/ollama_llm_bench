# Python Developer — Approved Libraries

Dependency rules for Ollama LLM Bench. See [SKILL.md](SKILL.md) for general Python rules.

---

## Critical Rules

- MUST NOT add Django, Flask, FastAPI, SQLAlchemy, or any web/ORM framework
- MUST use `pathlib.Path` — MUST NOT use `os.path` in new code
- MUST use `time.time()` for elapsed measurements — MUST NOT use `datetime.now()` without timezone
- MUST use stdlib `sqlite3` — MUST NOT add SQLAlchemy or other ORM
- Approval required before adding any new third-party dependency

---

## Approved Libraries (in `pyproject.toml`)

### Core Framework

| Library | Min Version | Role |
|---------|-------------|------|
| **PySide6** | 6.0 | Qt UI framework |
| **ollama** | 0.5.1 | Ollama Python client for LLM inference |
| **PyYAML** | 6.0.2 | YAML parsing for benchmark dataset files |

### Recommended (Not Yet Added)

| Library | Min Version | Role |
|---------|-------------|------|
| **pydantic** | 2.0 | External data validation (`BaseModel`, `frozen=True`) |
| **structlog** | — | Structured logging facade (migration target) |
| **httpx** | 0.27 | HTTP client (if needed beyond ollama-python) |

### Development

| Library | Min Version | Role |
|---------|-------------|------|
| **pytest** | 8.0 | Test framework |
| **pytest-cov** | 4.0 | Coverage reporting |
| **pytest-mock** | 3.12 | Mocking utilities |
| **ruff** | 0.9.0 | Linter + formatter |
| **mypy** | 1.14.0 | Type checker (migration target from pyright) |

---

## Usage Rules Per Library

### PySide6

- UI framework — all widget, signal, and threading imports from `PySide6.*`
- `MetaQObjectABC` metaclass when combining `QObject` + `ABC`
- `QThreadPool` + `QRunnable` for background tasks; `Signal`/`Slot` for UI updates
- MUST NOT mix PySide6 and PyQt6 imports in the same file

### ollama

- Used in `OllamaApi` service only — MUST NOT import elsewhere
- Create `ollama.Client` once in `_create_app_context()`
- Set `timeout=300` for long inference calls

### PyYAML

- Used in `YamlBenchmarkTaskApi` for loading task definitions
- MUST use `yaml.safe_load()` — MUST NOT use `yaml.load()` without `Loader=SafeLoader`

### sqlite3 (stdlib)

- Used in `SqLiteDataApi` for all persistence
- MUST use parameterized queries — MUST NOT use string interpolation in SQL
- MUST NOT add SQLAlchemy or any ORM layer

---

## Standard Library Preference

MUST use stdlib before considering third-party alternatives:

| Need | Stdlib Solution |
|------|----------------|
| File paths | `pathlib.Path` |
| Data containers | `dataclasses`, `collections` |
| Date/time | `datetime`, `time` |
| JSON | `json` |
| Regex | `re` |
| Database | `sqlite3` |
| Logging | `logging` |
| Concurrency | `threading`, `concurrent.futures` |

---

## Prohibited Libraries

| Pattern | Reason |
|---------|--------|
| `django`, `flask`, `fastapi` | No web framework — desktop app |
| `sqlalchemy`, `peewee` | No ORM — use stdlib `sqlite3` |
| `PyQt6` | PySide6 only — migration complete |
| `marshmallow` | Use Pydantic v2 for validation |
| `loguru` | Use structlog (migration target) |
| `black`, `autopep8`, `yapf` | Use Ruff |
| `isort` | Use Ruff (I rule) |
| `pendulum` | Use `datetime` + `time` |

---

## Adding a New Dependency

Before adding any new library:
1. Confirm no stdlib API covers the need
2. Check if an existing approved library can be extended
3. Verify: maintained within 12 months, no critical CVEs, approved license (MIT, BSD, Apache-2.0)
4. Transitive dependencies ≤ 15 (prefer ≤ 5)
5. Document in PR description
