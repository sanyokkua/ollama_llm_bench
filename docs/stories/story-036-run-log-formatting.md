---
id: STORY-036
title: Format a run-log event into a verbosity-selected one-line HTML fragment
status: done
spec_clauses:
  - 11_Services_and_Algorithms/15_LOG_FORMATTING.md#62-field-selection-per-verbosity
  - 11_Services_and_Algorithms/15_LOG_FORMATTING.md#63-colour-mapping-by-event-kind
  - 11_Services_and_Algorithms/15_LOG_FORMATTING.md#64-escaping-and-truncation
  - 11_Services_and_Algorithms/15_LOG_FORMATTING.md#5-postconditions
  - 11_Services_and_Algorithms/15_LOG_FORMATTING.md#9-error-handling
  - 11_Services_and_Algorithms/15_LOG_FORMATTING.md#12-test-cases
  - 10_Domain_and_Data/02_DTOS_AND_ENUMS.md#77-runlogevent
modules:
  - backend/log_formatting/
  - backend/domain/
acceptance_criteria:
  - STORY-036-AC-1
  - STORY-036-AC-2
  - STORY-036-AC-3
  - STORY-036-AC-4
  - STORY-036-AC-5
depends_on:
  - STORY-001
  - STORY-003
owner: coder
estimate: M
---

# STORY-036 — Format a run-log event into a verbosity-selected one-line HTML fragment

## Goal

Give the Progress widget's live event log its formatter: a pure, Qt-free `LogFormatter` that
turns one `RunLogEvent` into a single-line HTML fragment carrying exactly the fields the current
verbosity (Short / Normal / Verbose) selects, wraps the event-kind tag in a tone class mapped
from the event kind, HTML-escapes every user- or model-supplied value, truncates long excerpts at
Normal, and re-renders deterministically when the verbosity changes.

## In scope

- `backend/log_formatting/`: the `LogFormatter` Protocol, `make_log_formatter` factory, and a
  `backend/log_formatting/testing.py` fake.
- The per-verbosity field-selection matrix (strictly nested Short ⊆ Normal ⊆ Verbose), the
  always-present fields, and the size-only / truncated-excerpt+size / full-content+size behaviour
  for the prompt and response fields.
- The `RunLogEventKind`-to-tone mapping (info / primary / success / warning / error / muted) as a
  tone class name, never a raw colour.
- HTML escaping of every non-application value, newline-to-space normalization, and Normal-verbosity
  excerpt truncation applied after escaping so an entity is never split.

## Out of scope

- The Progress widget's event log panel, its bounded buffer, the batched high-rate delivery, and
  the verbosity dropdown that triggers a buffer re-render — owned by `ui/progress/` in a later
  phase; this service formats whatever events the widget passes it.
- Resolving a tone name to a concrete colour — owned by `ui/theme/`; this service emits the tone
  class only.
- Writing the run-log file on disk (which always records the full Verbose field set) — owned by
  `backend/log_file_writer/` (STORY-037); this service formats the on-screen line only.
- Defining the `LogFormatter` Protocol's neighbouring EventBus payload types
  (`InferenceProgressEvent`, `JudgeModelExcludedEvent`, `DriftWarning`, `DriftSeverity`,
  `DriftKind`) — those remain owned by `backend/events/` (STORY-003). `RunLogEvent`,
  `RunLogEventKind`, and `RunLogVerbosity` are added to `backend/domain/` by this story — see
  Notes.

## Spec inputs

- `11_Services_and_Algorithms/15_LOG_FORMATTING.md#62-field-selection-per-verbosity` — the exact
  Short/Normal/Verbose field matrix and the size-only vs excerpt vs full-content rule.
- `11_Services_and_Algorithms/15_LOG_FORMATTING.md#63-colour-mapping-by-event-kind` — the
  eleven-kind-to-tone mapping.
- `11_Services_and_Algorithms/15_LOG_FORMATTING.md#64-escaping-and-truncation` — the escaping
  set, the Normal-only truncation-after-escaping rule, and newline-to-space normalization.
- `11_Services_and_Algorithms/15_LOG_FORMATTING.md#5-postconditions` — single-line, balanced-tag,
  deterministic, non-mutating output.
- `11_Services_and_Algorithms/15_LOG_FORMATTING.md#9-error-handling` — the omit-absent-field,
  unrecognized-verbosity-treated-as-Normal, and unrecognized-kind-info-tone fallbacks.
- `11_Services_and_Algorithms/15_LOG_FORMATTING.md#12-test-cases` — LF-1..LF-26.

## Design constraints

- `backend/log_formatting/` is Qt-free and asyncio-free; it imports only `backend/domain` and
  `backend/events` (`01_MODULE_INVENTORY.md` §4.5). No PySide6.
- Formatting is a pure function of `(event, verbosity)` — no I/O, no shared mutable state; the
  same pair always yields a byte-identical fragment, and the input `event` is not mutated.
- The service serves the **Run Log** stream only; it is independent of the App Log and never
  writes to it. The Run Log is not redacted by this service (the SPEC-060 provider-SDK exception
  exception is applied upstream, not here).
