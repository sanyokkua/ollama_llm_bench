---
id: STORY-115
title: Prune run logs at startup by adding the orphan rule and wiring the cleanup into launch
status: draft
spec_clauses:
  - 10_Domain_and_Data/07_FILE_LAYOUT.md#82-run-log-cleanup
  - 12_Quality_and_NFRs/03_OBSERVABILITY.md#42-run-log-retention
  - 12_Quality_and_NFRs/07_RESOURCE_LIMITS.md#5-run-log-and-backup-retention
  - 12_Quality_and_NFRs/07_RESOURCE_LIMITS.md#7-resource-limits-summary
  - 08_Cross_Cutting/08-M_app_lifecycle.md#2-launch--order-of-operations
modules:
  - backend/log_file_writer/
  - backend/persistence/runs/
  - backend/persistence/results/
acceptance_criteria:
  - STORY-115-AC-1
  - STORY-115-AC-2
  - STORY-115-AC-3
  - STORY-115-AC-4
edge_cases: []
depends_on:
  - STORY-088
adrs: []
owner: coder
estimate: M
---

# STORY-115 — Prune run logs at startup by adding the orphan rule and wiring the cleanup into launch

## Goal

**Blocked:** stays `draft` until STORY-088 is `done`. STORY-088 implements the ≤ 90-day age rule
that this story composes with the orphan rule and then wires into launch; STORY-088 is its only
dependency.

The shipped application never deletes a run log. `<app-data>/logs/run/` grows for the entire life of
the installation: after a few hundred runs the folder holds a file per run forever, including logs
for runs the user deleted from the history months ago. This story makes the retention the
specification describes actually happen — it adds the missing third rule (delete a log whose run no
longer exists) and, more importantly, calls the cleanup during launch so the pruning runs at all.

## In scope

- **The orphan rule.** `backend/log_file_writer/_internal/run_log_cleanup.py` deletes a run-log file
  whose run id is not among the run ids that still exist in the database. Its module docstring today
  says "the age rule and the orphan rule are explicitly out of scope for this module and are left to
  a future story"; STORY-088 is that story for the age rule, and this is that story for the orphan
  rule. Both stale docstrings (`run_log_cleanup.py`'s and `cleanup_run_logs`'s) are corrected.
- **The set of live run ids reaching the cleanup.** `cleanup_run_logs` grows a required
  `live_run_ids` argument. The caller — the launch sequence — computes it from
  `RunsStore.list_runs()` as the textual form of every `BenchmarkRun.run_id`. `RunsStore` needs no
  new method and `backend/persistence/runs/` needs no code change.
- **Composing the three rules.** The count rule, the age rule, and the orphan rule are applied
  together in one pass, per §8.2's "The age rule and the count rule are both applied; whichever
  removes more files governs."
- **The startup wiring — the change that closes the reported gap.** `compose.py` calls
  `cleanup_run_logs` during launch, immediately after `ResultsStore.recover_in_flight_results()`,
  which is where the crash-recovery sweep runs today (`compose.py:274`). Right now `cleanup_run_logs`
  is exported from `backend/log_file_writer/api.py:77` and from that package's `__init__.py`, and its
  only references anywhere in `src/` are those two files and its own colocated test — nothing in
  `compose.py` or the launch path calls it, so the prune never executes in the running application.

## Out of scope

- **The ≤ 90-day age rule itself** — implemented by STORY-088, which this story depends on. This
  story composes it with the other two rules and does not re-implement or re-test it in isolation.
- **Deciding what "older than 90 days" means.** STORY-088 settles that the age comparison uses the
  `unix_ts` encoded in the filename, read through the injected `Clock`. This story keeps that
  decision unchanged and does not switch to a database-sourced run-finished timestamp.
- **Settings-backup retention (≤ 20 files) and the temp-folder wipe** — §8.3 and §8.4 of the same
  file-layout section. They are separate startup housekeeping steps with no story yet; they are
  named here so they are not mistaken for fallout from this one.
- **The rotating application log** (§8.1) and the in-memory run-log panel buffer — both bounded by
  other mechanisms and untouched here.
- **Surfacing a prune failure to the user.** A file that cannot be deleted is a logging concern, not
  a new user-facing surface; no dialog, banner, or notification is added.
- **Any change to `RunsStore` or `ResultsStore`.** Both are consumed through their existing
  Protocols exactly as they are.

## Spec inputs

