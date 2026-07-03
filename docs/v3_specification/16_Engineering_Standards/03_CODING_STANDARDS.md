# Coding Standards

**Status:** Draft
**Owner:** architect
**Audience:** architect, coder
**Last Updated:** 2026-06-06
**Cross-references:** `16_Engineering_Standards/01_PROJECT_STRUCTURE.md`, `16_Engineering_Standards/02_TOOLCHAIN.md`, `16_Engineering_Standards/07_TESTING_STANDARD.md`, `08_Cross_Cutting/08-A_architecture_principles.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`

This document fixes the Python 3.13 coding standards for every source file in Ollama LLM Bench. It covers typing discipline, the canonical form of cross-boundary data structures, interface declaration, naming, import rules, docstrings, design-by-contract usage, and the patterns that are banned outright. `mypy --strict` is the authority on typing; `ruff` enforces the lint-level rules; architecture tests enforce the contract and structure rules. Code that violates any rule here fails the pull-request gate.

---

## Table of Contents

1. Purpose and scope
2. Language and runtime
3. Typing discipline
4. Cross-boundary data structures
5. Interfaces
6. Functions and methods
7. Naming conventions
8. Imports
9. Docstrings
10. Design by contract
11. Error handling
12. Logging
13. Banned patterns

---

## 1. Purpose and scope

The standards make the codebase uniform, statically verifiable, and safe to evolve. They apply to the whole `src/ollama_llm_bench/` tree. UI-specific patterns — widget composition, signal/slot wiring, design-token usage — are layered on top of these rules and are specified in the UI sections of the specification; nothing here is overridden by the UI layer except where that layer explicitly states so.

## 2. Language and runtime

- The target is **Python 3.13**, pinned to the exact patch `3.13.3` in `.python-version`, with `requires-python = "==3.13.*"` in `pyproject.toml`.
- No language feature beyond Python 3.13 syntax is used.
- `from __future__ import ...` is not needed at Python 3.13 and must not be added.

## 3. Typing discipline

`mypy --strict` is the authority. Every function parameter, every return type, every class attribute, and every public module-level variable carries a type annotation. `Any` is used only with an inline justification comment; an unannotated public symbol is a defect.

Rules:

- **Modern built-in generics only.** Write `list[str]`, `dict[str, int]`, `tuple[int, ...]`, `str | None`. The aliases `typing.List`, `typing.Dict`, `typing.Optional`, and `typing.Union` must not be used.
- **`type` keyword for type aliases.** Write `type RunId = int`, not an assignment-style alias.
- **PEP 695 inline type parameters.** Write `def first[T](items: Sequence[T]) -> T | None: ...` and `class Box[T]: ...`. `typing.TypeVar` must not be used for new code.
- **`T | None`** is the spelling for optionality; tests for absence use `is None` and `is not None`.
- **`@override`** (PEP 698) is applied to every method that overrides a parent method.
- **`Final`** is applied to module-level constants and to any attribute that must not be rebound.
- **Parameters accept abstract collections** (`Iterable`, `Sequence`, `Mapping`) where the function does not mutate them; **return types are concrete** (`list`, `dict`, `tuple`). This keeps call sites flexible while keeping returns unambiguous.
- **Closed value domains are `StrEnum`**, per the binding catalog `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` — the member value is the string stored in the database and emitted in YAML and exports, and class identity is used at runtime (contract signatures, exhaustive `match`). Wherever a member's string is serialized, persisted, compared to raw text, or embedded in a format string, write **`.value` explicitly** — never rely on implicit `str` coercion of an enum member in an f-string or format string (the `mypy`/format-string inconsistency the old rule addressed). `Literal[...]` is reserved for tiny contract-local unions that never cross a persistence or export boundary; a plain `enum.Enum` is used for fixed named choices whose value is never serialized.

Every `# type: ignore` carries its specific error code and a justification. A bare `# type: ignore` is forbidden.

## 4. Cross-boundary data structures

**Every data structure that crosses a module boundary is a `msgspec.Struct` declared frozen, keyword-only, and garbage-collection-exempt:**

