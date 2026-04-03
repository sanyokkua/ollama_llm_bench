---
name: deps
description: Manage UV dependencies — add, remove, audit the dependency tree, or restore from lockfile. Never uses pip directly.
allowed-tools: Bash
---

## Subcommands

### `add <package>`
```bash
uv add <package> -q
# Verify the import works
uv run python -c "import <package>; print('ok')"
# Confirm lockfile is consistent
uv sync --frozen --check
```

### `remove <package>`
```bash
uv remove <package> -q
# Check for remaining import errors
uv run python -c "from ollama_llm_bench import main" 2>&1
uv sync --frozen --check
```

### `audit`
```bash
uv tree
```

### `sync` (restore from lockfile)
```bash
uv sync -q
```

## Rules

- **Always** use `-q` flag to suppress UV progress bar output (UV animated bars = thousands of useless tokens)
- **Never** use `pip install` — bypasses `uv.lock` and creates environment drift
- **Always** run `uv sync --frozen --check` after add/remove to confirm lockfile consistency
- Dev-only tools go in `[dependency-groups]` in `pyproject.toml`, not `[project.dependencies]`
- **Never** pin exact versions (`==X.Y.Z`) — use `>=X.Y` or bounded `>=X.Y,<Z.0`

## Approved Runtime Dependencies

| Package | Constraint | Purpose |
|---------|-----------|---------|
| `PySide6` | `>=6.0` | Qt UI framework (migration target) |
| `ollama` | `>=0.5.1,<0.6.0` | Ollama Python client |
| `pyyaml` | `>=6.0.2,<7.0.0` | YAML benchmark task parsing |

## Approved Dev Dependencies

`pytest>=8.0`, `pytest-mock>=3.12`, `pytest-cov>=4.0`, `ruff>=0.9.0`, `mypy>=1.14.0`

## Banned

`pip install`, `PyQt6` (use PySide6), `loguru` (use structlog), `black`/`isort` (use ruff)
