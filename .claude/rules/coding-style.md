---
description: "Python coding style rules — type hints, naming, functions, classes, error handling, SOLID, DI, complexity limits"
globs: "src/**/*.py"
alwaysApply: false
---

# Python Coding Style

## Critical Rules

- MUST add type hints to every function parameter, return type, class attribute, and public module-level variable
- MUST use modern built-in generic syntax: `list[str]`, `dict[str, int]`, `str | None` — MUST NOT use `typing.List`, `typing.Dict`, `typing.Optional`, `typing.Union`
- MUST use `@dataclass(slots=True, frozen=True, kw_only=True)` for internal data structures and `pydantic.BaseModel` for external/untrusted data
- MUST catch only specific exception types — MUST NOT use bare `except:` or `except Exception: pass`
- MUST chain exceptions with `raise NewError(...) from original` — use `from None` when deliberately suppressing
- MUST keep functions under 50 lines (target under 20) — extract helpers when exceeding
- MUST limit function parameters to maximum 4 — group related parameters into a dataclass or `TypedDict`
- MUST limit indentation depth to maximum 3 levels (target 2)
- MUST NOT use `global`, `from module import *`, `os.path`, or `print()` in production code
- MUST use `pathlib.Path` for all filesystem operations
- MUST use the `logging` module for all production output
- MUST use `f-strings` for all string interpolation — MUST NOT use `%` formatting or `.format()`
- MUST use context managers (`with` statement) for all resource management

## Interface Patterns: Protocol vs ABC

> **Migration note**: Existing code uses ABC exclusively (`core/interfaces.py`). New code should prefer Protocol.

- MUST use `Protocol` as the default interface mechanism for **new** interfaces
- MUST use `ABC` only when shared implementation logic must be provided by the base class
- MUST NOT refactor existing ABC interfaces to Protocol without a migration plan
- When modifying existing ABC-based code, follow the existing ABC pattern for consistency
- PREFER adding `@runtime_checkable` to a Protocol only when `isinstance()` checks are genuinely needed

## Naming Conventions

| Element | Convention |
|---|---|
| Variables, functions, methods | `snake_case` |
| Module-level constants | `UPPER_SNAKE_CASE` |
| Classes, type aliases | `PascalCase` |
| Private/internal | `_single_underscore` prefix |
| Throwaway variables | `_` |
| Generic type parameters | `T`, `KT`, `VT`, `ItemT` |
| Boolean vars/functions | `is_`, `has_`, `can_`, `should_`, `was_` prefix |
| Action functions | `verb_noun` pattern: `create_user()`, `validate_email()` |
| Conversion methods | `to_<format>`: `to_dict()`, `to_json()` |

- MUST NOT use bare `data`, `temp`, `flag`, `result`, `info`, `manager`, `handler` without domain-qualifying prefix
- MUST use `@property` with noun name for attribute access — MUST NOT use `get_`/`set_` prefixed methods
- MUST NOT use double underscore name mangling except for mixin name collision avoidance

## File Organization & Imports

- MUST organize imports: standard library → third-party → local, separated by blank lines, alphabetically sorted within groups
- MUST import specific names when using fewer than 4 items from a module
- **Absolute imports only** from the root package (project convention) — MUST NOT use relative imports
- MUST organize file contents in order: module docstring → imports → constants → type aliases → Protocol/ABC definitions → exception classes → private functions → public classes → public functions

## Type System

- MUST use `type` keyword for type aliases: `type UserId = int | str`
- MUST use inline type parameter syntax: `def first[T](items: list[T]) -> T | None:`
- MUST NOT use `TypeVar` for new code
- PREFER accepting abstract collection types in parameters (`Iterable[T]`, `Sequence[T]`, `Mapping[K, V]`)
- MUST return concrete types (`list[T]`, `dict[K, V]`)
- MUST test for `None` using `is None` / `is not None`
- MUST use `enum.Enum` (or `StrEnum`/`IntEnum`) for fixed named sets of choices
- PREFER `@override` (3.12+) on all methods that override a parent class method

## Function & Method Design

- MUST use positional-only (`/`) for args whose names are implementation details
- MUST use keyword-only (`*`) for all boolean flags and optional config arguments
- MUST handle invalid inputs at the top via early `return` or `raise` (guard clauses)
- MUST NOT use mutable objects as default argument values — use `None` and create inside body
- MUST use `@staticmethod` for methods that don't access `self` or `cls`
- MUST use `@classmethod` only for alternative constructors

## Class Design

- MUST use `frozen=True` on dataclasses by default — mutable requires code comment justification
- MUST use `slots=True` on all dataclasses
- MUST use `kw_only=True` on dataclasses with more than 2 fields
- MUST prefer composition over inheritance — limit inheritance depth to maximum 2 levels
- MUST prefix all internal attributes/methods with `_` — promote to public only when external access is genuinely needed

## Error Handling

- MUST catch specific exception types — MUST NOT use bare `except:`
- MUST chain exceptions: `raise NewError(...) from original_exception`
- PREFER raising exceptions for errors rather than returning `None` or `False`
- MUST use context managers for all resource management

## SOLID Principles

- **SRP**: Every class/function has exactly one reason to change
- **OCP**: Extend via new classes/functions, not modifying existing tested code
- **LSP**: Subtypes MUST be substitutable — MUST NOT strengthen preconditions or weaken postconditions
- **ISP**: Keep Protocol definitions small and focused
- **DIP**: High-level modules depend on Protocol abstractions, never concrete implementations

## Dependency Injection

- MUST inject all dependencies via `__init__`
- MUST type dependencies as Protocol (new code) or ABC (existing code), not concrete classes
- MUST NOT instantiate dependencies inside a class
- MUST NOT pass DI container, registry, or locator into classes
- MUST wire all dependencies in a Composition Root (this project: `app_context.py`)

## Design Patterns — Pythonic

| Pattern | Implementation |
|---|---|
| Factory | Factory function with `dict` dispatch |
| Singleton | Module-level instance or `@lru_cache(maxsize=1)` |
| Strategy | `Callable` parameter (simple) or `Protocol` (complex) |
| Observer | `EventBus` with `dict[str, list[Callable]]` |
| Adapter | Wrapper class implementing target Protocol |

### Banned Patterns

- MUST NOT use Service Locator, God Classes, Singleton via metaclass/`__new__`
- MUST NOT use monkey patching, `isinstance` chains for dispatch, `dict[str, Any]` for structured data

## Complexity Limits

| Metric | Target | Maximum |
|---|---|---|
| Function lines | 20 | 50 |
| Function parameters | 3 | 4 |
| Cyclomatic complexity | ≤10 | 10 |
| Class lines | 200 | 300 |
| Nesting depth | 2 | 3 |
| Inheritance depth | 1 | 2 |

## Concurrency

- MUST NOT call blocking functions inside async functions
- MUST use explicit `threading.Lock` for shared mutable data
- PREFER generators for large data processing
- PREFER `@functools.lru_cache` for expensive pure computations with repeated inputs
