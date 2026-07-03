# Algorithm: Mode Visibility Policy

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester, architect
**Last Updated:** 2026-06-06
**Cross-references:** `08_Cross_Cutting/08-G_feature_flags.md`, `08_Cross_Cutting/08-H_app_modes.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md`

The Mode Visibility Policy is the single data-driven table that decides which configuration sections and widgets of the New Benchmark surface are visible for each of the three `RunMode` values. It exists so that the New Benchmark widget contains **no hard-coded per-mode conditionals**: the widget asks the policy `is_visible(mode, section)` and shows or hides each section accordingly. This document defines the policy table, the lookup algorithm, and the rule for keeping the table exhaustive; it defines no implementation code.

---

## Table of Contents

1. Purpose
2. Inputs
3. Outputs
4. Preconditions
5. Postconditions
6. Algorithm
7. Configuration
8. Error handling
9. Threading and concurrency
10. Examples
11. Test cases

---

## 1. Purpose

The New Benchmark widget shows a different set of controls per run mode: `SYNTHETIC` shows an input/output size matrix; `TASKS` and `GRADED` show a task-file picker; the run-analysis toggle is shown in every mode but defaults differently per mode. Encoding this as `if mode == ...` branches scattered through the widget is brittle — a new mode or a moved control means hunting down conditionals, and the rules cannot be reviewed in one place or tested in isolation.

The Mode Visibility Policy replaces those branches with one declarative `(mode, section) → Visibility` lookup table. The widget builds every section once and then, on mode change, consults the policy for each section and applies the resulting visibility. The table is the contract; it is exhaustive over the Cartesian product of the three `RunMode` members and every defined section, so the policy is total — there is no `(mode, section)` pair for which the answer is undefined.

The policy governs **visibility and required-ness of New Benchmark sections only**. It does not govern the disabled-because-a-run-is-in-progress states (those are the run-state function matrix in `08_Cross_Cutting/08-H_app_modes.md` §2) and it does not govern the Settings dialog Evaluation toggles (those apply in every grading-capable mode and are not mode-keyed).

---

## 2. Inputs

| Input | Type | Meaning |
|---|---|---|
| `mode` | `RunMode` | The run mode currently selected on the New Benchmark widget — one of `SYNTHETIC`, `TASKS`, `GRADED`. |
| `section` | `ConfigSection` | The section or widget whose visibility is being queried. The full closed set is in §6.1. |

The policy reads nothing else. It is a pure function of `(mode, section)`; it does not read settings, the database, or readiness state. (Readiness gating — for example disabling Start for `GRADED` without an embedding model — is a separate concern handled by the New Benchmark widget against the readiness service.)

---

## 3. Outputs

The lookup returns one `Visibility` value:

| Value | Meaning for the widget |
|---|---|
| `VISIBLE` | The section is shown and the user may interact with it. |
| `VISIBLE_REQUIRED` | The section is shown and the user **must** supply a value before Start is enabled. Visually marked as required. |
| `VISIBLE_FORCED` | The section is shown but its value is forced by the mode and the user cannot change it; it is shown read-only for transparency. |
| `HIDDEN` | The section is not shown at all and contributes nothing to the Start preconditions. |

`VISIBLE`, `VISIBLE_REQUIRED`, and `VISIBLE_FORCED` are all "shown" states; `HIDDEN` is the only "not shown" state. A widget treats any of the three shown states as "build and place the section"; it treats the required/forced distinction as a decoration and a Start-precondition rule.

---

## 4. Preconditions

- `mode` is a valid `RunMode` member; `section` is a valid `ConfigSection` member.
- The widget has built every section described in §6.1 (the policy decides visibility of pre-built sections; it does not construct them).
- The policy table in §6.2 is complete over `RunMode × ConfigSection` — guaranteed by the maintenance rule in §7.

---

## 5. Postconditions

