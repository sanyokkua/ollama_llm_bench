# Configuration Reference

All configuration lives in `pyproject.toml`, the command-line, or `.editorconfig` / `.python-version`.
There are no environment variables, no `.env` files, no separate linter configs.

## Command-Line Flags

Entry point: `src/ollama_llm_bench/main.py:main` (registered as the console script `ollama_llm_bench` in `pyproject.toml`).

| Flag | Short | Choices | Default | Purpose |
|---|---|---|---|---|
| `--log-level` | — | `debug`, `info`, `warning`, `error` | `None` (**logging disabled**) | Enables the stdlib root logger at the given level. When `None`, the root logger is set above `CRITICAL` so nothing is emitted. |
| `--dataset` | `-d` | path | bundled `ollama_llm_bench/dataset` | Directory of YAML benchmark tasks. See [dataset-format.md](dataset-format.md). |

### Examples

```bash
# Normal launch — no logs, bundled dataset
uv run ollama_llm_bench

# With info-level logs to stdout
uv run ollama_llm_bench --log-level info

# With a custom dataset folder
uv run ollama_llm_bench -d /path/to/tasks

# Both flags together
uv run ollama_llm_bench --log-level debug -d /path/to/tasks
```

## Project Metadata (`pyproject.toml`)

### `[project]`

```toml
[project]
name = "ollama_llm_bench"
version = "0.1.1"
description = "Ollama benchmark"
authors = [{ name = "Oleksandr Kostenko", email = "sanyokkua@gmail.com" }]
license = { text = "MIT" }
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "pyqt6>=6.9.1,<7.0.0",
    "ollama>=0.5.1,<0.6.0",
    "pyyaml>=6.0.2,<7.0.0",
]
```

### `[project.scripts]`

```toml
ollama_llm_bench = "ollama_llm_bench.main:main"
```

Running `uv run ollama_llm_bench` invokes `main()` in `src/ollama_llm_bench/main.py`.

### Build System

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ollama_llm_bench"]

[tool.hatch.build.targets.wheel.force-include]
"src/ollama_llm_bench/dataset" = "ollama_llm_bench/dataset"
```

The `force-include` rule is critical: without it, the bundled YAML dataset would not be packaged into wheels.

### Development Dependencies

```toml
[dependency-groups]
dev = [
    "pytest>=8.4.1",
    "pytest-mock>=3.12",
    "pytest-cov>=4.0",
    "ruff>=0.9.0",
    "mypy>=1.14.0",
    "pyright>=1.1.403",
]
```

Install via `uv sync` (includes dev by default) or `uv sync --no-dev` to skip.

## UV Commands

The project uses **UV** as the sole package manager.
`uv.lock` is committed and must stay in sync with `pyproject.toml`.

| Command | Purpose |
|---|---|
| `uv sync` | Install all deps (incl. dev) into `.venv` from `uv.lock` |
| `uv sync --frozen` | Fail if `uv.lock` is stale — use in CI |
| `uv sync --no-dev` | Install only runtime deps |
| `uv run ollama_llm_bench` | Launch the app with the project's Python and venv |
| `uv run pytest` | Run tests |
| `uv run ruff check src/ tests/` | Lint |
| `uv run ruff format --check src/ tests/` | Check formatting |
| `uv run mypy src/` | Type-check (CI-authoritative) |
| `uv run pyright src/` | Type-check (IDE auxiliary) |
| `uv add <pkg>` | Add a runtime dependency |
| `uv add --dev <pkg>` | Add a dev dependency |
| `uv remove <pkg>` | Remove a dependency |
| `uv lock --upgrade` | Refresh `uv.lock` to newest compatible versions |

**Never use `pip install`** — it bypasses `uv.lock`.
**Never edit `uv.lock` by hand.**

## Ruff Configuration

### Lint (`[tool.ruff.lint]`)

```toml
[tool.ruff]
target-version = "py313"
line-length = 120
output-format = "concise"
exclude = [".venv", "__pycache__", ".mypy_cache", ".ruff_cache", "dist", "build"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "S", "SIM", "A", "C4", "RUF"]
ignore = ["E501"]

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]
"tests/*" = ["S101"]

