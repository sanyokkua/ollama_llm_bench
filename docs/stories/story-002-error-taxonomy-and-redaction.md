---
id: STORY-002
title: Define the four-category error taxonomy and the secret-redaction module
status: done
spec_clauses:
  - 11_Services_and_Algorithms/17_ERROR_TAXONOMY.md#62-the-hierarchy
  - 11_Services_and_Algorithms/17_ERROR_TAXONOMY.md#63-leaf-catalogue
  - 11_Services_and_Algorithms/17_ERROR_TAXONOMY.md#64-mixed-inheritance-for-multi-axis-dispatch
  - 10_Domain_and_Data/08_REDACTION_PATTERNS.md#3-the-regex-denylist
  - 10_Domain_and_Data/08_REDACTION_PATTERNS.md#7-the-api-surface
  - 10_Domain_and_Data/08_REDACTION_PATTERNS.md#8-order-of-operations-inside-a-redaction-pass
edge_cases:
  - EC-RD-3
  - EC-RD-5
  - EC-RD-6
modules:
  - backend/errors/
acceptance_criteria:
  - STORY-002-AC-1
  - STORY-002-AC-2
  - STORY-002-AC-3
  - STORY-002-AC-4
  - STORY-002-AC-5
  - STORY-002-AC-6
depends_on:
  - STORY-001
owner: coder
estimate: M
---

# STORY-002 — Define the four-category error taxonomy and the secret-redaction module

## Goal

Provide the single coherent error hierarchy every module raises and catches, and the single
redaction module that scrubs secrets at the two sanctioned surfaces. This gives the
application a mechanical, class-driven answer to whether a failure is retried, surfaced to
the user, or crashes the process — and guarantees no provider credential leaks through an
error message or the application log.

## In scope

- The full class hierarchy of `17_ERROR_TAXONOMY.md` §6.2: `AppError` (under `Exception`)
  with `TransientError` / `PermanentError` / `UserError` roots, every leaf in §6.3, the
  `ProviderError` marker type, and `ProgrammerError` (under `BaseException`, outside
  `Exception`) with its `DatabaseIntegrityError` / `ContractViolationError` /
  `ValidationError` leaves.
- The `ErrorContext` carrier (redaction-safe fields: `provider_id`,
  `model_id_truncated`, `endpoint`, `http_status`, `provider_error_code`, `attempt`,
  `request_id`, `correlation_id`, and the `phase` field on `HttpTimeoutError`).
- The mixed-inheritance leaves (`ProviderAuthError(UserError, ProviderError)`, etc.) with
  the category root listed first so MRO yields the correct `category`.
- The redaction module: `redact(text)` and the `redact_for_log` structlog processor, their
  shared ordered denylist, the never-log key-name list, the length cap, and the fixed
  `<redacted>` placeholder.

## Out of scope

- The provider-adapter boundary that *applies* `redact` when wrapping SDK exceptions —
  owned by the Phase-2/3 provider modules.
- The retry filter that consults `TransientError` — owned by STORY-007.
- The error-to-UX dispatch table (`17_ERROR_TAXONOMY.md` §6.6) — a controller-layer concern
  in a later phase.
- The `structlog` two-stream configuration that installs the processor — owned by
  STORY-004.

## Spec inputs

- `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md#62-the-hierarchy` — the class tree and
  the rule that `ProgrammerError` descends from `BaseException` outside `Exception`.
- `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md#63-leaf-catalogue` — every leaf, its
  category, and its `ErrorKind` / terminal `ResultStatus` mapping.
- `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md#64-mixed-inheritance-for-multi-axis-dispatch`
  — the `ProviderError`-marked leaf set and the MRO ordering rule.
- `10_Domain_and_Data/08_REDACTION_PATTERNS.md#3-the-regex-denylist` — the ten ordered
  denylist patterns and the env-var-name exception.
- `10_Domain_and_Data/08_REDACTION_PATTERNS.md#7-the-api-surface` — the exact two-callable
  surface (`redact`, `redact_for_log`) and the never-log key-name list.