```python
import msgspec


class BenchmarkResult(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    result_id: int
    run_id: int
    provider_id: str
    model_name: str
    duration_ms: int
    status: ResultStatus
    error_message: str | None = None
```

The three flags are mandatory and each is load-bearing:

- `frozen=True` — the struct is immutable, has a structural `__eq__`, and is safe to share across threads without locking.
- `kw_only=True` — every construction site is self-documenting, and adding or reordering fields does not silently break callers.
- `gc=False` — the struct is exempt from cyclic garbage collection, which removes it from GC pause scans; this is safe because DTOs never participate in reference cycles.

Field-level constraints are expressed with `Annotated` and `msgspec.Meta`, and are validated at decode time:

```python
from typing import Annotated

RetryCount = Annotated[int, msgspec.Meta(ge=1, le=10)]
ProviderId = Annotated[str, msgspec.Meta(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]
```

Domain data is stored **fully relationally** in SQLite — no struct is persisted as an opaque JSON/blob column (`10_Domain_and_Data/01_DOMAIN_MODEL.md` principle 1), and relational schema evolution is governed by the additive-structural-steps rule (DD-53), **not** by struct-level versioning. The tagged-union forward-compatibility pattern below therefore applies **only** to any struct that is serialised to disk **as a unit** outside the relational tables (e.g. a future on-disk cache/export payload); it is not used for the SQLite domain tables (SPEC-117). When such a serialised struct exists, it uses `msgspec` tagged unions so an older record still decodes:

```python
class RunRecordV1(msgspec.Struct, tag="v1", tag_field="schema",
                  frozen=True, kw_only=True, gc=False):
    started_at: float
    status: str


class RunRecordV2(msgspec.Struct, tag="v2", tag_field="schema",
                  frozen=True, kw_only=True, gc=False):
    started_at: float
    status: str
    duration_ms: int = 0   # new field; carries a default so v1 records still decode
```

The rules for evolution: a new field must be optional with a default; the type of an existing field must never change. New writes always emit the newest tag; old records continue to decode.

`@dataclass` is permitted only for a strictly private type that lives inside a single module's `_internal/` directory and never crosses a boundary. Any data that leaves a module is a `msgspec.Struct`. `dict[str, Any]` is never used to carry structured data — a `msgspec.Struct` is declared instead.

## 5. Interfaces

`typing.Protocol` is the default mechanism for declaring an interface. Protocols give structural typing with no inheritance burden, which suits a codebase where the composition root wires concrete implementations behind abstractions.

```python
from typing import Protocol


class LLMClient(Protocol):
    def chat(self, *, prompt: str, model: str) -> ChatReply: ...        # blocking; runs on a worker thread
    def probe_health(self, *, model: str) -> HealthStatus: ...          # blocking; runs on a worker thread
```

`abc.ABC` is used only when a base class must provide shared implementation logic that subclasses inherit. `@runtime_checkable` is added to a Protocol only when an `isinstance` check is genuinely required.

Protocols are kept small and focused — two callers that need different behaviour are given two Protocols rather than one wide one. A Protocol is declared in its owning module's `protocols.py` and re-exported through `api.py`.

## 6. Functions and methods

Size and shape limits:

| Metric | Target | Hard maximum |
|---|---|---|
| Lines per function | 20 | 50 |
| Parameters | 3 | 4 |
| Cyclomatic complexity | — | 10 |
| Lines per class | 200 | 300 |
| Nesting depth | 2 | 3 |
| Inheritance depth | 1 | 2 |

A function exceeding 50 lines is split into helpers. A function needing more than four parameters groups them into a `msgspec.Struct`. **Widget-construction exemption (SPEC-109):** a programmatic Qt `_build_ui`/view-construction method may exceed 50 lines when it is a flat, branch-free sequence of widget instantiation and layout wiring (no logic to factor out) — readability is not improved by arbitrarily splitting a linear build. And a **widget/service factory** that needs many collaborators receives them as a single **dependency-bundle `msgspec.Struct`** (or its one adapter gateway, §7b of `08_Cross_Cutting/08-E_interfaces_contracts.md`) rather than a long positional parameter list, satisfying the ≤4-parameter rule by construction.

Argument discipline:

