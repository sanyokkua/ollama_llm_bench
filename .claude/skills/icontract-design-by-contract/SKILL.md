---
name: icontract-design-by-contract
description: Use when writing or reviewing any module's api.py public function — every public function in api.py needs at least one icontract decorator, and getting the scope of what a contract may guard wrong is a common, serious mistake.
---

# Design by Contract with icontract

Source of truth: `docs/v3_specification/16_Engineering_Standards/03_CODING_STANDARDS.md` §10 (Design by contract).

## The baseline requirement

Every public function in every module's `api.py` carries **at least one** `@icontract.require` (a precondition) or `@icontract.ensure` (a postcondition). This is a hard rule, enforced by an architecture test that walks every `api.py` and asserts at least one `icontract` decorator is present on each public function — a missing contract fails the pull-request gate, not just a style review.

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

## The single most important rule

**Contracts guard programmer invariants only — never user, file, or provider input.**

An `icontract.require` may assert only caller-supplied invariants that the *code itself* controls: a non-empty schema the caller already validated upstream, a positive count, a well-formed internal argument passed by another module in this codebase. It must **never** validate user-, file-, or provider-supplied input.

Here is exactly why this distinction is not optional style guidance: a contract violation is an **unrecovered `ProgrammerError`** — a type that derives from `BaseException` outside `Exception`, that is never caught, and that crashes the process by design (see the `error-taxonomy-and-redaction` skill for the full hierarchy). If you validate user input via `@icontract.require`, the consequence is that a user typing a malformed value, or a provider returning a slightly-off response, **crashes the entire application** instead of being handled gracefully with an inline validation message or a typed `UserError`/`PermanentError`. That is the opposite of what error handling in this codebase is supposed to do.

User/file/provider input is validated by **ordinary code that returns errors-as-data** (DD-44) — an `if`/`raise` that raises a specific `AppError` leaf (`UserError`, `PermanentError`, etc.), never a contract. An architecture test specifically asserts that no `api.py` contract references a parameter that carries user/file/provider input — so getting this wrong is not just a design smell, it is a build-breaking violation.

Contracts stay **enabled in release builds** — never run with `-O` to strip them — because a violation is a real bug that should surface cleanly as a crash, not silently disappear. The cost is bounded because contracts sit on `api.py` boundaries only, never inside inner loops.

## Worked example: correct vs. incorrect

**CORRECT** — the contract guards an internal invariant the *caller already validated upstream*, not raw external input:

```python
import icontract


@icontract.require(
    lambda result_ids: len(result_ids) > 0,
    "result_ids must be non-empty — the caller (the Retry use case) already "
    "filters to retryable rows before calling this",
)
@icontract.ensure(lambda result, result_ids: result <= len(result_ids))
def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
    """Reset the named results for retry from their failed stage (DD-66).

    Args:
        result_ids: Identifiers of rows already confirmed retryable by the
            caller; this method does not re-validate retryability.

    Returns:
        The number of rows actually reset.
    """
    return self._reset_for_retry_impl(result_ids)
```

This is correct because `result_ids` being non-empty is an invariant the *calling code in this codebase* is responsible for upholding — the Retry use case filters to retryable rows before ever calling this method. If the precondition fails, that means a bug exists *in this codebase's own call site*, not that a user typed something wrong.

**INCORRECT** — mistakenly validating user input through a contract:

```python
import icontract


# WRONG — task_id is a value the USER typed into the Task Editor. A user who
# types an empty task_id should see an inline validation error, not crash
# the whole application via an unrecovered ProgrammerError.
@icontract.require(lambda task_id: len(task_id) > 0, "task_id must not be empty")
def save_task(self, task_id: str, content: str) -> None:
    ...
```

The fix is to validate this with ordinary code that raises a recoverable, typed error instead:

```python
# RIGHT — user input is validated with ordinary error-taxonomy code,
# not a contract.
def save_task(self, task_id: str, content: str) -> None:
    if not task_id:
        raise TaskFileError("task_id must not be empty")   # a UserError leaf —
        # surfaces as INLINE_FIELD in the UI, does not crash the process
    self._save_task_impl(task_id, content)
```

## A second pair: postconditions on a backend store method

The same correct/incorrect split applies to `@icontract.ensure` postconditions. A postcondition states something the *implementation itself* guarantees about its own output — never a claim about whether external input was well-formed.

**CORRECT** — the postcondition checks an invariant this method's own implementation must uphold:

```python
@icontract.ensure(
    lambda result, configs: len(result) == len(configs) or True,  # illustrative shape
)
@icontract.require(
    lambda configs: len({c.name for c in configs}) == len(configs),
    "the caller must present an internally non-duplicate set — replace_providers "
    "does not deduplicate names itself, it only enforces the UNIQUE constraint",
)
def replace_providers(self, configs: tuple[ProviderConfig, ...]) -> None:
    """Replace the entire provider catalog atomically.

    Raises:
        PersistenceError: on a duplicate name or a storage failure.
    """
    self._replace_providers_impl(configs)
```

The precondition here still guards a programmer invariant, not user input: by the time `replace_providers` is called, the Settings dialog's Save flow or the import flow has already assembled the working set — if that assembled set contains an internal duplicate, that is a bug in the calling code (the dialog failed to pre-validate), not a malformed value a user is actively typing into a field right now. Contrast this with the *user-facing* duplicate-name check, which happens earlier, inline, in the dialog's live-validation handler as ordinary `if`/`raise` code surfaced as `INLINE_FIELD` — by the time a value reaches this `api.py` boundary, the codebase's own contract is "this set is already clean."

## Decorator placement rules

- Contracts are attached to **concrete implementations**, never to `Protocol` definitions — a Protocol carries no logic, including no contract enforcement.
- Decorator order, outermost to innermost: `@property` (when present) is outermost, `@icontract.*` decorators sit underneath it, and the method definition is innermost. Where a Qt `@Slot` is also present, `@Slot` is the outermost decorator of all.
- `icontract.errors.ViolationError` is **never** caught anywhere in the codebase. It is allowed to propagate and crash the process — catching it would defeat the entire point of using contracts to surface bugs loudly.

## A quick test you can apply to any candidate contract

Before writing `@icontract.require(lambda x: ...)`, ask: **"If this condition is false, did a user, a file, or a provider response cause that — or did a bug in this codebase's own call site cause that?"**

- If the answer is "a user/file/provider caused it" → this is **not** a contract. Write an `if`/`raise` of a typed `AppError` leaf instead.
- If the answer is "only a bug in our own code could cause this" → this **is** a legitimate contract.

## Quick checklist before committing a new `api.py` function

- [ ] At least one `@icontract.require` or `@icontract.ensure` is present.
- [ ] Every condition in a `require`/`ensure` references only values this codebase itself produces or has already validated — never a raw user-typed string, raw file content, or a raw provider response field.
- [ ] If you need to reject a value that *could* come from a user, a file, or a provider, that rejection is an ordinary `if`/`raise` of a typed `AppError` leaf, not a contract.
- [ ] The decorator sits on the concrete implementation, not on a `Protocol` method.
- [ ] No code anywhere catches `icontract.errors.ViolationError`.
