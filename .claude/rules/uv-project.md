---
paths:
  - "pyproject.toml"
  - "uv.lock"
---

# UV Project Standards

Source of truth: `docs/v3_specification/16_Engineering_Standards/02_TOOLCHAIN.md`. `uv` is the
sole package manager, environment manager, and Python-version manager — it replaces `pip`,
`pip-tools`, `poetry`, `pipenv`, `virtualenv`, and `pyenv`.

## Build backend — uv_build (NOT hatchling)

**The build backend is `uv_build`** — the native build backend shipped with `uv`. This is a
common mistake to get wrong: do not default to `hatchling` or `setuptools`. `uv_build` is
selected because the application is a packaged desktop program with no PyPI publication step —
it is the lightest backend that produces a correct wheel from the `src/` layout, and it keeps
the build toolchain inside `uv` with no extra dependency.

```toml
[build-system]
requires = ["uv_build>=0.9.0,<0.10.0"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "ollama_llm_bench"
module-root = "src"
```

The wheel is built from `src/ollama_llm_bench/`. PyInstaller consumes the installed package to
produce the per-OS desktop binaries; the colocated `tests/` directories are excluded at
PyInstaller time.

## Python version — pinned to the exact patch

- `.python-version` contains a single line: `3.13.3` (the exact patch, not `3.13`).
- `pyproject.toml` declares `requires-python = "==3.13.*"`.
- `uv` reads `.python-version` to provision the interpreter.

## Rules

- Dependencies are added with `uv add` and `uv add --dev`, **never** `pip install`.
- Code is executed with `uv run`, never a bare `python`.
- `uv.lock` is committed to version control — never hand-edited, never `.gitignore`d.
- CI runs `uv sync --frozen`, which fails if `uv.lock` is stale relative to `pyproject.toml`.
  Production builds run `uv sync --frozen --no-dev`.

## Common commands

```bash
uv sync                                # Install dependencies, respecting uv.lock
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

## pyproject.toml skeleton

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
# [tool.coverage.*] sections follow — see linting.md and testing.md.
```

The full dependency-version table and policy live in `external-libraries.md`.

## The justfile — local-to-CI parity

A `justfile` at the repository root provides a named recipe for every CI step, so the full CI
gate can be reproduced locally:

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

coverage-layers:
    # per-layer branch-coverage gate — see testing.md "Coverage targets and time budgets"
    uv run coverage report --include='src/ollama_llm_bench/backend/*' --fail-under=90
    uv run coverage report --include='src/ollama_llm_bench/ui/*/_internal/controller.py,src/ollama_llm_bench/ui/*/_internal/view_model_select.py' --fail-under=85
    uv run coverage report --include='src/ollama_llm_bench/ui/*/_internal/view.py' --fail-under=60

trace:
    uv run python scripts/trace.py

trace-check:
    uv run python scripts/validate_traceability.py

check: lint typecheck import-check arch-test trace-check
    uv run pytest tests/unit tests/integration -q
```

Every gate CI runs has a `just` equivalent that runs the identical command — a green local
`just check` predicts a green CI run.

## Forbidden files

Never create: `setup.py`, `setup.cfg`, `requirements.txt`, `Pipfile`, `poetry.lock`.