[tool.ruff.lint.isort]
known-first-party = ["ollama_llm_bench"]
```

Rule set summary:

| Code | Rule family |
|---|---|
| `E` | pycodestyle errors |
| `F` | Pyflakes |
| `I` | isort (import sorting) |
| `B` | flake8-bugbear |
| `UP` | pyupgrade (modern syntax) |
| `S` | bandit security |
| `SIM` | flake8-simplify |
| `A` | flake8-builtins |
| `C4` | flake8-comprehensions |
| `RUF` | Ruff-specific |

`E501` (line too long) is ignored because the formatter already enforces width.
`F401` is allowed inside `__init__.py` for explicit re-exports.
`S101` (assert used) is allowed inside `tests/*` for pytest.

### Format (`[tool.ruff.format]`)

```toml
[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

Use the **two-step** execution order required by the formatting rule:

```bash
uv run ruff check --fix src/ tests/
uv run ruff format src/ tests/
```

CI (and `scripts/ai-check.sh`) use the read-only variant:

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

## Mypy Configuration (Authoritative Type Checker)

```toml
[tool.mypy]
python_version = "3.13"
strict = true
ignore_missing_imports = true
warn_unused_ignores = true
warn_redundant_casts = true
show_error_codes = true
show_column_numbers = true
no_error_summary = true
pretty = false
concise_errors = true
incremental = true
cache_dir = ".mypy_cache"
```

When mypy and pyright disagree, **mypy is authoritative** per the linting rule.

## Pyright Configuration

No `[tool.pyright]` section exists — the project uses Pyright defaults.
Pyright is treated as an IDE-only type checker.
CI / `scripts/ai-check.sh` still runs `pyright src/` to catch issues before mypy.

## Pytest Configuration

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = [
    "-q", "--tb=short", "--no-header",
    "-p", "no:warnings",
    "--import-mode=importlib",
    "--strict-markers", "--strict-config",
]
log_cli = false
log_level = "WARNING"
log_cli_level = "WARNING"
filterwarnings = [
    "ignore::DeprecationWarning",
    "ignore::PendingDeprecationWarning",
    "ignore::ResourceWarning",
]
markers = [
    "unit: Unit tests (fast, isolated)",
    "integration: Integration tests (require real resources)",
    "slow: Tests exceeding standard time budget",
]
```

> `tests/` does not exist yet.
> `uv run pytest` currently collects zero tests.
> See [testing-guide.md](testing-guide.md) for the intended structure.

## Coverage Configuration

```toml
[tool.coverage.run]
source = ["src"]
branch = true
omit = ["*/tests/*", "*/__init__.py"]

[tool.coverage.report]
fail_under = 80
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "@abstractmethod",
]
```

The **80 %** branch-coverage threshold is aspirational — current coverage is 0 %.

## Python Version

- **Runtime requirement**: `>=3.13` (`[project].requires-python`).
- **Pinned version**: `.python-version` file contains `3.13`.
- `uv python pin 3.13` keeps the two in sync.

## EditorConfig

`.editorconfig` (repository root):

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 4

[*.{yaml,yml,json,toml}]
indent_size = 2

[*.md]
trim_trailing_whitespace = false
```

## Quality Gate Script

`scripts/ai-check.sh` runs the full quality pipeline in **mandatory** order:

1. `uv run ruff check` — lint
2. `uv run ruff format --check` — format check
3. `uv run pyright` — type check (auxiliary)
4. `uv run mypy` — type check (authoritative)
5. `uv run pytest` — tests

It **stops at the first failure** to keep the output focused.
A parallel variant `scripts/ai-check-parallel.sh` also exists (not read by this documentation review).

## Logging Configuration

Logging is configured in `src/ollama_llm_bench/main.py:configure_logger`:

| Level flag | Effect |
|---|---|
| *(none)* | Root logger level set to `CRITICAL + 1` — nothing is emitted. |
| `--log-level debug` | `logging.DEBUG` + `"Debug logging is enabled"` note |
| `--log-level info` | `logging.INFO` + `"Logger configured successfully"` note |
| `--log-level warning` | `logging.WARNING` |
| `--log-level error` (or anything else) | `logging.ERROR` |

Format: `'%(asctime)s [%(levelname)-8s] %(name)s: %(message)s'`, date format `'%Y-%m-%d %H:%M:%S'`.
Handler: `StreamHandler(sys.stdout)`.

The project currently uses only the stdlib `logging` module via `logger = logging.getLogger(__name__)` at module level.
`structlog` is described as a target in the logging rule but is **not** in use — see [technical-debt.md](technical-debt.md).

## Runtime Paths

| What | Where |
|---|---|
| Application root | `Path.cwd()` at process start |
| SQLite database | `<app_root>/db.sqlite` (constant `_DB_FILE_NAME` in `app_context.py`) |
| Default dataset | `<app_root>/dataset` if `--dataset` not given and packaged resource unavailable (see `get_dataset_path`) |
| Exported summary CSV | `<app_root>/summary.csv` (`TableSerializer`) |
| Exported summary Markdown | `<app_root>/summary.md` |
| Exported details CSV | `<app_root>/details.csv` |
| Exported details Markdown | `<app_root>/details.md` |

The working directory at launch matters: all of the above are relative to it.
Running `uv run ollama_llm_bench` from `~` will create `~/db.sqlite`.

## Related Documents

- [architecture.md](architecture.md) — how these paths get wired into `ApplicationContext`
- [developer-guide.md](developer-guide.md) — adding new CLI flags or config
- [testing-guide.md](testing-guide.md) — the test runner configuration
- [technical-debt.md](technical-debt.md) — logging and config drift vs CLAUDE.md