- Keyword-only (`*`) is used for every boolean flag and every optional configuration argument.
- Positional-only (`/`) is used for arguments whose names are implementation details.
- Invalid inputs are rejected at the top of the function with guard clauses (early `return` or `raise`).
- A mutable object is never used as a default argument; the default is `None` and the mutable is created inside the body.
- `@staticmethod` is used for a method that touches neither `self` nor `cls`; `@classmethod` is used only for an alternative constructor.

The application uses constructor injection throughout. Every dependency is passed to `__init__` as a keyword-only argument, typed as a Protocol:

```python
class JudgeRunner:
    def __init__(
        self,
        *,
        llm: LLMClient,
        repo: ResultsRepository,
        bus: EventBus,
        logger: structlog.BoundLogger,
    ) -> None:
        self._llm = llm
        self._repo = repo
        self._bus = bus
        self._logger = logger
```

A class never constructs its own dependencies, never receives a container or service locator, and never uses an injection decorator. Wiring happens only in `compose.py`.

## 7. Naming conventions

| Element | Convention |
|---|---|
| Variables, functions, methods | `snake_case` |
| Module-level constants | `UPPER_SNAKE_CASE` |
| Classes, type aliases, Protocols | `PascalCase` |
| Private / internal symbols | `_leading_underscore` |
| Throwaway binding | `_` |
| Type parameters | `T`, `KT`, `VT`, descriptive `ItemT` |
| Boolean names | `is_`, `has_`, `can_`, `should_`, `was_` prefix |
| Action functions | `verb_noun` — `create_run`, `validate_task` |
| Conversion methods | `to_<format>` — `to_dict`, `to_json` |

Bare generic names — `data`, `temp`, `flag`, `result`, `info`, `manager`, `handler` — are not used without a domain-qualifying prefix. A read-only computed value is a `@property` with a noun name (`elapsed_ms`, not `get_elapsed_ms()`). Double-underscore name mangling is used only to avoid a genuine mixin attribute collision.

## 8. Imports

- **Absolute imports only.** Write `from ollama_llm_bench.backend.benchmark_pipeline import start_run`. Relative imports (`from .api import ...`) are forbidden and `ruff` rejects them.
- Imports are grouped into three blocks separated by blank lines — standard library, third-party, first-party — and sorted alphabetically within each block. `ruff` enforces the ordering.
- Specific names are imported when fewer than four are used from a module; the module is imported as a namespace when more are used.
- Imports are placed at module top level. A late import inside a function body is not used — it slows startup and hides import cycles.

The per-file layout of a module file:

```python
"""Module docstring.

Implements: STORY-NNN
"""
# 1. Imports — stdlib, third-party, first-party
import sqlite3
from pathlib import Path

import msgspec
import structlog

from ollama_llm_bench.backend.errors import AppError
from ollama_llm_bench.backend.persistence.protocols import RunRepository

# 2. Module-level constants — Final, UPPER_SNAKE_CASE
_DEFAULT_TIMEOUT_S: Final[float] = 30.0

# 3. Type aliases
type RunId = int

# 4. Protocol definitions
# 5. Exception classes
# 6. Private functions
# 7. Public classes
# 8. Public functions
```

## 9. Docstrings

Every public module, class, function, method, and constant carries a Google-style docstring (PEP 257). Triple double-quotes, an imperative-mood one-line summary, and — for callables — `Args`, `Returns` (or `Yields`), and `Raises` sections.

Type information lives in annotations, not in the docstring; the `Args` section describes the *meaning* of each parameter, not its type. The `Raises` section names every exception the caller may need to handle and the condition that triggers it. Side effects are documented explicitly.

```python
def write_rows(*, rows: list[CsvRow], schema: tuple[ColumnSpec, ...]) -> CsvBytes:
    """Serialize benchmark rows to RFC 4180 CSV bytes.

    Args:
        rows: The result rows to serialize, in display order.
        schema: The column definitions; its length is the row arity.

    Returns:
        The encoded CSV payload, UTF-8 with no byte-order mark.

    Raises:
        SchemaArityError: If a row's value count does not match the schema.
    """
```

A stale docstring is corrected immediately, never left to drift. A deprecation is marked with `@deprecated` from `typing_extensions` (PEP 702), which both emits a `DeprecationWarning` at runtime and produces a `mypy` diagnostic at every call site.