- `10_Domain_and_Data/08_REDACTION_PATTERNS.md#8-order-of-operations-inside-a-redaction-pass`
  — known-value masking, then regex substitution, then length cap.

## Design constraints

- `backend/errors/` is a pure, Qt-free module; standard library and `msgspec` only. The
  redaction functions are callable from any thread (`01_MODULE_INVENTORY.md` §4.1).
- **Ambiguity resolution — redaction ownership.** `redact` / `redact_for_log` live in
  `backend/errors/`, not `backend/infra/`: the module inventory assigns them here and the
  error taxonomy is their direct consumer. `backend/infra/`'s logging setup (STORY-004)
  installs the `redact_for_log` processor but does not define it.
- `ProgrammerError` must not be catchable by `except Exception`; a contract/domain
  invariant violation crashes the process.
- No secret-bearing value is placed on `ErrorContext`; the length cap and denylist are the
  only egress defences and `<redacted>` is a fixed, non-configurable token.

## Acceptance criteria

### STORY-002-AC-1

Every leaf error type resolves to exactly one of the four categories via its first base
class, and `issubclass(ProgrammerError, Exception)` is `False` so `except Exception` does
not catch a `ProgrammerError`.

### STORY-002-AC-2

For each leaf in the §6.3 catalogue table, its `category`, its mapped `ErrorKind`, and its
mapped terminal `ResultStatus` equal the values in that table (table-driven over every
leaf).

### STORY-002-AC-3

`ProviderAuthError` is an instance of both `UserError` and `ProviderError`, and its
`category` resolves to the `UserError` (first-listed) root — the mixed-inheritance MRO
rule holds for every `ProviderError`-marked leaf.

### STORY-002-AC-4

For each denylist pattern and the never-log key-name list, `redact` (or the processor)
replaces the secret span with `<redacted>`; and for the env-var-name exception input
`api_key=ANTHROPIC_API_KEY` the output is returned unchanged (table-driven over the
`RT-01`…`RT-18` cases).

### STORY-002-AC-5

Given text longer than 4000 characters, `redact` returns exactly 4000 characters followed
by the suffix ` …[truncated, N more characters]` where `N` is the number of characters
removed, and the cap is applied after substitution.

### STORY-002-AC-6

Given the same secret appearing multiple times in one string, `redact` replaces every
occurrence (EC-RD-3); given `None` or an empty string it returns an empty string with no
error (EC-RD-5); and a known-safe diagnostic identifier (`correlation_id`, `run_id`,
`result_id`, `task_id`, model-digest) presented as a named structured field is not redacted
by the value-shape patterns (EC-RD-6).

## Test plan

- STORY-002-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/errors/tests/test_hierarchy.py`,
  `test_programmer_error_is_outside_exception`.
- STORY-002-AC-2 — table-driven unit, same directory
  `src/ollama_llm_bench/backend/errors/tests/test_leaf_catalogue.py`,
  `test_leaf_category_kind_and_status_mapping`.
- STORY-002-AC-3 — unit, `src/ollama_llm_bench/backend/errors/tests/test_hierarchy.py`,
  `test_mixed_inheritance_mro_gives_category_root`.
- STORY-002-AC-4 — table-driven unit,
  `src/ollama_llm_bench/backend/errors/tests/test_redaction.py`,
  `test_denylist_patterns_and_env_var_exception`.
- STORY-002-AC-5 — unit, same file, `test_redact_applies_length_cap_after_substitution`.
- STORY-002-AC-6 — unit, same file, `test_redaction_edge_cases`; EC-RD-3, EC-RD-5, EC-RD-6
  covered here per `06_EDGE_CASE_TO_TEST_MAPPING.md`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-002.
- [ ] EC-RD-3, EC-RD-5, and EC-RD-6 have passing tests.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/errors/`.
- [ ] Backend branch coverage for `backend/errors/` meets the Phase 1 ≥90% gate.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
