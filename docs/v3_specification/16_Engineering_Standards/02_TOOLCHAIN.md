# Toolchain and Dependencies

**Status:** Draft
**Owner:** architect
**Audience:** architect, coder
**Last Updated:** 2026-06-06
**Cross-references:** `16_Engineering_Standards/01_PROJECT_STRUCTURE.md`, `16_Engineering_Standards/03_CODING_STANDARDS.md`, `16_Engineering_Standards/07_TESTING_STANDARD.md`, `13_Distribution_and_Release/01_PLATFORM_SUPPORT.md`

This document fixes the complete development toolchain for Ollama LLM Bench and the full set of runtime and development dependencies. It defines `uv` as the package and environment manager, `uv_build` as the build backend, `ruff` as the linter and formatter, `mypy --strict` as the type-checking authority, the dependency-version policy, the consolidated version table, and the structure of `pyproject.toml`. Every tool listed here is mandatory; every tool not listed is excluded unless added through a recorded Architecture Decision Record.

---

## Table of Contents

1. Purpose and scope
2. Package and environment manager — uv
3. Build backend — uv_build
4. Linter and formatter — ruff
5. Type checker — mypy
6. Architecture enforcement — import-linter
7. Dependency-version policy
8. Consolidated version table
9. pyproject.toml structure
10. Local task runner
11. Banned tools and libraries

---

## 1. Purpose and scope

The toolchain is uniform across every developer machine and the continuous-integration environment. There is one package manager, one linter, one formatter, one type checker, and one build backend. Local development and CI run the same commands against the same locked dependency set, so a green local check predicts a green CI run.

The application targets **Python 3.13** exactly and the **PySide6 6.8+** Qt binding using Qt Widgets built programmatically. There is no QML. The build backend is `uv_build`. The architecture is a hexagonal monolith with a single manual composition root and no dependency-injection container.

## 2. Package and environment manager — uv

`uv` is the sole package manager, environment manager, and Python-version manager. It replaces `pip`, `pip-tools`, `poetry`, `pipenv`, `virtualenv`, and `pyenv`.

Rules:

- The project is scaffolded and managed with `uv`. Dependencies are added with `uv add` and `uv add --dev`, never with `pip install`.
- Code is executed with `uv run`, never with a bare `python`.
- `uv.lock` is committed to version control. It is never hand-edited and never added to `.gitignore`.
- The Python version is pinned in `.python-version` to the exact patch release `3.13.3`. `uv` reads this file to provision the interpreter.
- CI runs `uv sync --frozen`, which fails if `uv.lock` is stale relative to `pyproject.toml`. Production builds run `uv sync --frozen --no-dev`.

Common commands:

```bash
uv sync                        # Install dependencies, respecting uv.lock
uv sync --frozen --all-extras --dev    # CI / full local setup
uv run python -m ollama_llm_bench      # Run the application
uv run ruff check src tests            # Lint
uv run mypy --strict src               # Type-check
uv run pytest                          # Test
uv add <package>                       # Add a runtime dependency
uv add --dev <package>                 # Add a development dependency
uv lock --upgrade                      # Refresh the lockfile to latest allowed versions
uv lock --upgrade --dry-run            # Preview available upgrades without committing
```

## 3. Build backend — uv_build

The build backend is `uv_build`, the native build backend shipped with `uv`. It is selected over `hatchling` and `setuptools` because the application is a packaged desktop program with no PyPI publication step: `uv_build` is the lightest backend that produces a correct wheel from the `src/` layout, and using it keeps the build toolchain inside `uv` with no extra dependency.

`pyproject.toml` declares it as the build system:

```toml
[build-system]
requires = ["uv_build>=0.9.0,<0.10.0"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "ollama_llm_bench"
module-root = "src"
```

The wheel is built from `src/ollama_llm_bench/`. PyInstaller consumes the installed package to produce the per-OS desktop binaries; the colocated `tests/` directories are excluded at PyInstaller time.

## 4. Linter and formatter — ruff

`ruff` is the sole linter and formatter. It replaces `flake8`, `pylint`, `pyflakes`, `pycodestyle`, `black`, `autopep8`, `yapf`, and `isort`.

Configuration lives in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py313"
src = ["src", "tests"]