- The lookup returns exactly one `Visibility` value for every `(mode, section)` pair; the function is total.
- The lookup is pure and side-effect free: the same `(mode, section)` always yields the same `Visibility`, and the call changes no state.
- The set of sections the widget shows for a given mode equals the set of table cells for that mode whose value is not `HIDDEN`.
- The set of Start preconditions contributed by visibility equals the set of cells whose value is `VISIBLE_REQUIRED` (each such section must hold a value).

---

## 6. Algorithm

### 6.1 The section vocabulary

`ConfigSection` is a closed enumeration of every New Benchmark section the policy governs.

| `ConfigSection` member | What it is |
|---|---|
| `RUN_MODE_SELECTOR` | The three-way mode selector itself. |
| `TEST_MODELS_PICKER` | The picker for one or more `TEST`-role `(provider, model)` targets. |
| `INPUT_SIZES` | The synthetic input-size selector (`PerformanceConfig.input_sizes`). |
| `OUTPUT_SIZES` | The synthetic output-size selector (`PerformanceConfig.output_sizes`). |
| `REPEATS` | The repetition-count selector (`PerformanceConfig.repeats`). |
| `TASK_FILES` | The YAML task-file list (`RunStartRequest.task_paths`). |
| `JUDGE_MODEL_PICKER` | The picker for the single `JUDGE`-role model. |
| `EMBEDDING_MODEL_INFO` | The read-only display of the resolved embedding model (the embedding selection itself lives in Settings). |
| `RUN_ANALYSIS_TOGGLE` | The "Generate run analysis" toggle (`feature.judge_run_analysis_enabled`). |
| `ADVANCED_OPTIONS` | The advanced-options group: warm-up, reasoning effort, temperature, max output tokens, and the adaptive retry/timeout overrides. (Stream-tokens-to-log is a live `ui.*` Settings preference, not a per-run override — SPEC-116.) (Auto-pause toggles are **not** here — they are global only, configured in Settings → Benchmark Events, and are not per-run overrides.) |

### 6.2 The policy table

The policy is this table. It is exhaustive: every one of the `3 × 10 = 30` cells is defined.

| `ConfigSection` | `SYNTHETIC` | `TASKS` | `GRADED` |
|---|---|---|---|
| `RUN_MODE_SELECTOR` | `VISIBLE` | `VISIBLE` | `VISIBLE` |
| `TEST_MODELS_PICKER` | `VISIBLE_REQUIRED` | `VISIBLE_REQUIRED` | `VISIBLE_REQUIRED` |
| `INPUT_SIZES` | `VISIBLE_REQUIRED` | `HIDDEN` | `HIDDEN` |
| `OUTPUT_SIZES` | `VISIBLE_REQUIRED` | `HIDDEN` | `HIDDEN` |
| `REPEATS` | `VISIBLE_REQUIRED` | `HIDDEN` | `HIDDEN` |
| `TASK_FILES` | `HIDDEN` | `VISIBLE_REQUIRED` | `VISIBLE_REQUIRED` |
| `JUDGE_MODEL_PICKER` | `VISIBLE` | `VISIBLE` | `VISIBLE` (required at Start when the per-task judge phase or the analysis toggle is on; see notes) |
| `EMBEDDING_MODEL_INFO` | `HIDDEN` | `HIDDEN` | `VISIBLE_REQUIRED` |
| `RUN_ANALYSIS_TOGGLE` | `VISIBLE` (default OFF) | `VISIBLE` (default OFF) | `VISIBLE` (default ON) |
| `ADVANCED_OPTIONS` | `VISIBLE` | `VISIBLE` | `VISIBLE` |

**Reading the table — the rationale for each non-uniform row:**

