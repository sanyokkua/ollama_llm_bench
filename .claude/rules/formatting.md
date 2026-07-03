---
paths:
  - "*.py"
  - "*.md"
  - "*.toml"
  - "*.yaml"
  - "*.sql"
  - "pyproject.toml"
---

# Formatting Standards

Source of truth for the Python part: `docs/v3_specification/16_Engineering_Standards/02_TOOLCHAIN.md`.
The multi-language tooling section below is a **project convention, not spec-mandated** — it
extends the spec's Python-only formatting story to the other file types this repository
contains.

## Python — ruff (spec-mandated)

`ruff` is the sole linter and formatter, replacing `flake8`, `pylint`, `pyflakes`,
`pycodestyle`, `black`, `autopep8`, `yapf`, and `isort`.

```toml
[tool.ruff]
line-length = 100
target-version = "py313"
src = ["src", "tests"]

[tool.ruff.lint.isort]
known-first-party = ["ollama_llm_bench"]
combine-as-imports = true
force-sort-within-sections = true

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
line-ending = "lf"
docstring-code-format = true
```

**Execution order is mandatory: `ruff check --fix` first, `ruff format` second.** Reversing the
order produces incorrect results. CI runs both in read-only `--check` mode and never
auto-fixes:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
```

Every suppression carries its specific rule code and a justification —
`# noqa: F401  # re-export` — never a bare `# noqa`. `RUF100` detects stale suppressions.

## Universal file rules

- UTF-8 without BOM, `LF` line endings everywhere.
- `.editorconfig` and `.gitattributes` are committed at the repository root:
  - `.gitattributes`: `* text=auto eol=lf` plus binary markers for non-text assets.
  - `.editorconfig`: UTF-8, LF, 4-space Python, 2-space TOML/YAML.
- All Ruff configuration lives in `pyproject.toml` — never a standalone `ruff.toml` or CLI
  flags in CI.

## Multi-language formatting (project convention, not spec-mandated)

`ruff` covers Python only. This repository additionally enforces formatting on the other
languages it ships, wired through `.claude/settings.json` PostToolUse hooks and the
git-level `.pre-commit-config.yaml` — **not** through `ruff`:

| File type | Tool | Mode |
|---|---|---|
| Markdown (`*.md`) | `mdformat` | format |
| TOML (`*.toml`) | `taplo fmt` | format |
| YAML (`*.yaml`, `*.yml`) | `yamllint` | lint |
| SQL (`*.sql`, dialect `sqlite`) | `sqlfluff format` / `sqlfluff lint` | format + lint |

These tools are local-environment and pre-commit concerns layered on top of the spec's
Python-only toolchain; they do not change any Python-level rule in `coding-style.md`,
`linting.md`, or `uv-project.md`. A standalone `.sql` file (a migration script, a query
reference) is formatted with `sqlfluff format --dialect sqlite` and linted with
`sqlfluff lint --dialect sqlite` before commit.

## Pre-commit hook ordering

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: <pinned>
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  # project-convention hooks for non-Python files (mdformat, taplo, yamllint, sqlfluff)
```

The `ruff` hook always appears before `ruff-format`. Revisions are pinned, never floating.
