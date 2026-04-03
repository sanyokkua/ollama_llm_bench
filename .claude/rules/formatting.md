---
description: "Python formatting standards — Ruff formatter, editorconfig, gitattributes, pre-commit hooks, import sorting"
globs: "*.py,pyproject.toml,.editorconfig,.pre-commit-config.yaml"
alwaysApply: false
---

# Python Formatting Standards

## Critical Rules

- MUST use **Ruff** as the single Python formatter and import sorter — MUST NOT use Black, autopep8, yapf, or standalone isort
- MUST always run `ruff check --fix .` **before** `ruff format .` — reversing order is incorrect
- All Ruff configuration MUST reside in `pyproject.toml` — MUST NOT use `ruff.toml` or CLI flags
- Every project MUST explicitly set `line-length` and `target-version` in `[tool.ruff]`
- CI MUST run `ruff check .` and `ruff format --check .` in read-only mode — MUST NOT auto-fix in CI
- Every repository MUST contain `.editorconfig` and `.gitattributes` at root
- All text files MUST use UTF-8 without BOM and `LF` line endings

## Two-Step Execution

```bash
ruff check --fix .
ruff format .
```

Running only one command or reversing order produces incorrect results.

CI read-only mode:
```bash
uv run ruff check .
uv run ruff format --check .
```

## Reference Configuration

```toml
[tool.ruff]
line-length = 120
target-version = "py313"
exclude = [".git", ".venv", "__pycache__", "build", "dist", ".mypy_cache", ".pytest_cache"]

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "UP", "N"]
ignore = ["E501"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
line-ending = "lf"
skip-magic-trailing-comma = false
docstring-code-format = true
docstring-code-line-length = "dynamic"

[tool.ruff.lint.isort]
known-first-party = ["ollama_llm_bench"]
combine-as-imports = true
force-sort-within-sections = true
```

## Import Sorting

Three groups separated by blank lines:
1. Standard library
2. Third-party packages
3. First-party (project) modules

MUST set `known-first-party = ["ollama_llm_bench"]` in isort config.

## EditorConfig

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 4

[*.py]
indent_size = 4

[*.{json,yaml,yml,toml}]
indent_size = 2

[*.md]
trim_trailing_whitespace = false

[Makefile]
indent_style = tab
```

## .gitattributes

```gitattributes
* text=auto eol=lf
*.png binary
*.jpg binary
*.ico binary
```

## Pre-commit Hooks

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

The `ruff` hook MUST appear before `ruff-format`. Pin revision to specific version.

## Format Suppression

- Use `# fmt: off` / `# fmt: on` blocks or `# fmt: skip` on single statements
- Legitimate uses: matrix/table alignment, ASCII art, DSL constructs
- If > 2% of file is suppressed, reconsider the approach
