---
paths:
  - "src/**/*.py"
---

# Coding Style

Source of truth: `docs/v3_specification/16_Engineering_Standards/03_CODING_STANDARDS.md`. `mypy --strict` is
the typing authority, `ruff` enforces lint-level rules, and architecture tests enforce the
contract/structure rules below. Violating any rule here fails the pull-request gate.

## Language and runtime

- Target is **Python 3.13**, pinned to the exact patch `3.13.3` in `.python-version`, with
  `requires-python = "==3.13.*"`.
- No language feature beyond Python 3.13 syntax. `from __future__ import ...` is not added —
  it is unnecessary at 3.13.

## Cross-boundary data structures — the msgspec rule

**Every data structure that crosses a module boundary is a `msgspec.Struct` declared frozen,
keyword-only, and garbage-collection-exempt:**

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

All three flags are mandatory and each is load-bearing:

- `frozen=True` — immutable, structural `__eq__`, safe to share across threads with no lock.
- `kw_only=True` — every construction site is self-documenting; reordering fields never
  silently breaks a caller.
- `gc=False` — exempt from cyclic garbage collection (removed from GC pause scans); safe
  because DTOs never participate in reference cycles.

Field-level constraints use `Annotated` + `msgspec.Meta`, validated at decode time:

```python
from typing import Annotated

RetryCount = Annotated[int, msgspec.Meta(ge=1, le=10)]
ProviderId = Annotated[str, msgspec.Meta(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]
```

Domain data is stored **fully relationally** in SQLite — no struct is persisted as an opaque
JSON/blob column. The tagged-union forward-compatibility pattern below applies **only** to a
struct serialised to disk as a unit outside the relational tables (e.g. a future export
payload), never to the SQLite domain tables:

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

Evolution rules: a new field must be optional with a default; an existing field's type never
changes. New writes always emit the newest tag; old records continue to decode.

**The one exception.** `@dataclass` is permitted only for a strictly private type that lives
inside a single module's `_internal/` directory and never crosses a module boundary. Any data
that leaves a module is a `msgspec.Struct`. `dict[str, Any]` is never used to carry structured
data — declare a `msgspec.Struct` instead.

## Interfaces — Protocol vs ABC

`typing.Protocol` is the **default** mechanism for declaring an interface — structural typing
with no inheritance burden, suited to a composition root that wires concrete implementations
behind abstractions:

```python
from typing import Protocol


class LLMClient(Protocol):
    def chat(self, *, prompt: str, model: str) -> ChatReply: ...        # blocking; worker thread
    def probe_health(self, *, model: str) -> HealthStatus: ...          # blocking; worker thread
```

`abc.ABC` is used **only** when a base class must provide shared implementation logic that
subclasses inherit. `@runtime_checkable` is added to a Protocol only when an `isinstance`
check is genuinely required. Protocols are kept small and focused — two callers needing
different behaviour get two Protocols, not one wide one. A Protocol is declared in its owning
module's `protocols.py` and re-exported through `api.py`.

## Modern typing — no exceptions

- **Modern built-in generics only**: `list[str]`, `dict[str, int]`, `tuple[int, ...]`,
  `str | None`. `typing.List`, `typing.Dict`, `typing.Optional`, `typing.Union` are forbidden.
- **`type` keyword for type aliases**: `type RunId = int`, never an assignment-style alias.
- **PEP 695 inline type parameters**: `def first[T](items: Sequence[T]) -> T | None: ...`,
  `class Box[T]: ...`. `typing.TypeVar` is **never** used for new code.
- **`T | None`** is the spelling for optionality; absence is tested with `is None` /
  `is not None`.
- **`@override`** (PEP 698) on every method overriding a parent method.
- **`Final`** on module-level constants and any attribute that must not be rebound.
- Parameters accept abstract collections (`Iterable`, `Sequence`, `Mapping`) where the
  function does not mutate them; **return types are concrete** (`list`, `dict`, `tuple`).
- Closed value domains are `StrEnum` — the member value is what is stored in the database and
  emitted in YAML/exports. Where a member is serialized, persisted, or embedded in a format
  string, write **`.value` explicitly** — never rely on implicit `str` coercion in an
  f-string. `Literal[...]` is reserved for tiny contract-local unions that never cross a
  persistence/export boundary.
- Every `# type: ignore` carries its specific error code and a justification. A bare
  `# type: ignore` is forbidden.

