---
id: STORY-073
title: Add the Progress run-log judge-excluded line and run-log search-match highlighting
status: in-progress
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

- [x] Every acceptance criterion has a passing test that names STORY-073.
- [x] EC-PROV-4b has a passing test (exactly one canonical `judge_excluded` line per run).
- [x] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the search
  no-term / term-present / term-cleared states and the judge-excluded log path.
- [x] An architecture test confirms the LogController does not build the log HTML itself (it
  delegates to `backend/log_formatting`), and that the touched modules reference no
  `setStyleSheet`, embed no colour literal, and import no `asyncio`.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/progress/` and
  `backend/log_formatting/`.
- [x] `just trace` resolves this story's spec clauses; the record validates with no orphan clause
  and no orphan test for STORY-073.
- [x] The module inventory is unchanged.
- [x] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records.

## Notes

- STORY-060's notes recorded the `judge_excluded` run-log line and search highlighting as
  out-of-scope-at-the-time; this story picks them up.
- If `backend/log_formatting/` already maps the `judge_excluded` kind, AC-2's deliverable narrows to
  a proving test plus any tone/text correction; the LogController subscription (AC-1) and the view
  highlight (AC-3) are the substantive additions.
- Incidental additive cross-module touch: this story's `modules:` front-matter names only
  `ui/progress/` and `backend/log_formatting/`, but rendering the `judge_excluded` event kind (the
  In-scope item) presupposes the kind exists as a domain value. `backend/domain/models.py` gained
  one additive `StrEnum` member, `RunLogEventKind.JUDGE_EXCLUDED = "judge_excluded"`, plus two new
  optional fields on the `RunLogEvent` struct, `provider_name: str | None` and
  `consecutive_timeouts: int | None`, both defaulting to `None` so no existing construction site
  breaks. This is a purely additive domain change, not a new module dependency.
- Story-text discrepancy: the Test plan section above cites test paths under
  `ui/progress/_internal/tests/` (e.g. `_internal/tests/test_log_controller.py`). That path does
  not exist in this codebase — colocated tests live one level up, outside `_internal/`. The actual
  test files are `src/ollama_llm_bench/ui/progress/tests/test_log_controller.py` and
  `src/ollama_llm_bench/ui/progress/tests/test_log_search_highlight.py`, and the backend test is at
  `src/ollama_llm_bench/backend/log_formatting/tests/test_judge_excluded_rendering.py`. The tests
  that were written follow the real, existing colocated-`tests/` layout.
- Known follow-up (found during review, deliberately out of scope for this story): the run-log
  search **filter** (`filter_search` in `ui/progress`, pre-existing and untouched by this story)
  matches against tag-stripped log-line text but does not decode HTML entities before matching. The
  new search **highlighter** added by this story does decode entities before matching. The visible
  effect: if a line's only occurrence of a search term is inside a raw entity — for example the
  term "amp" appearing only as part of the literal text `&amp;` — the filter still keeps that line
  visible (a tag-stripped-text match), but the highlighter finds no un-entity-decoded occurrence to
  mark, so the line shows with zero highlighted spans. The same divergence has a second, equally
  narrow variant found in the final whole-branch review: the filter matches against the line's
  *concatenated* tag-stripped text, while the highlighter matches each between-tags text segment
  independently — so a term that straddles a markup-tag boundary (e.g. spanning the end of a tone
  span and the text after it) also keeps the line visible while producing zero marks. Fixing both
  requires changing `filter_search`'s matching semantics (decode entities and match per visible
  segment, or have the highlighter match across segments), which is a change to STORY-060's
  existing behaviour and is left for a future story rather than folded in here; one unified
  matching implementation shared by filter and highlighter would close both gaps at once.
- Plan/test deviation: the implementation plan's originally drafted unit tests used the literal
  hex string `"#334455"` as a stand-in highlight-background value. The architecture scan
  `test_progress_embeds_no_colour_literal` in `tests/architecture/test_progress_boundaries.py`
  rejects any `#RRGGBB`-shaped string literal anywhere under `ui/progress/`, including its test
  files, so that literal would have failed the architecture gate. The landed tests instead use the
  non-colour placeholder string `"test-highlight-token"` wherever a highlight-background value is
  needed. The `LogFormatter`/highlight helper code being tested does not itself validate that its
  colour-role argument is shaped like a hex colour, so this substitution changes no assertion's
  meaning — it only avoids tripping an unrelated architecture check with an incidental test value.
