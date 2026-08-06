---
id: STORY-088
title: Close three known test debts — Gemini contract leg, run-log retention, and a shared resume fixture
status: ready
spec_clauses:
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#6a-shared-contract-test-suite-per-protocol
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#7a-the-provider-wire-stub-transport-level-test-double
  - 12_Quality_and_NFRs/07_RESOURCE_LIMITS.md#5-run-log-and-backup-retention
  - 12_Quality_and_NFRs/07_RESOURCE_LIMITS.md#7-resource-limits-summary
modules:
  - backend/provider_gemini/
  - backend/log_file_writer/
  - ui/resume_benchmark/
acceptance_criteria:
  - STORY-088-AC-1
  - STORY-088-AC-2
  - STORY-088-AC-3
edge_cases: []
depends_on: []
adrs: []
owner: coder
estimate: M
---

# STORY-088 — Close three known test debts — Gemini contract leg, run-log retention, and a shared resume fixture

## Goal

Clear three specific, independently verifiable debts around the test suite. One is a documentation
defect in a test module, one is a piece of spec-required behaviour that was never implemented and so
was never tested, and one is a triplicated test helper. This story was originally written against a
stale snapshot of the repository and has been re-scoped in place — read the acceptance criteria as
written, not the older summary they replaced.

**Note on ownership.** The `owner` is `coder`, not `tester`: AC-2 now requires writing production
code (the run-log age-prune rule), not only a test.

## In scope

- **AC-1 — correct a stale module docstring.** `tests/contract/test_llm_client_contract.py` **already
  runs the Gemini legs**: `_make_gemini_real_client` (line 287) and `_make_gemini_fake_client`
  (line 322) exist, `_build_llm_client` dispatches to both (lines 366–368), and the `llm_client`
  fixture is parametrized over all six legs — `openai_real`, `openai_fake`, `anthropic_real`,
  `anthropic_fake`, `gemini_real`, `gemini_fake` (lines 371–380). The only thing left wrong is the
  module docstring: line 19 still says
  `params=["openai_real", "openai_fake", "anthropic_real", "anthropic_fake"]` — four legs, not
  six. While correcting it, also fix the neighbouring stale sentence at lines 21–23 claiming
  `embed`/`list_models` are "OpenAI-only" assertions: the `embedding_capable_llm_client` fixture at
  line 388 is parametrized over `openai_real`, `openai_fake`, `gemini_real`, `gemini_fake`, so those
  assertions cover the embedding/discovery-capable legs, not OpenAI alone.
- **AC-2 — implement the ≤ 90-day run-log age rule, then test it together with the count rule.**
  `backend/log_file_writer/_internal/run_log_cleanup.py` implements only the count rule
  (`cleanup_run_logs_by_count`, capping the directory at `DEFAULT_RUN_LOG_KEEP_COUNT = 200`), and its
  own module docstring says so explicitly: "Only the count rule from §8.2 is implemented here — the
  age rule and the orphan rule are explicitly out of scope for this module and are left to a future
  story." This story is that future story for the **age** rule. Implement it, expose it through the
  existing public `cleanup_run_logs` in `backend/log_file_writer/api.py`, and update both stale
  docstrings.
- **AC-3 — consolidate a triplicated test fake.** An identical `compose_filename` fake method is
  defined three times under `src/ollama_llm_bench/ui/resume_benchmark/tests/`:
  `test_actions.py` line 531, `test_controller.py` line 190, and `test_controller_menu_actions.py`
  line 217. That directory has **no `conftest.py`** yet — create one and move the fake into a single
  shared fixture, with all three files consuming it.

## Out of scope

- **The run-log orphan rule.** `12_Quality_and_NFRs/07_RESOURCE_LIMITS.md` §5 defines an orphan as
  "a log whose run was deleted", so removing orphans requires knowing which run ids still exist —
  a dependency on the runs store that `backend/log_file_writer/` deliberately does not have. It
  stays out of scope and out of this story's modules list; it needs its own story and a decision on
  where that cross-module lookup belongs.
- **Wiring the prune into application startup.** `cleanup_run_logs` is a public function that
  nothing currently calls: it appears in `api.py`, `__init__.py`, and its own colocated tests, and
  **not** in `compose.py`. The spec says the prune happens at startup, so the app does not currently
  do it — but wiring it would add `compose.py` as a fourth module and push this story past its `M`
  bound. AC-2 therefore tests `cleanup_run_logs` directly. The startup wiring needs its own story.
- **Any change to the Gemini adapter or the resume widget's production code.** AC-1 is a docstring
  fix and AC-3 is a test refactor. (The former blanket "no change to production code" line has been
  removed: AC-2 now deliberately changes production code in `backend/log_file_writer/`.)
- **The run-log panel buffer bound** — a separate UI concern; this story covers on-disk run-log file
  retention only.

## Spec inputs

- `16_Engineering_Standards/07_TESTING_STANDARD.md#6a-shared-contract-test-suite-per-protocol` —
  every swap-point Protocol with a real implementation and a `testing.py` fake carries one shared
  contract-test suite run against both. Both Gemini legs already satisfy this; AC-1 only makes the
  module's own docstring say so.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#7a-the-provider-wire-stub-transport-level-test-double`
  — the `LLMClient` real leg runs against the `pytest-httpserver` wire stub via the SDK's base-URL
  override, fully offline. The Gemini real leg already does this; AC-1 must not change it.
- `12_Quality_and_NFRs/07_RESOURCE_LIMITS.md#5-run-log-and-backup-retention` — the authoritative
  statement of the retention rule: per-run log files are held to "At most 200 files; none older than
  90 days; no orphan (a log whose run was deleted)", pruned "At startup, after the recovery sweep.
  The age rule and the count rule are **both applied; whichever removes more files governs**." That
  last clause is the one AC-2's test must pin — the two rules compose, they are not alternatives.