## Function/class/complexity limits

| Metric | Target | Hard maximum |
|---|---|---|
| Lines per function | 20 | 50 |
| Parameters | 3 | 4 |
| Cyclomatic complexity | — | 10 |
| Lines per class | 200 | 300 |
| Nesting depth | 2 | 3 |
| Inheritance depth | 1 | 2 |

A function exceeding 50 lines is split into helpers. A function needing more than four
parameters groups them into a `msgspec.Struct`.

**Widget-construction exemption.** A programmatic Qt `_build_ui`/view-construction method may
exceed 50 lines when it is a flat, branch-free sequence of widget instantiation and layout
wiring with no logic to factor out. A widget/service factory needing many collaborators
receives them as a single **dependency-bundle `msgspec.Struct`** (or its one adapter gateway —
see `pyside6-app-development.md`), satisfying the ≤4-parameter rule by construction.

Argument discipline:

- Keyword-only (`*`) for every boolean flag and every optional configuration argument.
- Positional-only (`/`) for arguments whose names are implementation details.
- Invalid inputs are rejected at the top with guard clauses (early `return`/`raise`).
- A mutable object is never a default argument; default is `None`, mutable created in body.
- `@staticmethod` for a method touching neither `self` nor `cls`; `@classmethod` only for an
  alternative constructor.

Constructor injection throughout. Every dependency is a keyword-only `__init__` argument,
typed as a Protocol:

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

A class never constructs its own dependencies, never receives a container or service locator,
never uses an injection decorator. Wiring happens only in `compose.py`.

## Naming conventions

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

Bare generic names — `data`, `temp`, `flag`, `result`, `info`, `manager`, `handler` — are not
used without a domain-qualifying prefix. A read-only computed value is a `@property` with a
noun name (`elapsed_ms`, not `get_elapsed_ms()`). Double-underscore name mangling is used only
to avoid a genuine mixin attribute collision.

## Design by contract (icontract)

Every public function in every module's `api.py` carries at least one `@icontract.require`
(precondition) or `@icontract.ensure` (postcondition). Contracts guard **programmer
invariants only — never user input**: a contract violation is an unrecovered `ProgrammerError`
that crashes the process. User/file/provider input is validated by ordinary code that returns
errors-as-data, never by a contract. Contracts stay enabled in release builds. The full rule
set (decorator ordering, the architecture-test enforcement) is in `linting.md` and
`error-handling-standard.md`; see those files for the complete treatment — this file states
only that the obligation exists on every `api.py` public function.

## Banned patterns

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
| `typing.List` / `Optional` / `Union` | `list` / `T \| None` |
| `typing.TypeVar` for new code | PEP 695 inline type parameters |
| Monkey-patching | Redesign with a Protocol seam |
| Service locator / dependency-injection container | Constructor injection wired in `compose.py` |
| A singleton via metaclass or `__new__` | A single instance created in `compose.py` |
| A class constructing its own dependencies | Dependencies passed to `__init__` |
| Bare `# noqa` / bare `# type: ignore` | The specific code plus a justification |
| Late import inside a function body | A module-level import |

## Imports

- **Absolute imports only**: `from ollama_llm_bench.backend.benchmark_pipeline import start_run`.
  Relative imports are forbidden and `ruff` rejects them.
- Three blocks separated by blank lines: standard library, third-party, first-party; sorted
  alphabetically within each block.
- Specific names are imported when fewer than four are used from a module; otherwise the
  module is imported as a namespace.
- Imports are placed at module top level. A late import inside a function body is not used.

Per-file layout of a module file (top to bottom): module docstring → imports (stdlib →
third-party → first-party) → module-level constants (`Final`, `UPPER_SNAKE_CASE`) → type
aliases → Protocol definitions → exception classes → private functions → public classes →
public functions. See `project-structure.md` for the package-level (`__init__.py`/`api.py`/
`models.py`/`protocols.py`/`_internal/`) public-surface rules.

## Error handling and logging (cross-reference)

The full error taxonomy and logging rules live in `error-handling-standard.md` and
`logging.md`. The universal rules restated here because they are coding-style obligations:
only specific exception types are caught (no bare `except:`/blanket `except Exception:`
outside a tiny allowlist); exceptions are chained with `raise NewError(...) from original`;
every resource uses a context manager; within one `except` block, log the exception **or**
re-raise it, never both; `ProgrammerError` derives from `BaseException`, not `Exception`.
