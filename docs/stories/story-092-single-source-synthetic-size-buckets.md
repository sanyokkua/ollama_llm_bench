---
id: STORY-092
title: Expose the synthetic-size bucket table on the generator's public surface and consume it from the New Benchmark widget
status: done
spec_clauses:
  - 11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#23-size-definitions
  - 11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#4-preconditions
  - 11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#8-error-handling
  - 02_New_Benchmark_Widget/description.md#42-performance-matrix--synthetic-benchmark-only
  - 02_New_Benchmark_Widget/description.md#6-validation-rules
modules:
  - backend/performance_task_generator/
  - ui/new_benchmark/
acceptance_criteria:
  - STORY-092-AC-1
  - STORY-092-AC-2
  - STORY-092-AC-3
edge_cases: []
depends_on: []
adrs: []
owner: coder
estimate: M
---

# STORY-092 — Expose the synthetic-size bucket table on the generator's public surface and consume it from the New Benchmark widget

## Goal

Remove a real structural-debt item recorded in STORY-071: the fixed synthetic-size token targets
(64, 256, 1024, 4096, 16384) are written out twice — once inside the Performance Task Generator and
once inside the New Benchmark widget — because the UI cannot reach into another module's
`_internal/`. The two copies can silently drift, and the failure mode is not subtle: the widget
would offer the user a size the generator no longer recognizes, and picking it would abort run
creation. This story makes the generator the single source: it publishes the bucket table on its
public surface, and the widget reads the numbers from there instead of restating them.

## In scope

### The three concrete symbols

| Role                        | Symbol                                                                                                                       |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Source of truth             | `backend/performance_task_generator/_internal/size_buckets.py` → `SIZE_BUCKETS`                                              |
| Copy of the numbers         | `ui/new_benchmark/_internal/performance_matrix.py` → `_SIZE_ROWS`                                                            |
| Consumer named by STORY-071 | `ui/new_benchmark/_internal/synthetic_validation.py` → `SyntheticSizeRuleValidator` — **no change needed; see Out of scope** |

`SIZE_BUCKETS` is a `MappingProxyType[int, str]` holding
`{64: "tiny", 256: "small", 1024: "medium", 4096: "large", 16384: "xlarge"}` — note the direction:
it maps **token count → bucket label**, matching §2.3's "The numeric value in
`input_sizes`/`output_sizes` is the bucket's target token count". It is not private by name, but it
lives in `_internal/`, and `backend/performance_task_generator/api.py` currently exports only
`make_performance_task_generator` — so nothing outside the module can reach it, and `import-linter`'s
"Module internals are private" contract enforces that. That unreachability is exactly why the
duplicate exists.

`_SIZE_ROWS` is **not** a pure duplicate and must not simply be deleted. Each of its five rows is a
`(size key, bucket token target, default checked, input caption, output caption)` tuple, and four of
those five columns are UI-only data fixed by `02_New_Benchmark_Widget/description.md` §4.2: the
short keys `XS`/`SM`/`MD`/`LG`/`XL` (which deliberately differ from the generator's
`tiny`/`small`/`medium`/`large`/`xlarge` labels), the XS+SM default-checked flags, and the long
human captions such as `MD — ~250 tok · 1 page · 380 words`. Only the **second column — the token
target — is the duplicated data**, and only that column is what this story removes.

### The work

- Publishing the fixed size-bucket table on `backend/performance_task_generator/`'s public surface
  (`api.py` / `models.py`), as the single authoritative definition per §2.3. This is the story's one
  new public API symbol.
- Changing `ui/new_benchmark/_internal/performance_matrix.py` so `_SIZE_ROWS` no longer states the
  five token targets: each row takes its token target from the published table (the table's keys in
  ascending order, aligned with the five §4.2 rows), while keeping its size key, default-checked
  flag, and captions.