- `INPUT_SIZES` / `OUTPUT_SIZES` / `REPEATS` are `VISIBLE_REQUIRED` only for `SYNTHETIC`, because only that mode generates synthetic tasks from the input/output size matrix (`PerformanceConfig`). The other two modes have no synthetic matrix, so these three sections are `HIDDEN`.
- `TASK_FILES` is the mirror image: `HIDDEN` for `SYNTHETIC` (it uses no task files) and `VISIBLE_REQUIRED` for `TASKS` and `GRADED`, both of which run real tasks loaded from YAML files.
- `JUDGE_MODEL_PICKER` is `VISIBLE` (user-controllable) in **every mode**. A judge model is required at Start when either (a) the per-task judge phase is enabled (only possible in `GRADED`) OR (b) the run-analysis toggle is ON (any mode). Both default ON in `GRADED`, so the picker is required by default in that mode; if the user disables both, the picker becomes optional and may be left empty. In `SYNTHETIC` and `TASKS` the per-task judge phase never applies, so the picker is required only when the user opts the run-analysis toggle on.
- `EMBEDDING_MODEL_INFO` is `HIDDEN` for `SYNTHETIC` and `TASKS` — neither mode grades, so the cosine phase never runs and no embedding model is needed — and `VISIBLE_REQUIRED` for `GRADED`, which always needs a ready embedding model.
- `RUN_ANALYSIS_TOGGLE` is `VISIBLE` (user-controllable) **in every mode**. The per-mode default of `feature.judge_run_analysis_enabled` differs only by initial state: **OFF in `SYNTHETIC` and `TASKS`, ON in `GRADED`**. The user can override the per-mode default in either direction; this is the canonical *"Optional — controlled by the 'Generate run analysis' toggle; default ON in GRADED, OFF in SYNTHETIC and TASKS."* rule (see DD-30).

This table is consistent with the per-mode visibility matrix in `08_Cross_Cutting/08-G_feature_flags.md` §11.2 and the run-mode property table in `08_Cross_Cutting/08-H_app_modes.md` §3; those documents describe the same rules in prose and are the cross-checks for any future change to this table.

### 6.3 The lookup

```
function is_visible(mode, section) -> Visibility:
    return POLICY_TABLE[section][mode]      # total: every cell defined
```

The widget applies the result like this on every mode change:

```
function apply_mode(mode):
    for section in ALL_CONFIG_SECTIONS:
        v = is_visible(mode, section)
        widget_for(section).set_shown(v != HIDDEN)
        widget_for(section).set_required_marker(v == VISIBLE_REQUIRED)
        widget_for(section).set_read_only(v == VISIBLE_FORCED)
    recompute_start_preconditions()
```

`recompute_start_preconditions` collects every section whose policy value is `VISIBLE_REQUIRED` and requires each to hold a value before the Start button is enabled. A `VISIBLE_FORCED` section never contributes a precondition — its value is supplied by the mode, not the user. A `HIDDEN` section contributes nothing.

When the mode changes, a section that becomes `HIDDEN` keeps its last-entered value in the widget's in-memory state but that value is excluded from the `RunStartRequest`: for example, switching from `SYNTHETIC` to `TASKS` hides the size selectors and the request carries `performance_config = None`; switching back restores the selectors with their previous values. The policy decides visibility; the request-assembly step reads only currently-shown sections.

---

## 7. Configuration

The Mode Visibility Policy is **not** configurable through any setting key. The policy table is a fixed in-code data structure. It is intentionally outside the `08-G` flag registry because it is structural UI layout, not user-tunable behaviour: the user cannot make `TASK_FILES` appear in `SYNTHETIC` mode, because that mode has no concept of task files.

Settings keys interact with the *contents* of policy-visible sections but never with the policy itself:

- `feature.judge_run_analysis_enabled` is the value behind `RUN_ANALYSIS_TOGGLE`; the policy decides that the toggle is **shown in every mode**, while the key holds its value. The per-mode initial default (OFF in `SYNTHETIC` and `TASKS`, ON in `GRADED`) is supplied by the New Benchmark widget when it constructs the toggle for a freshly selected mode; the policy does not encode the default.
- The `benchmark.*` and `feature.*` per-run-overridable keys are the values behind `ADVANCED_OPTIONS`; the policy shows that group in every mode.
- `benchmark.last_mode` seeds the initial `mode` the widget passes to the policy when it opens.