- `10_Domain_and_Data/07_FILE_LAYOUT.md#82-run-log-cleanup` — the authoritative three-rule table and
  the ordering: "At application startup, after the crash-recovery sweep, the run-log cleanup runs",
  with rules Age ("a run log whose corresponding run finished more than 90 days ago is deleted"),
  Count ("when more than 200 run logs remain, the oldest are deleted until 200 remain"), and Orphans
  ("a run log whose `run_id` no longer exists in the database (the run was deleted) is deleted"),
  followed by "The age rule and the count rule are both applied; whichever removes more files
  governs."
- `12_Quality_and_NFRs/03_OBSERVABILITY.md#42-run-log-retention` — the same three rules restated, plus
  the fact that fixes the correctness question this story would otherwise have to guess at: "A run
  log is never written after its run reaches a terminal state, so a pruned file is never re-created."
  Deleting an orphan is therefore permanent and safe.
- `12_Quality_and_NFRs/07_RESOURCE_LIMITS.md#5-run-log-and-backup-retention` — the retention row for
  `logs/run/*.log`: "At most 200 files; none older than 90 days; no orphan (a log whose run was
  deleted)", pruned "At startup, after the recovery sweep."
- `12_Quality_and_NFRs/07_RESOURCE_LIMITS.md#7-resource-limits-summary` — the summary row fixing the
  numbers and the enforcement mechanism: "≤ 200 files, ≤ 90 days, no orphans", "Oldest-first /
  age-based prune at startup", enforced by "Startup cleanup; integration test". The spec names an
  integration test as the enforcement; AC-3 is that test.
- `08_Cross_Cutting/08-M_app_lifecycle.md#2-launch--order-of-operations` — the launch order the wiring
  must fit into. Step 5 opens the database and checks the schema, step 6 seeds defaults, step 8
  builds the object graph, and step 11 enters the Qt event loop. The cleanup belongs inside the
  object-graph build, after the stores exist and after the recovery sweep, and strictly before the
  event loop is entered — never on a timer or a first-idle tick.

## Design constraints

- **`backend/log_file_writer/` must not learn about persistence.** The module inventory records its
  notable dependencies as `backend/infra` alone, and STORY-088 deliberately kept the orphan rule out
  precisely because it "requires knowing which run ids still exist — a dependency on the runs store
  that `backend/log_file_writer/` deliberately does not have". The seam is therefore **inbound data,
  not an inbound dependency**: `cleanup_run_logs` accepts the live run ids as a plain
  `frozenset[str]` parameter, and the composition root — the only file allowed to know about both —
  reads them from `RunsStore` and passes them in. `backend/log_file_writer/` imports no persistence
  module, no `RunsStore` Protocol, and no domain run type; the module inventory's dependency column
  stays true and needs no edit.
  - This is not forced by `import-linter`: `pyproject.toml`'s contracts are Qt-freedom, private
    internals, provider independence, sole-compose-root, and adapters-never-import-ui — none of them
    would reject a `log_file_writer → persistence.runs` import. It is forced by the module
    inventory's dependency column and by keeping the cleanup a pure function of a directory plus
    three plain inputs, which is what makes it testable without a database.
- **`live_run_ids` is a required keyword argument with no default.** An empty set is a legitimate
  input (a fresh installation has no runs, so every stray run log is an orphan) *and* is exactly what
  a caller that forgot to supply it would produce — and it deletes every run log. A required
  parameter makes the omission a call-site error instead of silent data destruction. Do not give it
  an `icontract` precondition: the emptiness is not distinguishable as a programmer invariant, and
  the run set is data, not a caller invariant.
- **The three rules compose in one pass, and the composition is well-defined because two of them are
  prefixes.** The age set and the count set are both prefixes of the run-log files ordered
  oldest-timestamp-first, so one always contains the other and their union is exactly the larger of
  the two — which is what makes "whichever removes more files governs" literally true rather than
  ambiguous. The orphan set is *not* a prefix (an orphan can carry any timestamp), so the deleted set
  is the orphan set unioned with the larger of the age and count sets. Implement it that way and say
  so in the docstring.
- **`cleanup_run_logs` will exceed the four-parameter limit.** After STORY-088 it carries
  `platform_detector`, `clock`, `keep_count`, and `max_age_days`; `live_run_ids` is a fifth.
  `03_CODING_STANDARDS.md`'s limit is four, and the sanctioned remedy is to group them — introduce a
  frozen `msgspec.Struct` retention-policy value in `backend/log_file_writer/models.py` carrying the
  three tunables (`keep_count`, `max_age_days`, `live_run_ids`) so the public signature stays within
  the limit. Do not solve it by widening the limit or by adding a module-level default.
