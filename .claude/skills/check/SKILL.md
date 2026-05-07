---
name: check
description: Run the full quality pipeline — ruff lint, ruff format check, mypy, pytest — in the correct sequential order. Stops at first failure to avoid cascading noise.
allowed-tools: Bash
---

Run the quality pipeline in strict sequential order. Each stage must pass before the next starts. Pass an optional path argument (defaults to `src/ tests/`).

## Execution Order

```bash
# 1. Lint (fastest — catches syntax errors before type checkers waste time)
uv run ruff check --output-format=concise ${ARGUMENTS:-src/ tests/}

# 2. Format compliance
uv run ruff format --check ${ARGUMENTS:-src/ tests/}

# 3. Type check (mypy strict)
uv run mypy src/

# 4. Tests — only run if all type checks pass
uv run pytest -q --tb=short --no-header
```

## Reporting Rules

- On **all pass**: report one summary line only — "lint, format, types, tests — [N] passed in [X]s"
- On **any failure**: stop immediately, show only the failing stage output, do not run subsequent stages
- Never show passing stage output — it's noise
- For a specific path: `check src/ollama_llm_bench/services/ollama_llm_api.py`

## Why This Order

Ruff catches syntax errors in seconds before Mypy wastes time on unparseable files. Run tests last so type errors don't obscure test failures.