**Maintenance rule (keeping the table total).** When a new `RunMode` member is added, a new column must be added to the §6.2 table with a defined value in every row. When a new `ConfigSection` is added, a new row must be added with a defined value in every column. A lookup that finds a missing cell is a programmer error (see §8). The §6.2 table and the matrices in `08-G` §11.2 and `08-H` §3 must be updated together; they are three views of one rule set.

---

## 8. Error handling

| Situation | Handling |
|---|---|
| `is_visible` called with a `mode` not in `RunMode` | Cannot occur — `mode` is a `StrEnum` member supplied by the typed mode selector. If it somehow does, it is a programmer error and the policy raises a `KeyError`-class exception; it is not a recoverable runtime condition. |
| `is_visible` called with a `section` not in `ConfigSection` | Same — a programmer error; the policy raises rather than returning a default. The policy never silently invents a `HIDDEN` answer for an unknown section, because that would mask a missing-cell maintenance bug. |
| A `(mode, section)` cell is missing from the table | Caught by a startup self-check (see §9) that asserts the table covers the full `RunMode × ConfigSection` product. The application fails fast at startup rather than mid-interaction. |

The policy has no recoverable error states. Every input is enum-typed and every cell is defined; a failure here is always a build-time or maintenance defect, surfaced loudly, never swallowed.

---

## 9. Threading and concurrency

- The policy is a **pure, synchronous, immutable** lookup. The table is a module-level constant built once at import time.
- It is consulted exclusively on the Qt main thread, by the New Benchmark widget, during widget construction and on every mode-selector change. It performs no I/O and touches no shared mutable state, so it needs no locking and is safe to call from any thread, though in practice only the UI thread calls it.
- A **startup self-check** runs once at application start: it iterates the full `RunMode × ConfigSection` product and asserts every cell resolves, failing fast if a maintenance update (§7) left a gap. This check is cheap (30 lookups today) and guarantees the totality postcondition.
- Because the policy is stateless, mode switching incurs only the cost of re-querying and re-applying visibility; there is no debounce or async work.

---

## 10. Examples

### 10.1 Happy path — switching to SYNTHETIC

The user opens New Benchmark; `benchmark.last_mode` is `synthetic`, so the widget calls `apply_mode(SYNTHETIC)`:

| Section | `is_visible` result | Widget effect |
|---|---|---|
| `RUN_MODE_SELECTOR` | `VISIBLE` | shown |
| `TEST_MODELS_PICKER` | `VISIBLE_REQUIRED` | shown, required marker, contributes a precondition |
| `INPUT_SIZES` | `VISIBLE_REQUIRED` | shown, required marker, contributes a precondition |
| `OUTPUT_SIZES` | `VISIBLE_REQUIRED` | shown, required marker, contributes a precondition |
| `REPEATS` | `VISIBLE_REQUIRED` | shown, required marker, contributes a precondition |
| `TASK_FILES` | `HIDDEN` | not shown; `task_paths` omitted from the request |
| `JUDGE_MODEL_PICKER` | `VISIBLE` | shown, optional |
| `EMBEDDING_MODEL_INFO` | `HIDDEN` | not shown |
| `RUN_ANALYSIS_TOGGLE` | `VISIBLE` | shown, user-controllable |
| `ADVANCED_OPTIONS` | `VISIBLE` | shown |

Start is enabled once the four `VISIBLE_REQUIRED` sections all hold values; the assembled `RunStartRequest` carries a `performance_config` and an empty `task_paths`.

### 10.2 Edge case — GRADED defaults the run-analysis toggle ON but the user can override