- A file whose name does not match the `run_<run_id>_<unix_ts>.log` template is left untouched by all
  three rules, exactly as the count rule already does. The run id compared against `live_run_ids` is
  the textual segment between `run_` and the final `_<unix_ts>`; `RunId` is an `int`, so the caller
  supplies `str(run.run_id)`.
- A missing run-log directory is not an error — it has nothing to prune.
- `backend/log_file_writer/` stays Qt-free and asyncio-free.
- **The cleanup runs synchronously on the launch thread, before the Qt event loop is entered.** It is
  bounded file I/O over at most a few hundred small files; do not submit it to the `TaskRunner` and
  do not block on a `Future` for it. Nothing may be scheduled onto the event loop to make it happen
  later.
- **A deletion failure must never abort launch.** An individual file that cannot be unlinked
  (permission denied, the file vanished between listing and deleting) is logged to the `app.*` stream
  and the pass continues with the remaining files. This is a `PermanentError`-class condition handled
  as data, not a crash: launch has already succeeded by this point and housekeeping is not a
  precondition for a usable application.
- `compose.py` is at 405 lines against a 450-line architecture-test budget
  (`tests/architecture/test_compose_line_budget.py`). The wiring must fit inside that headroom; if it
  cannot be expressed in a handful of lines, put the helper in `_compose_shims.py` rather than
  widening the budget.

## Acceptance criteria

### STORY-115-AC-1

The orphan rule classifies each file in the run-log directory by whether its encoded run id is still
a live run:

| File in `<app-data>/logs/run/` | Encoded run id present in `live_run_ids` | Outcome after the prune |
| ------------------------------ | ---------------------------------------- | ----------------------- |
| `run_7_1700000000.log`         | yes                                      | retained                |
| `run_8_1700000000.log`         | no                                       | deleted                 |
| `run_9_1700000000.log`         | `live_run_ids` is empty                  | deleted                 |
| `notes.txt`                    | not applicable — name does not match     | untouched               |
| `run_10_1700000000.log.bak`    | not applicable — name does not match     | untouched               |

Every deletion decision in this table is made regardless of the file's age and regardless of how many
files the directory holds.

### STORY-115-AC-2

The count, age, and orphan rules are applied together in one pass, and where the count and age rules
disagree the one that removes more files governs. With the retention policy fixed at 200 files and
90 days and the clock pinned:

| Directory content                                                                | Files deleted                               | Files surviving |
| -------------------------------------------------------------------------------- | ------------------------------------------- | --------------- |
| 210 files, none older than 90 days, every run live                               | the 10 oldest                               | 200             |
| 150 files, 30 of them older than 90 days, every run live                         | those 30                                    | 120             |
| 210 files, 40 of them older than 90 days, every run live                         | the 40 oldest (age removes more than count) | 170             |
| 100 files, none older than 90 days, 7 whose run id is absent from `live_run_ids` | those 7                                     | 93              |
| 210 files, 40 older than 90 days, plus 3 recent files whose run id is absent     | the 40 oldest plus those 3                  | 167             |

### STORY-115-AC-3

Given an application-data directory holding more run-log files than the retention policy allows,
when the application is launched, then the run-log directory is pruned to the policy before the
application reaches its running state — with no test code calling `cleanup_run_logs` itself.

### STORY-115-AC-4

Given a launch, when the run-log prune runs, then the crash-recovery sweep
(`ResultsStore.recover_in_flight_results`) has already completed, and the prune has itself completed
before the Qt event loop is entered.

## Test plan

- STORY-115-AC-1 — unit, table-driven `@pytest.mark.parametrize` with one case per row and no loop in
  the test body, colocated
  `src/ollama_llm_bench/backend/log_file_writer/tests/test_run_log_cleanup.py`,
  `test_orphan_rule_deletes_only_logs_whose_run_is_gone`.
- STORY-115-AC-2 — unit, table-driven `@pytest.mark.parametrize` with one case per row, same file,
  `test_count_age_and_orphan_rules_compose_in_one_pass`. Uses `tmp_path` and the injected `Clock` so
  "now" is pinned rather than creating files with real 91-day-old timestamps.