[tool.ruff.lint]
select = [
    "E", "F", "W",   # pycodestyle + pyflakes
    "I",             # import sorting
    "B",             # bugbear
    "UP",            # pyupgrade
    "S",             # bandit security
    "SIM",           # simplify
    "A",             # builtin shadowing
    "C4",            # comprehensions
    "RUF",           # ruff-specific
    "TID",           # tidy imports
    "PL",            # pylint subset
    "TC",            # type-checking imports
    "ARG",           # unused arguments
    "G",             # logging format
    "DTZ",           # datetime timezone
    "T20",           # no print
    "BLE",           # blind except
    "FBT",           # boolean trap
    "PIE",
    "RET",
]
ignore = ["E501"]    # line length is enforced by the formatter

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "all"

[tool.ruff.lint.isort]
known-first-party = ["ollama_llm_bench"]
combine-as-imports = true
force-sort-within-sections = true

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
line-ending = "lf"
docstring-code-format = true

[tool.ruff.lint.per-file-ignores]
"src/ollama_llm_bench/backend/*/__init__.py" = ["F401"]   # intentional re-exports
"src/ollama_llm_bench/backend/*/api.py" = ["F401"]
"src/ollama_llm_bench/adapters/*/__init__.py" = ["F401"]
"src/ollama_llm_bench/adapters/*/api.py" = ["F401"]
"src/ollama_llm_bench/ui/*/__init__.py" = ["F401"]
"src/ollama_llm_bench/ui/*/api.py" = ["F401"]
"src/ollama_llm_bench/compose.py" = ["F401"]
"tests/**/*" = ["ARG", "S101"]                     # tests may use assert
"tests/typing_negative/**/*" = ["F401", "F841"]    # intentionally broken types
```

The execution order is mandatory: `ruff check --fix` first, `ruff format` second. Reversing the order produces incorrect results. CI runs both in read-only `--check` mode and never auto-fixes.

Every suppression carries its specific rule code and a justification — `# noqa: F401  # re-export` — never a bare `# noqa`. `RUF100` detects stale suppressions.

## 5. Type checker — mypy

`mypy` is the authoritative type checker and the gate that blocks merges. An IDE may additionally run `pyright`, but only `mypy` decides correctness.

```toml
[tool.mypy]
python_version = "3.13"
strict = true
warn_unused_ignores = true
warn_redundant_casts = true
warn_return_any = true
warn_unreachable = true

[[tool.mypy.overrides]]
module = "tests.typing_negative.*"
ignore_errors = true
```

`strict = true` enables the full strict bundle, including `--no-implicit-reexport` and `--disallow-untyped-defs`. The `tests.typing_negative.*` override exists because those files are designed to fail type-checking; the test runner inverts their exit code (see `07_TESTING_STANDARD.md`).

Every type suppression carries its specific error code and a justification — `# type: ignore[no-untyped-call]  # third-party stub gap` — never a bare `# type: ignore`.

## 6. Architecture enforcement — import-linter

`import-linter` enforces the module boundaries defined in `01_PROJECT_STRUCTURE.md`. Its contracts live in `pyproject.toml` under `[tool.importlinter]` and are run with `uv run lint-imports`. The full contract set — Qt-free backend, private internals, provider independence, sole composition root — is specified in `01_PROJECT_STRUCTURE.md` Section 9.

`pytest-archon` complements `import-linter` for symbol-level rules that import analysis cannot see; those tests are specified in `07_TESTING_STANDARD.md`.

## 7. Dependency-version policy

The policy is **always the latest stable release at the time of work**. There is no long-term version freezing. When a module is implemented or revised, its dependencies are taken at the newest stable version, the lockfile is refreshed with `uv lock --upgrade`, and the version table in this document (Section 8) is updated to record the versions in use. The specification is a living document on this point: the version table is kept current with each dependency refresh.

The lower bounds in `pyproject.toml` express the floor that the code is known to require; they are not pins. `uv.lock` records the exact resolved versions actually installed, and is the reproducibility anchor. `psygnal` is the single exception that carries an upper bound, because its minor releases have historically renamed public symbols — it is constrained to a single minor series and that series is advanced deliberately.