- Leaving the New Benchmark widget's offered input and output size sets equal, by construction, to
  the generator's published table — so the generator's §4 precondition ("every numeric value in
  `input_sizes` / `output_sizes` corresponds to a defined size bucket") holds by construction rather
  than by coincidence.

## Out of scope

- **Changing `SyntheticSizeRuleValidator`.** STORY-071's follow-up note said this class "carries an
  independent bucket copy". It does not — read it: it checks only that
  `PerformanceConfig.input_sizes` and `.output_sizes` are non-empty in `SYNTHETIC` mode and emits
  the fixed §6 hard error `"Select at least one input size and one output size."`. It holds no
  bucket numbers, so single-sourcing the table requires no edit to it. It is named in this story
  purely so the next reader does not re-open the question.
- **Adding a widget-side "this size is not a known bucket" hard error.** The generator raises on an
  unknown size (§8), but `02_New_Benchmark_Widget/description.md` §6 defines no user-facing message
  for that case, and inventing UI copy is not this story's call. AC-3 instead proves the situation
  cannot arise from this widget.
- **No new UI copy is needed for an unrecognised size value, and none is to be invented — this
  question is closed, not pending a product decision.** An earlier note suggested the missing
  widget-side message needed the product owner to choose wording. It does not, for two reasons that
  together make the case unreachable rather than unhandled. First, the specification already fixes
  the behaviour: `11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md` §8's error-handling
  table says "A numeric size with no matching bucket → Raise a validation error naming the offending
  value; no partial task list is returned", and §10.4 works the same case through end to end —
  `input_sizes=(999,)` makes `generate` raise a validation error naming `999`, no tasks are returned,
  and **run creation aborts**. So the outcome is specified; there is no undefined behaviour needing a
  decision. Second, once this story lands, the widget derives its offered token targets *from* the
  generator's published table, so no selection the user can make in the Performance Matrix can
  produce a size the generator does not recognise — that is precisely what AC-3 proves, bucket by
  bucket. Do not add a message, a banner, or a validation rule for a state the UI cannot reach.
- **Building a backend `RunValidator` service** that subsumes all New Benchmark validation rules —
  see Notes; there is no such module and no spec clause defining one.
- The generator's cartesian-expansion algorithm and its `PerformanceConfig` DTO — delivered by
  STORY-034; unchanged here.
- The performance-matrix controls, defaults, captions, and estimate line — delivered by STORY-071;
  this story only changes where the widget reads the token targets from.

## Spec inputs

- `11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#23-size-definitions` — the fixed
  application size-bucket table (`tiny` 64, `small` 256, `medium` 1024, `large` 4096, `xlarge`
  16384\) that both the generator and the widget must share; this is the single authoritative
  definition, and the numeric value carried in `PerformanceConfig` is the bucket's target token
  count.
- `11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#4-preconditions` — "Every numeric
  value in `input_sizes` and `output_sizes` corresponds to a defined size bucket (see §2.3)", and
  the axes contain no duplicates "(the widget offers each bucket once)". The widget is the guarantor
  of this precondition; single-sourcing the table is what makes it structurally guaranteed.
- `11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#8-error-handling` — "A numeric size
  with no matching bucket → Raise a validation error naming the offending value; no partial task
  list is returned." This is the failure the duplication risks, and the failure AC-3 proves
  unreachable. §10.4 walks the same case through: `input_sizes=(999,)` raises naming `999`, no tasks
  are returned, and run creation aborts — which is why no additional widget-side message is needed.
- `02_New_Benchmark_Widget/description.md#42-performance-matrix--synthetic-benchmark-only` — the
  five Input Size and five Output Size toggles with their exact captions, and the XS+SM
  default-checked selection. These stay in the widget; only the token targets move.
- `02_New_Benchmark_Widget/description.md#6-validation-rules` — the synthetic-mode hard error
  "Select at least one input size and one output size." that gates Start. Cited to fix the boundary:
  this rule is unchanged by this story and no second size-related message is added.

## Design constraints

- `backend/performance_task_generator/` is Qt-free; the published bucket table is plain data (a
  read-only mapping or a frozen `msgspec.Struct`), never a Qt object, and stays immutable —
  publishing it must not hand a caller something it can mutate.
- The UI reads the table only through the generator module's package root — never by importing
  `backend.performance_task_generator._internal.*`, which the `import-linter` "Module internals are
  private" contract forbids.
- The widget still holds only its `NewBenchmarkGateway` (D-R-06); the published bucket table is
  consumed as read-only module data, and no backend store or service Protocol is held directly.
- No `setStyleSheet`, no colour literal, no `asyncio` in the touched UI module.

## Acceptance criteria

### STORY-092-AC-1

Given the Performance Task Generator's public surface,
when the published size-bucket table is read,
then it maps exactly `64 → "tiny"`, `256 → "small"`, `1024 → "medium"`, `4096 → "large"`,
`16384 → "xlarge"`, and contains no other entry.

### STORY-092-AC-2

Given a fresh New Benchmark widget in Synthetic mode,
when the token targets of its Input Size toggles and of its Output Size toggles are collected,
then each of those two sets equals exactly the set of keys of the generator's published bucket
table.

### STORY-092-AC-3

For each size bucket the widget offers, a Synthetic selection of exactly that bucket on both axes
produces a `PerformanceConfig` the generator expands without raising:

| Widget toggle | Token target carried in `PerformanceConfig` | `generate()` outcome    |
| ------------- | ------------------------------------------- | ----------------------- |
| XS            | 64                                          | expands; raises nothing |
| SM            | 256                                         | expands; raises nothing |
| MD            | 1024                                        | expands; raises nothing |
| LG            | 4096                                        | expands; raises nothing |
| XL            | 16384                                       | expands; raises nothing |

## Test plan

- STORY-092-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/performance_task_generator/tests/test_size_buckets_public.py`,
  `test_public_bucket_table_is_the_canonical_mapping`.
- STORY-092-AC-2 — unit (`pytest-qt`), the **existing** colocated file
  `src/ollama_llm_bench/ui/new_benchmark/_internal/tests/test_performance_matrix.py`,
  `test_offered_sizes_equal_generator_published_table`.
- STORY-092-AC-3 — unit, table-driven `@pytest.mark.parametrize` with one case per bucket (no loop
  in the test body), `tests/integration/test_synthetic_size_bucket_round_trip.py`,
  `test_every_offered_bucket_is_accepted_by_the_generator`. It lives in `tests/integration/` rather
  than a colocated directory because it crosses the `ui/new_benchmark/` ↔
  `backend/performance_task_generator/` boundary, which a colocated module test may not do.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-092.
- [x] The widget-local copy of the token targets is gone: a grep or architecture check confirms the
  literals `64`, `256`, `1024`, `4096`, `16384` appear as size-bucket targets only in
  `backend/performance_task_generator/`, and no longer in `ui/new_benchmark/`.
- [x] `_SIZE_ROWS` still supplies the §4.2 size keys, default-checked flags, and captions unchanged
  — the Performance Matrix renders exactly as it did before.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory is unchanged.
- [x] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [x] The next candidate stories are proposed in the closing report.

## Unblocks and next steps

**Unblocks**

- **STORY-093** — the Phase-12 traceability, risk, and architecture documentation story. Flip it
  `draft` → `ready` **only once every other story it depends on is `done`**: STORY-076 through
  STORY-089, STORY-091, and STORY-114. STORY-092 is one input among many.

**What to do on completion**

Once STORY-092's acceptance-criteria tests pass:

1. For each story listed under **Unblocks**, check its remaining `depends_on` entries. Flip its
   `status` from `draft` to `ready` only if every one of them is now `done`; otherwise leave it
   `draft` and name the outstanding dependencies in the closing report.
1. Re-run `just trace` — the traceability record embeds each story's `status`, so it goes stale the
   moment a status changes — and then `just trace-check`.
1. Propose the next stories to pick up, ranked, in the closing report rather than stopping silently.
   The natural next picks are the other independently-`ready` finalization stories that also gate
   STORY-093 — STORY-084, STORY-085, and STORY-088 — since none of them depends on this one.

## Notes

- **No backend `RunValidator` module exists, and the running application ships an inert stub in its
  place.** STORY-071's follow-up spoke of a future backend `RunValidator` that would subsume the
  widget-local `SyntheticSizeRuleValidator`. Neither the module inventory
  (`14_Process_and_Traceability/01_MODULE_INVENTORY.md`) nor the service inventory
  (`11_Services_and_Algorithms/01_SERVICE_INVENTORY.md`) defines such a service or module, and no
  spec clause specifies a backend run-validation service — the New Benchmark validation rules are a
  UI concern (`02_New_Benchmark_Widget/description.md` §6) and the generator does its own
  precondition validation (§4/§8). This story therefore resolves the concrete, spec-grounded half of
  the debt (single-sourcing the bucket table) and nothing more.

- **The "unrecognised size value" question is closed — do not re-open it.** No product decision and
  no new UI copy is outstanding. §8 already specifies the outcome (raise a validation error naming
  the offending value, return no partial task list) and §10.4 confirms run creation aborts; and once
  the widget derives its token targets from the generator's published table, no user action in the
  Performance Matrix can reach that state at all. It is recorded here, and in Out of scope, so a
  later reader does not mistake the absence of a message for a gap.

- **What that means for the user today.** `src/ollama_llm_bench/_compose_shims.py` line 114 defines
  `_NoRunValidator`, whose `validate()` returns an empty tuple for every request, and `compose.py`
  line 330 wires it as the application's run validator. So the two Start-time errors the
  specification requires — `02_New_Benchmark_Widget/description.md` §13's **EC-RUN-3** ("Start with
  no reachable providers for selected models. The Run Validator raises a hard error; Start is
  disabled") and **EC-PROV-5** ("A plain API key references an unset environment variable. The Run
  Validator raises a hard error; Start is blocked") — **never appear in the running application**.
  The user can press Start with no reachable provider, or with an API key naming an environment
  variable that is not set, and the app will let the run begin and fail later instead of stopping it
  up front. `_NoRunValidator` is one of five permanent no-op stubs in that file, all disclosed in
  STORY-077's notes as "a future story's job" with no such story ever written. That work is tracked
  as item 1 of the recorded gap list until it is storied; it is deliberately **not** part of
  STORY-092.

- **The implementation landed on 2026-08-10; the story was closed on 2026-08-20.** All three
  commits are on `feature/spec-v3-implementation`: `da8854b` published `SIZE_BUCKETS` on the
  generator's public surface, `2b407e3` derived the Performance Matrix token targets from it, and
  `5ec8aa8` added the AC-1/AC-2/AC-3 tests plus the `ui/new_benchmark/` drift guard and
  regenerated the traceability record. The session then moved straight on to STORY-088,
  STORY-084, STORY-114, STORY-086 and STORY-117 without running the close, so the story sat at
  `ready` with finished work behind it. The ten-day gap between the commit dates and this `done`
  flip is that oversight and nothing else — no further implementation happened in between.
  Closing it required only the missing CHANGELOG entry for the new public symbol, an independent
  spec-conformance review, and a green `just check`.

- **Two concerns the closing conformance review raised, neither introduced by this story and
  neither a blocker — both are for the owner.** First, the spec is internally inconsistent about
  the XS…XL ↔ `tiny`…`xlarge` pairing this story's premise rests on: `02_New_Benchmark_Widget`
  §4.2's captions advertise `~5`/`~50`/`~250`/`~1500`/`~3500` tokens while §2.3's targets for the
  same five buckets are 64/256/1024/4096/16384, and neither document states that §4.2's XS row
  *is* §2.3's `tiny` row. Ascending-order alignment is the only sensible reading and is what the
  code encodes, but it is an inference. This is pre-existing from STORY-071, and this story
  forbids touching the captions, so it is recorded rather than resolved. Second, importing the
  generator's package root puts a concrete `backend/*` implementation into the UI's import graph,
  which `16_Engineering_Standards/01_PROJECT_STRUCTURE.md`'s folder table does not list among the
  `backend/` packages `ui/*` may import — no `import-linter` contract catches it, and there is
  precedent (`ui/new_benchmark/_internal/view.py` imports `backend.mode_visibility`), but the
  tension is structural and cannot be fixed by relocating the constant.