- STORY-115-AC-3 — integration, `tests/integration/test_run_log_retention_at_startup.py`,
  `test_launching_the_application_prunes_run_logs`. Builds the real application through the
  composition root against a `tmp_path` application-data root seeded with an over-quota run-log
  directory, and asserts the directory is within policy afterwards. **This test fails today** — not
  because the pruning logic is wrong, but because nothing calls it; it is the test that proves the
  wiring exists. It must reach the pruning through the launch path only, never by importing or
  calling `cleanup_run_logs`.
- STORY-115-AC-4 — integration, same file,
  `test_prune_runs_after_the_recovery_sweep_and_before_the_event_loop`. Records the call order of
  `recover_in_flight_results` and the prune against a shared recorder, and asserts the prune has
  completed by the time `build_app` returns — so it cannot have been deferred onto the event loop.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-115.
- [ ] `cleanup_run_logs` applies the count, age, and orphan rules, and neither its own docstring nor
  `run_log_cleanup.py`'s module docstring still says the orphan rule is out of scope.
- [ ] `cleanup_run_logs` is called from the launch path, and a repository-wide search for it returns
  a call site outside `backend/log_file_writer/` and its tests.
- [ ] `backend/log_file_writer/` imports no `backend/persistence/*` module, confirmed by an
  architecture check.
- [ ] `compose.py` stays within its 450-line budget.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
- [ ] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [ ] The next candidate stories are proposed in the closing report.

## Unblocks and next steps

**Unblocks**

Nothing. No story's `depends_on` names STORY-115, so finishing it makes no `draft` → `ready` flip
available and the flip checkbox above is satisfied vacuously — say so explicitly in the closing
report rather than leaving it ambiguous.

**What to do on completion**

1. There is no successor story to flip; confirm that in the closing report.
1. Re-run `just trace` — the traceability record embeds each story's `status`, so flipping this story
   to `done` makes it stale — then `just trace-check`.
1. Propose the next stories to pick up, ranked, in the closing report rather than stopping silently.
   The two adjacent, still-unowned pieces of the same startup-housekeeping section are the natural
   candidates and should be proposed as stories rather than folded in here: the settings-backup
   retention cap (§8.3, at most 20 `settings_<unix_ts>.yaml` files, currently unenforced) and the
   temp-folder wipe (§8.4, `<app-data>/temp/` emptied at every startup before any subsystem uses it).
   Verify each against the code before writing it up — this story did not confirm whether either is
   already wired.

## Notes

- **Why the orphan rule could not go in STORY-088.** STORY-088's Out-of-scope section states it
  plainly: an orphan is "a log whose run was deleted", so removing orphans requires knowing which run
  ids still exist, which `backend/log_file_writer/` has no way to learn on its own. That is a design
  question, not just extra work, and the answer this story records is the parameter seam above.
- **Why the startup wiring belongs with the orphan rule rather than with STORY-088.** Both need the
  same new call site. STORY-088 already touches three modules, which is its `M` ceiling, and adding
  the wiring would have pushed it past that. Landing the orphan rule and the wiring together means
  the launch sequence is written once, with the final signature, instead of twice.
- **`compose.py` is not a citable module.** The load-bearing change for AC-3 and AC-4 is in
  `compose.py`, which the module-inventory parser cannot cite (it accepts only backtick-quoted
  `backend/…/`, `adapters/…/`, `ui/…/` paths). Following the precedent STORY-094 and STORY-095 set
  for their own non-inventory deliverables, `modules:` cites the three modules the story genuinely
  exercises: `backend/log_file_writer/` (the only one whose code changes),
  `backend/persistence/runs/` (supplies the live run-id set through its existing `list_runs()`; no
  change), and `backend/persistence/results/` (the module the inventory records as owning the
  `recover_in_flight_results` startup sweep, which AC-4 orders against; no change).
- **No edge-case id is claimed, on purpose.** `run_log_cleanup.py`'s docstring cites `EC-FL-10`, but
  that identifier is already owned and discharged by STORY-037 (`done`), and it describes the count
  rule alone — "More than 200 run logs accumulate → startup cleanup prunes the oldest down to 200".
  Claiming it here would record duplicate coverage for behaviour this story does not introduce.
  `10_Domain_and_Data/07_FILE_LAYOUT.md` §11 is that file's own edge-case table (eight rows:
  `EC-FL-1` to `EC-FL-4` and `EC-FL-7` to `EC-FL-10`), and none of them covers the orphan rule or the
  startup wiring — so there is no honest id to claim and `edge_cases:` is empty.