A new dependency is admissible only if it has a recent release, no known critical vulnerabilities, more than one maintainer, a permissive license (MIT, BSD, Apache-2.0, ISC, PSF), and a small transitive footprint. Adding a dependency that fails any of these criteria requires a recorded Architecture Decision Record.

## 8. Consolidated version table

The following are the dependency floors in effect as of the **Last Updated** date of this document. Each refresh advances these to the newest stable release and updates this table.

### Runtime dependencies

| Package | Floor | Role |
|---|---|---|
| `PySide6` | `>=6.8,<6.9` | Qt 6 binding; UI layer (Qt Widgets, programmatic); `QThreadPool` worker execution in the adapter (D-R-01) |
| `msgspec` | `>=0.21.0` | All DTOs and cross-boundary data; serialization |
| `psygnal` | `==0.15.*` | Reactive signals for the store layer (upper bound deliberate) |
| `structlog` | `>=25.5.0` | Structured logging over the standard library `logging` |
| `icontract` | `>=2.7.3` | Design-by-contract decorators on public APIs |
| `ruamel.yaml` | `>=0.18` | Comment-preserving YAML for benchmark task files |
| `platformdirs` | `>=4.0` | Cross-platform application-data directory resolution |
| `click` | `>=8.1` | Command-line interface for the diagnostic doctor commands |
| `typing-extensions` | `>=4.5.0` | `@deprecated` (PEP 702) runtime support |

### Development dependencies

| Package | Floor | Role |
|---|---|---|
| `pytest` | `>=8.0` | Test framework |
| `pytest-qt` | `>=4.5` | Widget tests; `qtbot`; `QAbstractItemModelTester` |
| `pytest-cov` | `>=4.0` | Coverage measurement |
| `pytest-mock` | `>=3.12` | `mocker` fixture with `spec=` enforcement |
| `pytest-archon` | `>=0.0.7` | Architecture tests at the import and symbol level |
| `pytest-randomly` | `>=3.15` | Test-order randomization |
| `pytest-rerunfailures` | latest | Flake detection for opt-in local slow-test runs |
| `pytest-httpserver` | latest | Provider wire stub — local HTTP server for transport-level adapter tests (`07_TESTING_STANDARD.md` §7a) |
| `hypothesis` | latest | Property-based and stateful testing |
| `icontract-hypothesis` | latest | Property tests inferred from `icontract` contracts |
| `freezegun` | `>=1.4` | Deterministic time in tests |
| `ruff` | `>=0.9.0` | Linter and formatter |
| `mypy` | `>=1.16` | Static type checker (`mypy 1.16+` is required for PEP 702 `@deprecated` on `@property`) |
| `import-linter` | `>=2.11` | Module-boundary contracts |
| `pip-audit` | `>=2.10` | Dependency vulnerability scanning |

### Build dependencies

| Package | Floor | Role |
|---|---|---|
| `uv_build` | `>=0.9.0,<0.10.0` | Build backend |
| `pyinstaller` | `>=6.0` | Produces the per-OS desktop binaries (`--onedir`) |

## 9. pyproject.toml structure

`pyproject.toml` is the single source of truth for project metadata, dependencies, and every tool's configuration. Its skeleton:

```toml
[build-system]
requires = ["uv_build>=0.9.0,<0.10.0"]
build-backend = "uv_build"

[project]
name = "ollama-llm-bench"
version = "1.0.0"
description = "Desktop application for benchmarking local and remote LLMs."
requires-python = "==3.13.*"
license = { text = "MIT" }
readme = "README.md"

dependencies = [
    "PySide6>=6.8,<6.9",
    "msgspec>=0.21.0",
    "psygnal==0.15.*",
    "structlog>=25.5.0",
    "icontract>=2.7.3",
    "ruamel.yaml>=0.18",
    "platformdirs>=4.0",
    "click>=8.1",
    "typing-extensions>=4.5.0",
]

[project.scripts]
ollama-llm-bench = "ollama_llm_bench.__main__:main"

[dependency-groups]
dev = [
    "pytest>=8.0", "pytest-qt>=4.5", "pytest-cov>=4.0", "pytest-mock>=3.12",
    "pytest-archon>=0.0.7", "pytest-randomly>=3.15", "pytest-rerunfailures",
    "pytest-httpserver",
    "hypothesis", "icontract-hypothesis", "freezegun>=1.4",
    "ruff>=0.9.0", "mypy>=1.16", "import-linter>=2.11", "pip-audit>=2.10",
]
build = ["pyinstaller>=6.0"]

[tool.uv.build-backend]
module-name = "ollama_llm_bench"
module-root = "src"

# [tool.ruff], [tool.mypy], [tool.importlinter], [tool.pytest.ini_options],
# [tool.coverage.*] sections follow — see the relevant standards documents.
```