- The service never raises to the UI: a malformed event still produces a renderable line.
- `icontract` on any `api.py` symbol guards programmer invariants only.

## Acceptance criteria

### STORY-036-AC-1

Given one `RunLogEvent` rendered at Short, Normal, and Verbose, then the selected field set is
strictly nested — every field present at Short is present at Normal, and every field at Normal is
present at Verbose — per the §6.2 matrix.

### STORY-036-AC-2

Given a prompt/response field, its rendering varies by verbosity per this table:

| Verbosity | Prompt/response field rendered as                    |
| --------- | ---------------------------------------------------- |
| Short     | character/token counts only, no text                 |
| Normal    | truncated excerpt with trailing ellipsis plus counts |
| Verbose   | full untruncated text plus counts                    |

### STORY-036-AC-3

Each `RunLogEventKind` maps its kind tag to exactly the tone class of the §6.3 table:

| Event kind                                           | Tone    |
| ---------------------------------------------------- | ------- |
| `STAGE`, `SYSTEM`, `PROVIDER_SWITCH`, `MODEL_SWITCH` | info    |
| `TASK_START`                                         | primary |
| `DONE`, `FINISHED`                                   | success |
| `JUDGE`                                              | warning |
| `RETRY`, `FAILED`                                    | error   |
| `STOPPED`                                            | muted   |

### STORY-036-AC-4

Given an event whose model response or error text contains `<`, `>`, `&`, `"`, and a newline,
when it is formatted, then all four characters are escaped to HTML entities, the newline is
replaced with a single space, and the fragment contains no newline and no block-level element.

### STORY-036-AC-5

Given an unrecognized `verbosity` value, it is treated as Normal and a line is still produced;
given an unrecognized event kind, it is rendered with the `info` tone and a generic tag; and given
a selected field absent from the event payload, that field is omitted with no empty placeholder.

## Notes

STORY-001 and STORY-003 were both marked `done` without ever defining `RunLogEvent`,
`RunLogEventKind`, or `RunLogVerbosity` (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §7.7),
despite each citing the other as the owner. This story folds in the missing addition as an
approved first implementation step, ahead of its own `log_formatting` scope:

- `RunLogVerbosity` and `RunLogEventKind` are added to `backend/domain/models.py` §4
  (Enumerations).
- `RunLogEvent` is added to `backend/domain/models.py` §7 (domain records — runtime and
  service DTOs), matching the field list of §7.7 exactly.
- `backend/domain/__init__.py`'s docstring and `__all__` are corrected to include the three
  names; the genuine EventBus-payload exclusion (`InferenceProgressEvent`,
  `JudgeModelExcludedEvent`, `DriftWarning`, `DriftSeverity`, `DriftKind`, owned by
  STORY-003) is unchanged.

**Addendum — spec-conformance review (2026-07-14).** An independent spec-conformance review
found that §6.2 of `15_LOG_FORMATTING.md` describes three distinct text rows (system prompt /
user prompt (task) / model response) while §7.7 of `02_DTOS_AND_ENUMS.md` (this story's own
DTO) only provides two text fields (`prompt_excerpt`/`response_excerpt`); the implementation
renders one collapsed `prompt` field from `prompt_excerpt`, which is the only interpretation
the DTO supports, and this is flagged for spec-owner sign-off rather than resolved by this
story.

## Test plan

- STORY-036-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/log_formatting/tests/test_field_nesting.py`,
  `test_field_set_is_strictly_nested`. Covers LF-1, LF-2, LF-3, LF-4.
- STORY-036-AC-2 — unit (table-driven over verbosities), colocated
  `src/ollama_llm_bench/backend/log_formatting/tests/test_excerpt_rendering.py`,
  `test_prompt_response_rendering_per_verbosity`,
  `test_prompt_response_rendering_with_token_counts_per_verbosity`,
  `test_prompt_response_rendering_without_token_counts_falls_back_to_char_only`. Covers LF-19,
  LF-20.
- STORY-036-AC-3 — unit (table-driven over the eleven kinds), colocated
  `src/ollama_llm_bench/backend/log_formatting/tests/test_tone_mapping.py`,
  `test_event_kind_maps_to_tone`. Covers LF-5..LF-10.
- STORY-036-AC-4 — unit, colocated
  `src/ollama_llm_bench/backend/log_formatting/tests/test_escaping.py`,
  `test_escaping_and_newline_normalization_one_line`. Covers LF-17, LF-18, LF-26.
- STORY-036-AC-5 — unit (table-driven over fallbacks), colocated
  `src/ollama_llm_bench/backend/log_formatting/tests/test_fallbacks.py`,
  `test_unrecognized_and_absent_field_fallbacks`. Covers LF-16, LF-21, LF-22, LF-23, LF-25.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-036.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/log_formatting/`.
- [x] An architecture test confirms the module imports no Qt and no `asyncio`.
- [x] The traceability record validates with no orphan clause and no orphan test for STORY-036.
- [x] The module inventory is unchanged.
