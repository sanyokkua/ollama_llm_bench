---
paths:
  - "src/**/*.py"
---

# Code Documentation

This rule is general Python documentation best practice, not drawn from one specific spec
file, except for its interplay with `icontract` which is fixed in
`docs/v3_specification/16_Engineering_Standards/03_CODING_STANDARDS.md` Section 9-10 (see also
`linting.md`). Apply it alongside `coding-style.md`.

## Google-style docstrings on every public symbol

Every public module, class, function, method, and constant carries a Google-style docstring
(PEP 257): triple double-quotes, an imperative-mood one-line summary, and — for callables —
`Args`, `Returns` (or `Yields`), and `Raises` sections.

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

- **Imperative mood**: "Serialize", "Return", "Calculate" — never third-person "Serializes",
  "Returns".
- **Do not duplicate type information already in the signature.** Type hints carry the type;
  the `Args` section describes the parameter's *meaning* and constraints, not its type.
- Document the **why** and the **public contract** — not a step-by-step narration of what the
  code literally does. Before writing a comment, exhaust this hierarchy: (1) name it clearly,
  (2) refactor for clarity, (3) comment as a last resort.
- A stale docstring is corrected immediately, in the same commit as the code change it
  documents — never left to drift.
- No commented-out code, ever.

## Raises: names error-taxonomy categories, not ad hoc exceptions

The `Raises` section of a docstring names the categories and leaf types from the application's
error taxonomy (`error-handling-standard.md`) — `TransientError`, `ProviderAuthError`,
`TaskCancelledError`, and so on — never an invented, undocumented exception name. A docstring
that says "Raises: ValueError" where the function actually raises a taxonomy leaf is wrong;
update it to name the real leaf.

```python
def fetch_model_list(self, *, provider_id: ProviderId) -> tuple[ModelName, ...]:
    """Return the model list a provider currently reports.

    Raises:
        ProviderAuthError: The provider rejected the configured credential.
        HttpTimeoutError: The request exceeded the transport time budget.
    """
```

## icontract and docstrings are both expected together

An `icontract` decorator is **not a substitute** for a docstring, and a docstring is not a
substitute for a contract — they serve different readers. A contract is a **runtime-checked
invariant** enforced on every call; a docstring is the **human-readable description** of that
same contract plus the function's broader behaviour (what it returns, what it raises, what it
means). A public `api.py` function carries both:

```python
import icontract


@icontract.require(lambda schema: len(schema) > 0, "schema must define at least one column")
@icontract.ensure(lambda result, rows: result.row_count == len(rows))
def write_rows(*, rows: list[CsvRow], schema: tuple[ColumnSpec, ...]) -> CsvBytes:
    """Serialize benchmark rows to RFC 4180 CSV bytes.

    Args:
        rows: The result rows to serialize, in display order.
        schema: The column definitions; its length is the row arity (enforced by contract).

    Returns:
        The encoded CSV payload, UTF-8 with no byte-order mark.
    """
```

The contract enforces "schema is non-empty" and "every row's arity matches the schema" at
runtime on every call; the docstring tells a human reader the same facts in prose, plus the
return shape. Neither one is dropped because the other exists.

## Module and class documentation

- Every module file opens with a module docstring stating its purpose (see
  `coding-style.md` for the full per-file layout: docstring -> imports -> constants -> type
  aliases -> Protocol definitions -> exception classes -> private functions -> public classes
  -> public functions).
- A class docstring states the class's single responsibility and documents its public
  attributes and constructor arguments **in one location only** — not duplicated between the
  class docstring and an `__init__` docstring.
- A trivial property getter, a standard dunder method behaving exactly as expected, and a
  private function under 5 lines with a self-describing name may omit a docstring. A private
  method whose logic exceeds 15 lines, contains a workaround, or is called from multiple
  internal locations should carry one.

## TODO / FIXME / HACK format

```python
# TODO(owner): Description of work [TICKET-ID]
# FIXME(owner): Description of defect [TICKET-ID]
# HACK(owner): Description of workaround [TICKET-ID]
```

A `FIXME` must never exist without a ticket reference. A `HACK` must include both a rationale
and a ticket for its removal. A marker comment whose ticket is closed is removed immediately,
not left in the codebase as dead documentation.