`requires-python = "==3.13.*"` pins the language to Python 3.13. The `[project.scripts]` entry point names the package callable.

## 10. Local task runner

A `justfile` at the repository root provides a named recipe for every CI step, so the full CI gate can be reproduced locally. The recipes wrap `uv run` invocations:

```just
default:
    @just --list

setup:
    uv sync --frozen --all-extras --dev

lint:
    uv run ruff check src tests

format:
    uv run ruff format src tests

typecheck:
    uv run mypy --strict src

import-check:
    uv run lint-imports

test:
    uv run pytest

arch-test:
    uv run pytest tests/architecture -q

check: lint typecheck import-check arch-test
    uv run pytest tests/unit tests/integration -q
```

Local-to-CI parity is mandatory: every gate CI runs has a `just` equivalent that runs the identical command.

## 11. Banned tools and libraries

| Banned | Reason | Replacement |
|---|---|---|
| `pip`, `poetry`, `pipenv`, `pip-tools` | Superseded by a single unified manager | `uv` |
| `pyenv`, `virtualenv` | `uv` manages interpreters and environments | `uv` |
| `black`, `autopep8`, `yapf` | Superseded by one formatter | `ruff format` |
| `flake8`, `pylint`, `isort`, `pycodestyle` | Superseded by one linter | `ruff` |
| `PyQt6`, `PyQt5`, `PySide2` | Project standardizes on one current Qt binding | `PySide6` |
| QML / Qt Quick | UI is built programmatically with Qt Widgets | Hand-written `QWidget` code |
| `pydantic` on hot paths | Slower than `msgspec`; external files (imports, task YAML) are covered by safe-load parsing plus explicit per-field validation, so no pydantic-style validation layer is needed | `msgspec.Struct` |
| `dataclasses` for cross-boundary data | No immutability or validation guarantees | `msgspec.Struct(frozen, kw_only, gc=False)` |
| `tenacity` | The project uses its own cooperative `CancellationToken`-aware retry policy (`11_Services_and_Algorithms/18_RETRY_POLICY.md`) | The in-house retry wrapper |
| `stamina` | Async-oriented retry library; the backend has no event loop (D-R-01), and the spec'd retry algorithm (per-category parameters, `CancellationToken`-aware backoff) has no off-the-shelf equivalent. Removed by DD-43. | The in-house retry wrapper (`11_Services_and_Algorithms/18_RETRY_POLICY.md`) |
| `purgatory` | Asyncio-native circuit breaker; needs an event loop the application forbids (D-R-01). The spec'd breaker (dispatcher-thread-confined, per-provider, warmup-aware) is fully defined in-house. Removed by DD-43. | The in-house `backend/circuit_breaker/` (`11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`) |
| A blocking HTTP client on the GUI thread | Stalls the UI | A synchronous HTTP client (e.g. `httpx.Client`) called only on `TaskRunner` worker threads |
| Any dependency-injection container | Reflection-based wiring defeats `mypy` and the composition root | Manual wiring in `compose.py` |
| `loguru`, `picologging` | Project standardizes on structured logging over the standard library | `structlog` |
| `asyncio` / `qasync` / `anyio` | Per D-R-01 the application uses a synchronous backend + Qt `QThreadPool` `TaskRunner`; no event loop or structured-concurrency runtime is used. (Supersedes the earlier D-027/DD-37 stdlib-asyncio decision.) | Standard-library `threading` / `concurrent.futures` + Qt `QThreadPool`; cooperative `CancellationToken` (`threading.Event`); `try` / `finally` cleanup — see `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` and `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` |
| GPL / AGPL / SSPL / BSL licensed dependencies | License incompatibility | A permissively licensed alternative |
