---
id: STORY-073
title: Add the Progress run-log judge-excluded line and run-log search-match highlighting
status: ready
spec_clauses:
  - 04_Progress_Widget/description.md#81-toolbar
  - 04_Progress_Widget/description.md#83-event-kinds
  - 04_Progress_Widget/description.md#62-model-stability-indicator
  - 04_Progress_Widget/description.md#12-event-bus-integration
  - 08_Cross_Cutting/08-I_edge_cases.md#EC-PROV-4b
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b4-progressgateway
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/progress/
  - backend/log_formatting/
acceptance_criteria:
  - STORY-073-AC-1
  - STORY-073-AC-2
  - STORY-073-AC-3
edge_cases:
  - EC-PROV-4b
depends_on:
  - STORY-058
  - STORY-060
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: M
---

# STORY-073 — Add the Progress run-log judge-excluded line and run-log search-match highlighting

## Goal

Close two deferred Progress run-log behaviours. First, when the judge model is excluded mid-run,
the exclusion is shown as a persistent red stability callout but is never written to the run event
log — so a user reading the log alone never sees it. This story appends the one-time `judge_excluded`
log line, in addition to the existing callout, so the same exclusion is surfaced both ways. Second,
the run-log search currently filters lines but does not highlight the matched text; the spec
requires both filter and highlight. This story adds case-insensitive highlighting of the matched
substring in each visible line.

## In scope

- `ui/progress/` LogController: subscribe to `_judge_model_excluded` and append exactly one
  `judge_excluded` log line rendered by the log-formatting service, in addition to the existing
  stability-callout handling.
- `ui/progress/` run-log view: highlight the matched substring of each visible line while a search
  term is active (case-insensitive), and remove all highlight marks when the search is cleared,
  preserving the existing line-filtering behaviour.
- `backend/log_formatting/`: render the `judge_excluded` event kind to the canonical text and the
  `error` tone token per the event-kind mapping.

## Out of scope

- The judge-model exclusion **stability callout** in the Model panel — delivered by the Progress
  stability sub-controller (STORY-058); this story adds the log line that accompanies it, not the
  callout.
- The run-log verbosity model, bounded buffer, auto-scroll, and the existing line-filter search
  predicate — delivered by STORY-060; this story extends the same view with highlighting.
- Emitting `_judge_model_excluded` and the exclusion decision itself — a `backend/benchmark_pipeline`
  concern, already delivered; this story only renders the event.
- The `task_judge_timeout` log line — a separate event kind already covered.
- Wiring the concrete `ProgressGateway` in `compose.py` — this story **must not touch** `compose.py`.

## Spec inputs

- `04_Progress_Widget/description.md#81-toolbar` — the Search input "filters visible lines and
  highlights matches. Case-insensitive substring match." — the highlight half is what this story adds.
- `04_Progress_Widget/description.md#83-event-kinds` — the `judge_excluded` kind, its source signal
  `_judge_model_excluded`, its `error` tone, and the canonical line text "Judge model '<name>'
  excluded: <N> consecutive max-budget timeouts. Remaining tasks' judge phase will be skipped."
- `04_Progress_Widget/description.md#62-model-stability-indicator` — the judge callout is rendered
  "in addition to, not instead of" the Event-Log `judge_excluded` entry; the same exclusion is both
  the panel callout and the one-time log line.
- `04_Progress_Widget/description.md#12-event-bus-integration` — the `_judge_model_excluded`
  subscription renders the callout **and** appends the `judge_excluded` log line.
- `08_Cross_Cutting/08-I_edge_cases.md#EC-PROV-4b` — the Event Log appends exactly one
  `judge_excluded` entry in the canonical form; the event fires at most once per run.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b4-progressgateway` — the gateway surface the
  Progress controller reads through.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — the tone
  tokens (`error`) and highlight roles; no colour literal.

## Design constraints

- The LogController never builds the log HTML itself — it passes the `_judge_model_excluded` event
  to the log-formatting service and appends the returned line (D-R-06).
- The `judge_excluded` line appears **exactly once per run**: the event fires at most once per
  `BENCHMARK_RUN` activity, and a defensive duplicate delivery must not append a second line.
- Search highlighting is a view concern applied over the already-filtered visible lines; it never
  changes which lines are visible and never mutates the cached raw events, so switching verbosity or
  clearing the search re-renders cleanly.
- The `<name>` in the log line is the live-resolved judge provider display name (registry read while
  the run is in flight, DD-33); `<N>` is the event payload's `consecutive_timeouts`.
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope and emits `DEBUG`-level events —
  static event name + keyword fields — at every Event Bus handler invocation.

## Acceptance criteria

### STORY-073-AC-1

Given a `GRADED` run whose judge model is excluded, when the LogController receives the
`_judge_model_excluded` event carrying `consecutive_timeouts = N` and the judge provider name, then
exactly one `judge_excluded` log line is appended reading "Judge model '<name>' excluded: N
consecutive max-budget timeouts. Remaining tasks' judge phase will be skipped."

### STORY-073-AC-2

Given the LogController appends a `judge_excluded` line, when the log-formatting service renders it,
then the line carries the `error` tone token.

### STORY-073-AC-3

Given the run log contains lines, some of which contain the substring "judge" in any letter case,
when the user enters the search term "JUDGE", then only lines containing the substring
(case-insensitively) stay visible and the matched substring within each visible line is highlighted;
and when the search input is cleared, then all highlight marks are removed and the full buffer is
shown.

## Test plan

- STORY-073-AC-1 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/progress/_internal/tests/test_log_controller.py`,
  `test_judge_model_excluded_appends_one_log_line`. Covers EC-PROV-4b.
- STORY-073-AC-2 — unit, colocated
  `src/ollama_llm_bench/backend/log_formatting/tests/test_judge_excluded_rendering.py`,
  `test_judge_excluded_kind_renders_error_tone`.
- STORY-073-AC-3 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/progress/_internal/tests/test_log_search_highlight.py`,
  `test_search_filters_and_highlights_matches_case_insensitively`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-073.
- [ ] EC-PROV-4b has a passing test (exactly one canonical `judge_excluded` line per run).
- [ ] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the search
  no-term / term-present / term-cleared states and the judge-excluded log path.
- [ ] An architecture test confirms the LogController does not build the log HTML itself (it
  delegates to `backend/log_formatting`), and that the touched modules reference no
  `setStyleSheet`, embed no colour literal, and import no `asyncio`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/progress/` and
  `backend/log_formatting/`.
- [ ] `just trace` resolves this story's spec clauses; the record validates with no orphan clause
  and no orphan test for STORY-073.
- [ ] The module inventory is unchanged.
- [ ] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records.

## Notes

- STORY-060's notes recorded the `judge_excluded` run-log line and search highlighting as
  out-of-scope-at-the-time; this story picks them up.
- If `backend/log_formatting/` already maps the `judge_excluded` kind, AC-2's deliverable narrows to
  a proving test plus any tone/text correction; the LogController subscription (AC-1) and the view
  highlight (AC-3) are the substantive additions.
