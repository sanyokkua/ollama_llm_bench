---
description: "Python linting standards — Ruff linter, Mypy/pyright type checking, noqa rules, import-linter, CI pipeline"
globs: "*.py,pyproject.toml,.pre-commit-config.yaml"
alwaysApply: false
---

# Python Linting Standards

> **Migration note**: The project currently uses pyright for type checking. Target state is Mypy as CI authority. Pyright may continue as IDE-only checker.

## Critical Rules

- MUST use **Ruff** (>= 0.9.0) as the sole linter — MUST NOT use Flake8, Pylint, pyflakes, or pycodestyle
- MUST use **Mypy** (>= 1.14.0) as the authoritative static type checker in CI — Pyright MAY be used in IDE only
- All configuration MUST reside in `pyproject.toml` — MUST NOT create `.flake8`, `mypy.ini`, or `.isort.cfg`
- Every `# noqa` MUST include specific rule code(s) — blanket `# noqa` is forbidden
- Every `# type: ignore` MUST include specific Mypy error code — blanket `# type: ignore` is forbidden
- MUST enable `strict = true` in `[tool.mypy]` for new projects
- CI MUST run `ruff check .`, `ruff format --check .`, and `mypy .` — all MUST block merge

## Tool Stack

| Tool | Status | Role |
|---|---|---|
| Ruff | Required | Primary linter and formatter |
| Mypy | Required | Type checker — CI authority |
| Pyright/Pylance | Acceptable | Type checker — IDE use only |
| import-linter | Recommended | Architecture layer enforcement |

## Rule Selection

### Minimum Required

`E` (pycodestyle), `F` (Pyflakes), `I` (isort), `B` (flake8-bugbear)

### Recommended for New Projects

`UP` (pyupgrade), `S` (bandit security), `SIM` (simplify), `A` (builtins), `C4` (comprehensions), `RUF` (Ruff-specific)

### Reference Configuration

```toml
[tool.ruff]
target-version = "py313"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "S", "SIM", "A", "C4", "RUF"]
ignore = ["E501"]

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]
"tests/*" = ["S101"]

[tool.mypy]
python_version = "3.13"
strict = true
ignore_missing_imports = true
warn_unused_ignores = true
warn_redundant_casts = true
```

## Error Suppression

### Inline `# noqa`

```python
# GOOD — specific code + justification
from plugins import handler  # noqa: F401  # Dynamic plugin loading

# FORBIDDEN
from plugins import handler  # noqa
```

### Type Ignore

```python
# GOOD
result = api.call()  # type: ignore[no-untyped-call]  # Untyped SDK

# FORBIDDEN
result = api.call()  # type: ignore
```

- If a file has > 3 inline `# noqa` for the same rule, MUST use `per-file-ignores` instead
- MUST enable `RUF100` to detect stale `# noqa` comments

## Architecture Enforcement

```toml
[tool.importlinter]
root_packages = ["ollama_llm_bench"]

[[tool.importlinter.contracts]]
name = "Core must not import Qt modules"
type = "forbidden"
source_modules = ["ollama_llm_bench.core"]
forbidden_modules = ["PySide6", "PyQt6"]
```

## CI Pipeline

```yaml
- name: Ruff check
  run: uv run ruff check .

- name: Ruff format check
  run: uv run ruff format --check .

- name: Mypy
  run: uv run mypy .
```

MUST NOT use `--fix` in CI. MUST NOT suppress exit codes.

## Pre-commit Hooks

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.14.0
    hooks:
      - id: mypy
```