## 10. Design by contract

Every public function in every module's `api.py` carries at least one `@icontract.require` (a precondition) or `@icontract.ensure` (a postcondition).

**Contracts guard programmer invariants only — never user input (SPEC-105).** An `icontract.require` may assert only caller-supplied invariants the code itself controls (a non-empty schema, a positive count, a well-formed internal argument). It must **never** validate user-, file-, or provider-supplied input: a contract violation is an unrecovered `ProgrammerError` that crashes the process (the error model, `16_Engineering_Standards/05_ERROR_HANDLING_STANDARD.md`), and user input that fails a contract would therefore crash the app instead of being handled. User/file/provider input is validated by ordinary code that returns errors-as-data (DD-44), never by a contract. Contracts stay **enabled in release builds** (a violation is a real bug that should surface cleanly, not run with `-O`); cost is bounded because they sit on `api.py` boundaries, not inner loops. An architecture test asserts no `api.py` contract references a parameter that carries user/file/provider input.

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

Rules:

- Contracts are attached to **concrete implementations**, never to Protocol definitions.
- Decorator order: `@property` is outermost when present, `@icontract.*` decorators sit underneath it, and the method definition is innermost. Where a Qt `@Slot` is also present, `@Slot` is the outermost decorator.
- A contract violation is a programmer error. `icontract.errors.ViolationError` is never caught; it is allowed to propagate and crash the process.

An architecture test walks every `api.py` and asserts that each public function carries at least one `icontract` decorator (see `07_TESTING_STANDARD.md`).

## 11. Error handling

- Only specific exception types are caught. A bare `except:` and a blanket `except Exception:` are forbidden outside a tiny, explicitly listed allowlist (the terminal error hook and any provider adapter that wraps a C-extension binding).
- Exceptions are chained: `raise NewError(...) from original`. `from None` is used only when suppression is deliberate.
- Every resource is managed with a context manager (`with`).
- Within one `except` block the code either logs the exception or re-raises it — never both.
- Programmer errors — contract violations, impossible-state assertions — are surfaced as a dedicated `ProgrammerError` type that derives from `BaseException` (not `Exception`), so it survives `except Exception:` nets and reaches the terminal hook to crash the process deterministically.

The application's full error taxonomy, retry policy, and redaction pipeline are specified in the error-handling sections of the specification; this section fixes only the universal rules.

## 12. Logging

- `print()` is not used in application code.
- Logging goes through `structlog`. Loggers are obtained at module level.
- Variable data is passed as keyword arguments — `logger.info("file_saved", path=path, size_bytes=size)`. An f-string inside a logging call is forbidden because it destroys the structured fields.
- Logging is configured exactly once, in `compose.py`, before the `QApplication` is created.

## 13. Banned patterns

| Banned pattern | Replacement |
|---|---|
| `print(...)` in application code | `structlog` logger call |
| `os.path` | `pathlib.Path` |
| `from module import *` | Explicit imports |
| `global` statement | Constructor injection |
| Relative imports | Absolute imports |
| `%`-formatting / `str.format()` | f-strings (outside logging calls) |
| f-string inside a logging call | Keyword arguments |
| `@dataclass` for cross-boundary data | `msgspec.Struct(frozen, kw_only, gc=False)` |
| `dict[str, Any]` for structured data | A declared `msgspec.Struct` |
| `pydantic` on a hot path | `msgspec.Struct` |
| Bare `except:` / `except Exception:` | A specific exception type |
| Mutable default argument | `None` default; create the mutable in the body |
| `typing.List` / `Optional` / `Union` | `list` / `T | None` |
| `typing.TypeVar` for new code | PEP 695 inline type parameters |
| Monkey-patching | Redesign with a Protocol seam |
| Service locator / dependency-injection container | Constructor injection wired in `compose.py` |
| A singleton via metaclass or `__new__` | A single instance created in `compose.py` |
| A class constructing its own dependencies | Dependencies passed to `__init__` |
| Bare `# noqa` / bare `# type: ignore` | The specific code plus a justification |
| Late import inside a function body | A module-level import |
