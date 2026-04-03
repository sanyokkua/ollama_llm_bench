---
description: "UV project standards — sole package manager, pyproject.toml, uv.lock, dependency management, CI integration"
globs: "pyproject.toml,uv.lock,.python-version"
alwaysApply: false
---

# Python UV Project Standards

> **Migration note**: The project currently uses Poetry with `poetry-core` build backend. Target state is UV with `hatchling`. Migration should be done in a dedicated PR.

## Critical Rules

- MUST use `uv` as the sole package manager — MUST NOT use `pip`, `poetry`, `pipenv`, or `pip-tools`
- MUST use `pyproject.toml` as single source of truth — MUST NOT create `setup.py`, `setup.cfg`, or `requirements.txt`
- MUST commit `uv.lock` — MUST NOT add to `.gitignore` or edit manually
- MUST use `uv add` / `uv remove` for all dependency changes
- MUST use `uv run` to execute project commands
- MUST use `--frozen` for all `uv sync` in CI pipelines
- MUST use `src/` layout for all packages
- MUST NOT mix UV with other package managers

## Common Commands

```bash
# Install/sync
uv sync

# Run application
uv run ollama_llm_bench

# Run with flags
uv run ollama_llm_bench --log-level info
uv run ollama_llm_bench -d /path/to/dataset

# Development
uv run pytest
uv run ruff check .
uv run ruff format .
uv run mypy .

# Dependencies
uv add <package>
uv add --dev <package>
uv remove <package>
uv lock --upgrade
```

## pyproject.toml Configuration

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ollama_llm_bench"
version = "0.1.1"
requires-python = ">=3.13"
dependencies = [
    "PySide6>=6.0",
    "ollama>=0.5.1,<0.6.0",
    "pyyaml>=6.0.2,<7.0.0",
]

[dependency-groups]
dev = ["pytest>=8.0", "ruff>=0.9.0", "mypy>=1.14.0", "pytest-mock>=3.12", "pytest-cov>=4.0"]

[project.scripts]
ollama_llm_bench = "ollama_llm_bench.main:main"
```

## Version Constraints

- MUST use loose constraints (`>=X.Y`) for library dependencies
- PREFER bounded ranges (`>=X.Y,<Z.0`) for application dependencies
- MUST NOT pin exact versions (`==X.Y.Z`) in `[project.dependencies]`
- Rely on `uv.lock` for exact reproducibility

## Dependency Groups

- MUST use `[dependency-groups]` for dev tools (pytest, ruff, mypy)
- MUST use `[project.optional-dependencies]` only for extras published to PyPI
- MUST NOT place dev-only tools in `[project.optional-dependencies]`

## Python Version

- MUST pin with `uv python pin 3.13`
- MUST commit `.python-version`
- MUST ensure `.python-version` satisfies `requires-python` in `pyproject.toml`

## CI Integration

```yaml
- uses: astral-sh/setup-uv@v4
  with:
    enable-cache: true

- name: Install dependencies
  run: uv sync --frozen

- name: Run tests
  run: uv run pytest

- name: Lint
  run: uv run ruff check . && uv run ruff format --check .

- name: Type check
  run: uv run mypy .
```

| Flag | Purpose | When |
|---|---|---|
| `--frozen` | Fail if lockfile stale | Always in CI |
| `--no-dev` | Skip dev deps | Production builds |

## Forbidden Files

MUST NOT create: `setup.py`, `setup.cfg`, `requirements.txt`, `Pipfile`, `poetry.lock`

When migrating from Poetry:
```bash
uv init --app --package ollama-llm-bench
# Transfer dependencies from pyproject.toml
uv sync
uv run pytest
# Remove poetry.lock after verification
```