The user switches the selector to Graded Benchmark; the widget calls `apply_mode(GRADED)`. The cell `is_visible(GRADED, RUN_ANALYSIS_TOGGLE)` returns `VISIBLE`, so the widget shows the toggle as user-controllable; the toggle initialises **ON** by the mode's default. The user can disable it to skip the extra inference cost when they only care about per-task verdicts; doing so does not disable the per-task judge phase, which is governed by `eval.phase_judge_enabled`. In the same pass, `EMBEDDING_MODEL_INFO` resolves to `VISIBLE_REQUIRED`, contributing a Start precondition — Graded Benchmark cannot start without a ready embedding model. The `JUDGE_MODEL_PICKER` cell resolves to `VISIBLE`, and the Start button additionally requires a judge model when either the per-task judge phase is enabled or the run-analysis toggle is ON; both are ON by default in this mode, so the picker is required by default — but if the user disables both, the picker becomes optional. `INPUT_SIZES`, `OUTPUT_SIZES`, and `REPEATS` resolve to `HIDDEN` and are removed; their previously-entered values are kept in widget memory but excluded from the `RunStartRequest`.

### 10.3 Edge case — switching away and back preserves nothing in the request

The user is in `SYNTHETIC` with sizes entered, switches to `TASKS` (sizes become `HIDDEN`), then switches back. The size selectors reappear with their previous values intact because the widget kept them in memory; but had the user pressed Start while in `TASKS`, the `RunStartRequest` would have carried `performance_config = None` and the task-file list — the policy ensures the request only ever reflects the sections currently shown for the active mode.

---

## 11. Test cases

| # | Scenario | Setup | Expected |
|---|---|---|---|
| T-1 | Table is total | iterate `RunMode × ConfigSection` | every `(mode, section)` resolves to a `Visibility`; no gap. |
| T-2 | Size sections shown only for performance | `is_visible(m, INPUT_SIZES)` for each mode | `VISIBLE_REQUIRED` for `SYNTHETIC`; `HIDDEN` for `TASKS` and `GRADED`. |
| T-3 | Task files hidden for performance | `is_visible(m, TASK_FILES)` for each mode | `HIDDEN` for `SYNTHETIC`; `VISIBLE_REQUIRED` for `TASKS` and `GRADED`. |
| T-4 | Judge picker visible in every mode | `is_visible(m, JUDGE_MODEL_PICKER)` | `VISIBLE` for all three modes. Required at Start when either the per-task judge phase or the run-analysis toggle is ON. |
| T-5 | Embedding info required only for full grading | `is_visible(m, EMBEDDING_MODEL_INFO)` | `HIDDEN`, `HIDDEN`, `VISIBLE_REQUIRED` respectively. |
| T-6 | Run-analysis toggle visible in every mode | `is_visible(m, RUN_ANALYSIS_TOGGLE)` | `VISIBLE` for all three modes. The per-mode default of `feature.judge_run_analysis_enabled` is OFF in `SYNTHETIC` and `TASKS`, ON in `GRADED`; user-overridable in any mode. |
| T-7 | Test models picker required in every mode | `is_visible(m, TEST_MODELS_PICKER)` | `VISIBLE_REQUIRED` for all three modes. |
| T-8 | Advanced options shown in every mode | `is_visible(m, ADVANCED_OPTIONS)` | `VISIBLE` for all three modes. |
| T-9 | Lookup is pure | call `is_visible` twice for the same pair | identical result; no state change. |
| T-10 | Start preconditions match required cells | `apply_mode(m)` then read preconditions | the precondition set equals the set of `VISIBLE_REQUIRED` sections for `m`. |
| T-11 | Run-analysis toggle contributes no fixed precondition | `apply_mode(GRADED)` | `RUN_ANALYSIS_TOGGLE` is user-controllable; it adds no Start precondition by visibility alone. (The judge picker's required-ness derives from the toggle state plus the per-task judge phase, not from the policy table.) |
| T-12 | Hidden section excluded from the request | switch synthetic → tasks, assemble request | request carries `performance_config = None`. |
| T-13 | Startup self-check fails on a missing cell | remove a cell, run the self-check | startup fails fast with a clear missing-cell message. |
| T-14 | Unknown section raises | `is_visible(mode, <not a ConfigSection>)` | raises; does not return a default. |
| T-15 | Consistency with 08-G §11.2 | compare table to the `08-G` matrix | every shown/hidden cell agrees with the feature-flag visibility matrix. |