- `12_Quality_and_NFRs/07_RESOURCE_LIMITS.md#7-resource-limits-summary` — the summary row fixing the
  numbers and the mechanism: "≤ 200 files, ≤ 90 days, no orphans", "Oldest-first / age-based prune
  at startup", enforced by "Startup cleanup; integration test". The spec is the authority on both
  the 200 and the 90; take them from here, not from the current constant.

## Design constraints

- `backend/log_file_writer/` is Qt-free and asyncio-free.
- The age rule must read the current time through the injected **`Clock` Protocol**, not
  `datetime.now()` / `time.time()` directly, so the test can pin "now" deterministically rather than
  creating files with real timestamps 91 days in the past.
- A file that does not match the `run_<run_id>_<unix_ts>.log` template is left untouched by both
  rules, exactly as the count rule already does; the age comparison uses the `unix_ts` encoded in
  the filename.
- A missing run-log directory is not an error — it simply has nothing to prune.
- `cleanup_run_logs`'s `icontract` preconditions guard programmer invariants only (a non-negative
  keep count, a non-negative max age); they never validate user input.
- The Gemini real contract leg contacts no live model — it runs against the wire stub on
  `127.0.0.1`, matching the offline-CI rule and the existing OpenAI/Anthropic legs.
- The consolidated resume fixture preserves the exact filenames the three resume export tests
  already assert on; no assertion in those tests changes except where the fake comes from.

## Acceptance criteria

### STORY-088-AC-1

Given the shared `LLMClient` contract-test suite module,
when its module docstring is read,
then it lists the six legs actually registered on the `llm_client` fixture — `openai_real`,
`openai_fake`, `anthropic_real`, `anthropic_fake`, `gemini_real`, `gemini_fake` — and no leg named
in the docstring is absent from the fixture, nor any fixture leg absent from the docstring.

### STORY-088-AC-2

Given a run-log directory holding both more than 200 files and files whose encoded timestamp is more
than 90 days before the injected clock's "now",
when the run-log prune runs,
then the surviving files are at most 200 in number **and** all at most 90 days old, deletion having
proceeded oldest-timestamp-first, with every file that violated either rule removed and every file
that violated neither retained.

### STORY-088-AC-3

Given a resume-widget export action,
when a run is exported,
then the target filename is the shared `conftest.py` fixture's `compose_filename` result, and
`test_actions.py`, `test_controller.py`, and `test_controller_menu_actions.py` each obtain that fake
from the single shared fixture rather than defining their own copy.

## Test plan

- STORY-088-AC-1 — unit, `tests/contract/test_llm_client_contract.py`,
  `test_module_docstring_lists_every_registered_leg` — parses this module's own `__doc__` and the
  `llm_client` fixture's registered params and asserts the two sets are equal, so the docstring
  cannot silently rot again the next time a provider is added.
- STORY-088-AC-2 — integration (`tmp_path`, injected `Clock`),
  `tests/integration/test_run_log_retention.py`,
  `test_startup_prune_caps_run_logs_to_200_files_and_90_days` — builds a directory that violates
  both rules at once and asserts the exact surviving file set, per §5's "whichever removes more
  files governs".
- STORY-088-AC-3 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/resume_benchmark/tests/test_actions.py`,
  `test_export_uses_shared_compose_filename_fixture`, with the fixture living in the new
  `src/ollama_llm_bench/ui/resume_benchmark/tests/conftest.py` and `test_controller.py` /
  `test_controller_menu_actions.py` consuming the same fixture.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-088.
- [ ] `cleanup_run_logs` applies both the count rule and the age rule, and neither its own docstring
  nor `run_log_cleanup.py`'s module docstring still says the age rule is out of scope.
- [ ] No `compose_filename` fake remains defined inside any
  `src/ollama_llm_bench/ui/resume_benchmark/tests/test_*.py`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
- [ ] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [ ] The next candidate stories are proposed in the closing report.

## Unblocks and next steps

**Unblocks**

- **STORY-115** — the run-log orphan rule plus the startup wiring, that is, exactly the two items
  this story leaves open below. **STORY-088 is its only dependency**, so finishing this story
  unblocks it immediately: flip
  `docs/stories/story-115-run-log-retention-orphan-rule-and-startup-wiring.md` from `draft` to
  `ready` with no further conditions to check.
- **STORY-093** — the Phase-12 traceability, risk, and architecture documentation story. Flip it
  `draft` → `ready` **only once every other story it depends on is `done`**: STORY-076 through
  STORY-089, STORY-091, STORY-092, and STORY-114. STORY-088 is one input among many.

**What to do on completion**

Once STORY-088's acceptance-criteria tests pass:

1. For each story listed under **Unblocks**, check its remaining `depends_on` entries. Flip its
   `status` from `draft` to `ready` only if every one of them is now `done`; otherwise leave it
   `draft` and name the outstanding dependencies in the closing report. STORY-115 has no other
   dependency, so it flips unconditionally.
1. Re-run `just trace` — the traceability record embeds each story's `status`, so it goes stale the
   moment a status changes — and then `just trace-check`.
1. Propose the next stories to pick up, ranked, in the closing report rather than stopping silently.
   The natural next picks are the other independently-`ready` finalization stories that also gate
   STORY-093 — STORY-084, STORY-085, and STORY-092 — since none of them depends on this one.
1. The two items this story deliberately leaves open — the run-log **orphan** rule, and wiring
   `cleanup_run_logs` into application startup — are both already owned by STORY-115, so they no
   longer need a story written for them. Name STORY-115 in the closing report as the immediate
   follow-on rather than re-raising them as unowned.
