---
paths:
  - "*.py"
  - "pyproject.toml"
---

# Linting Standards

Source of truth: `docs/v3_specification/16_Engineering_Standards/02_TOOLCHAIN.md` and the
icontract section of `docs/v3_specification/16_Engineering_Standards/03_CODING_STANDARDS.md`.

## ruff — rule sets

```toml
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

## mypy --strict — the CI authority

`mypy` is the authoritative type checker and the gate that blocks merges. An IDE may
additionally run `pyright`, but only `mypy` decides correctness.

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

`strict = true` enables the full strict bundle, including `--no-implicit-reexport` and
`--disallow-untyped-defs`. The `tests.typing_negative.*` override exists because those files
are designed to fail type-checking — the test runner inverts their exit code (see
`testing.md`).

Every type suppression carries its specific error code and a justification —
`# type: ignore[no-untyped-call]  # third-party stub gap` — never a bare `# type: ignore`.

## import-linter and pytest-archon

`import-linter` enforces the module boundaries from `project-structure.md`. Its contracts live
in `pyproject.toml` under `[tool.importlinter]` and run with `uv run lint-imports`. The full
contract set — Qt-free backend, private internals, provider independence, sole composition
root — is specified in `project-structure.md`.

`pytest-archon` complements `import-linter` for symbol-level rules that import analysis cannot
see (no bare `except:`, no module-level mutable globals, `setStyleSheet` confined to
`ui/theme`, the MVC-family widget-module shape, the passive-View rule). These tests live in
`tests/architecture/` — see `testing.md` Section "Architecture tests".

## The icontract requirement

Every public `api.py` function carries **at least one** `@icontract.require` (precondition) or
`@icontract.ensure` (postcondition).

```python
import icontract


@icontract.require(lambda schema: len(schema) > 0, "schema must define at least one column")
@icontract.require(
    lambda rows, schema: all(len(r.values) == len(schema) for r in rows),
    "every row must match the schema arity",
)
@icontract.ensure(lambda result, rows: result.row_count == len(rows))
def write_rows(*, rows: list[CsvRow], schema: tuple[ColumnSpec, ...]) -> CsvBytes:
    """Serialize benchmark rows to RFC 4180 CSV bytes."""
    return _write_rows_impl(rows=rows, schema=schema)
```

**Contracts guard PROGRAMMER invariants only — never user input.** A contract may assert only
caller-supplied invariants the code itself controls (a non-empty schema, a positive count, a
well-formed internal argument). It must **never** validate user-, file-, or provider-supplied
input: a contract violation is an unrecovered `ProgrammerError` that crashes the process, and
user input failing a contract would crash the app instead of being handled as data (see
`error-handling-standard.md`). User/file/provider input is validated by ordinary code that
returns errors-as-data.

Rules:

- Contracts are attached to **concrete implementations**, never to Protocol definitions.
- Decorator order: `@property` is outermost when present, `@icontract.*` decorators sit
  underneath it, the method definition is innermost. Where a Qt `@Slot` is also present,
  `@Slot` is the outermost decorator.
- A contract violation is a programmer error — `icontract.errors.ViolationError` is never
  caught; it propagates and crashes the process.
- Contracts stay **enabled in release builds** — a violation is a real bug that should surface
  cleanly, not run with `-O`. Cost is bounded because contracts sit on `api.py` boundaries, not
  inner loops.
- An architecture test asserts no `api.py` contract references a parameter that carries
  user/file/provider input, and that every public `api.py` function carries at least one
  `icontract` decorator.

## Suppression discipline

Every `# noqa`/`# type: ignore` must carry a specific rule/error code, never bare. `RUF100`
(stale `# noqa` detection) and `warn_unused_ignores` (stale `# type: ignore` detection) are
both enabled, so a suppression that is no longer needed fails the gate rather than rotting
silently.
