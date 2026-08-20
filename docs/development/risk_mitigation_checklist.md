# Risk mitigation verification checklist

Each row R-001 through R-016 of the risk register's summary matrix
(`docs/v3_specification/15_Risks_and_Open_Questions/01_RISK_REGISTER.md` §3) is checked here
against the artifact that actually verifies its mitigation.

The register states what the mitigation *should* be. This document records whether anything in
the repository *proves* it. Those are different questions, and before STORY-093 fourteen of the
sixteen rows had only the register's own prose standing behind them.

Verdicts: `verified`, `waived`, `retired`.

- `verified` — the Evidence cell names a `path/to/file:LINE`, a `test_*` function, or a named CI
  workflow step that exercises the mitigation.
- `waived` — no such artifact exists. The row links to a `##` section below stating why, and what
  would close it. A waiver is a disclosure, not an approval.
- `retired` — the risk no longer applies and is superseded.

Prose alone is not a verdict. A row whose only backing is the register's own description of its
mitigation is `waived`, however plausible that description reads.

This document records what was observed. It never changes code: closing a waiver is its own
story.

## The checklist

| Risk  | Registered mitigation                                                                           | Verdict    | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ----- | ----------------------------------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R-001 | qasync event-loop stability on Python 3.13                                                      | `retired`  | **RETIRED** — superseded by R-016; see [R-001](#r-001--retired-superseded-by-r-016).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| R-002 | Unsigned-binary UX: checksums, per-OS unblock instructions, AV false-positive tracking          | `waived`   | **WAIVED** — checksums only; see [R-002](#r-002--waived-unsigned-binary-ux-is-one-third-built).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| R-003 | Cap CI spend: cancel superseded runs, order jobs cheapest-first                                 | `verified` | `.github/workflows/pr-gate.yml:8` (`concurrency` with `cancel-in-progress: true`); the cheapest-first `needs:` chain `lint` → `typecheck` (`pr-gate.yml:41`) → 3-OS `test` matrix (`pr-gate.yml:66`).                                                                                                                                                                                                                                                                                                                                                                                                                  |
| R-004 | Adaptive-timeout ladder is bounded and observable under a controllable clock                    | `waived`   | **WAIVED** — the ladder itself is clockless; see [R-004](#r-004--waived-the-timeout-ladder-is-tested-without-a-clock).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| R-005 | Serial execution plus a clear model-load failure path under memory pressure                     | `waived`   | **WAIVED** — load-failure half only; see [R-005](#r-005--waived-only-the-load-failure-half-of-memory-pressure-is-covered).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| R-006 | Persist each result before starting the next unit; never batch to the end                       | `verified` | `test_at_most_one_unit_in_flight_and_persist_before_next` (`backend/benchmark_pipeline/tests/test_serial_execution.py:28`); `test_no_row_enters_a_later_phase_before_the_earlier_phase_fully_drains` (`.../test_batching_drain.py:52`).                                                                                                                                                                                                                                                                                                                                                                                |
| R-007 | WAL, a busy timeout, a single writer, and a crash-recovery sweep at launch                      | `verified` | `PRAGMA journal_mode = WAL` (`backend/persistence/app_settings/_internal/pragmas.py:19`), `busy_timeout` (`:21`); `test_concurrent_writes_are_serialized_through_one_lock` (`tests/integration/persistence/test_single_writer.py:20`); `test_sweep_resets_only_the_four_mid_flight_statuses` (`.../test_crash_recovery_sweep.py:126`); `test_recover_in_flight_results_is_idempotent` (`:159`); `test_schema_version_mismatch_aborts_and_leaves_db_untouched` (`tests/integration/test_launch_schema_check.py:55`); `test_quit_closes_db_with_wal_checkpoint_truncate` (`tests/integration/test_quit_sequence.py:78`). |
| R-008 | Pin SDK majors, disable SDK-side retries, and test each adapter against wire stubs              | `verified` | `max_retries=0` at `backend/provider_openai_compatible/_internal/sdk_factory.py:57` and `backend/provider_anthropic/_internal/sdk_factory.py:43`; `pytest-httpserver` wire stubs in `tests/contract/test_llm_client_contract.py:55`.                                                                                                                                                                                                                                                                                                                                                                                   |
| R-009 | Probe embedding availability before a Graded run starts, without spending compute               | `verified` | `test_automatic_check_never_issues_model_compute` (`backend/readiness/tests/test_embedding_probe.py:33`); `test_listed_but_cannot_embed_model_still_passes_handshake` (`:69`); implementation `backend/readiness/_internal/embedding_probe.py`.                                                                                                                                                                                                                                                                                                                                                                        |
| R-010 | Keep large result sets responsive by filtering and paging on the SQL side                       | `waived`   | **WAIVED** — no part of this exists; see [R-010](#r-010--waived-no-part-of-the-large-result-set-mitigation-exists).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| R-011 | Build on all three OSes from per-OS PyInstaller spec files                                      | `waived`   | **WAIVED** — the spec files do not exist and the workflow references them; see [R-011](#r-011--waived-the-release-workflow-references-a-packaging-directory-that-does-not-exist).                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| R-012 | Confine cross-thread traffic to two audited modules and prove UI-thread delivery                | `verified` | `_qt_parity_rig` (`tests/conftest.py:66`); `test_only_qt_event_bus_declares_the_generic_relay_signal` (`tests/architecture/test_qt_event_bus_module.py:57`); `test_only_store_qt_bridge_and_backend_stores_import_psygnal` (`.../test_store_qt_bridge_module.py:56`); `test_stability_service_methods_called_only_from_dispatcher_thread_modules` (`.../test_stability_dispatcher_thread_only.py:114`).                                                                                                                                                                                                                |
| R-013 | Redact on both egress surfaces: `redact()` at the adapter boundary, `redact_for_log` on `app.*` | `verified` | `test_no_denylist_pattern_survives_either_redaction_surface` (`backend/errors/tests/test_redaction_fuzz.py`), plus the enumerated cases RT-01..RT-19 in `backend/errors/tests/test_redaction.py`. Two named residual risks: see [R-013](#r-013--residual-risks-behind-a-verified-verdict).                                                                                                                                                                                                                                                                                                                             |
| R-014 | Pin the full dependency graph in a tracked lockfile and audit it on release                     | `verified` | Tracked `uv.lock`, installed with `uv sync --frozen` in every workflow job; the `uv run pip-audit` step at `.github/workflows/release.yml:48`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| R-015 | Snapshot the provider name onto each result so a later rename cannot rewrite history            | `waived`   | **WAIVED** — the column exists, the invariant is untested; see [R-015](#r-015--waived-the-provider-name-snapshot-column-exists-but-nothing-pins-it).                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| R-016 | Bounded worker lifecycle: finite deadlines, cooperative cancellation, bounded quit              | `waived`   | **WAIVED** — three sub-invariants, none architecture-tested; see [R-016](#r-016--waived-the-concurrency-invariants-are-asserted-in-prose-not-in-tests).                                                                                                                                                                                                                                                                                                                                                                                                                                                                |

## R-001 — retired, superseded by R-016

The register itself records R-001 as **RETIRED / superseded by D-R-01** and replaced by R-016
(`01_RISK_REGISTER.md:68`). The v3 architecture bans `asyncio`, `anyio`, and `qasync` from `src/`
outright — enforced by the `hookify:block-asyncio-imports` rule — so there is no event loop whose
stability could be at issue.

This row needs no artifact. It is listed only so the checklist covers all sixteen register rows
and a reader does not mistake its absence for an oversight.

## R-002 — waived: unsigned-binary UX is one third built

The registered mitigation has three parts. One exists:

- **Checksums** — the `Checksum` step at `.github/workflows/release.yml:84-88` emits `SHA256SUMS`
  beside the artifacts.

Two do not:

- **Per-OS unblock instructions.** No document tells a user how to get past Gatekeeper or
  SmartScreen. Nothing under `docs/` covers it.
- **Antivirus false-positive tracking.** No issue template, no log, no process.

The checksum step is also downstream of R-011: it runs `cd dist-artifacts || exit 0`, so on a real
tag push it exits successfully having checksummed nothing, because the build step above it fails
first.

Closing this needs a Phase-13 distribution story, sequenced after R-011.

## R-004 — waived: the timeout ladder is tested without a clock

The adaptive-timeout ladder is implemented and tested — `backend/benchmark_pipeline/_internal/`
carries `units.py`, `warmup.py`, `provider_probe.py`, and `lightweight_call.py`, with matching
suites under `backend/benchmark_pipeline/tests/`.

What is missing is the part the risk is actually about. The register's concern is *mis-tuning*:
a ladder that stalls a run or wastes it. Demonstrating either requires driving the ladder across
its rungs under a controllable clock, and the ladder's own tests use no clock at all.

Fake-clock deadline coverage does exist, but it sits one layer down in a provider adapter, over
the per-request deadline rather than the ladder:
`test_stall_past_deadline_raises_timeout_and_closes_stream`
(`backend/provider_openai_compatible/tests/test_deadline.py:114`) and
`test_cold_start_within_budget_streams_instead_of_timing_out` (`:216`).

Closing this needs a ladder-level test that advances a fake clock through every rung and asserts
the total bound.

## R-005 — waived: only the load-failure half of memory pressure is covered

Two things can go wrong when many models load. The registered mitigation addresses both; the
repository addresses one.

- **Covered** — the model-load-failure path, by
  `tests/integration/test_first_use_model_load_failure.py`.
- **Not covered** — memory pressure itself. Nothing measures, bounds, or reacts to resident model
  memory. Serial execution limits concurrent load by construction, but no test pins that property
  against this risk, and no artifact addresses a host that runs out of memory mid-run.

Closing this needs a decision first: whether the application should detect memory pressure at all,
or whether serial execution plus a clean load-failure path is the whole intended mitigation. If it
is the whole mitigation, the register's wording should change and this row becomes `verified`
against the existing test.

## R-010 — waived: no part of the large-result-set mitigation exists

This is the largest gap in the register, and unlike the others nothing partial is in place.

- No SQL-side filtering or paging anywhere. `canFetchMore`, `LIMIT`, and `OFFSET` return zero hits
  across `src/`; result tables load their full set.
- `tests/perf/` contains only `.gitkeep`.
- No test asserts responsiveness, or any bound at all, on a large result set.

The three schema indexes that support result queries do exist
(`idx_results_run`, `idx_results_run_status`, `idx_results_run_task`, declared from
`backend/persistence/app_settings/_internal/schema_ddl.py:307`), so the database side is ready for
paging that the application never asks for.

Closing this needs a story that fixes a concrete row-count target, adds SQL-side paging behind the
result table model, and puts a measured test under `tests/perf/`.

## R-011 — waived: the release workflow references a packaging directory that does not exist

`.github/workflows/release.yml:74` runs:

```yaml
run: uv run --group build pyinstaller "packaging/${{ matrix.os }}.spec"
```

There is no `packaging/` directory and no `*.spec` file in the repository. The step's own preceding
comment (`release.yml:71-72`) says the spec files "land in Phase 13 ... this step is a placeholder
until then", so this is disclosed rather than accidental — but it means the release path is broken
today and would fail on the first real tag push, taking the packaging and checksum steps with it.

Nothing detects this: `release.yml` is tag-triggered, so no pull-request gate ever runs it.

Closing this needs the Phase-13 packaging story. Until then the risk is not merely unmitigated —
the mitigation as written cannot execute.

## R-013 — residual risks behind a `verified` verdict

Both redaction surfaces are implemented and tested, so this row is `verified`. Two gaps remain
inside it, recorded here rather than left implicit.

**Residual risk 1 — no architecture test pins the boundary.** All three provider adapters route
SDK exceptions through `redact()` in their `_internal/translate_exception.py`. Nothing enforces
that a *fourth* adapter would. The invariant is upheld by three independent implementations
agreeing, which is convention, not enforcement.

**Residual risk 2 — `redact_for_log` diverges from §7.2 on non-string field values.**
`08_REDACTION_PATTERNS.md` §7.2 step 2 says to serialise the log record to a line and apply the
denylist to *that*. The implementation instead applies the denylist to each field value
individually, and `_redact_field_value`
(`backend/errors/_internal/redaction.py:177-184`) returns any non-`str` value unchanged. A secret
inside a nested `list` or `dict`, or in a non-`str` value, therefore reaches the `app.*` stream
un-redacted unless its field name is on the never-log list.

The property test's scope is set accordingly and says so: it plants secrets in free text and in
string-valued fields only. Widening it without first fixing the implementation would assert a
behaviour the code does not have.

Closing residual risk 1 needs an architecture test over `backend/provider_*/`. Closing residual
risk 2 needs an implementation change, and is the higher-ranked of the two.

## R-015 — waived: the provider-name snapshot column exists but nothing pins it

The schema half of this mitigation is real. `benchmark_results.provider_name` is `TEXT NOT NULL`
with a non-empty check (`backend/persistence/app_settings/_internal/schema_ddl.py:215`), and
`benchmark_runs` carries the same snapshot shape for the judge and embedding providers
(`schema_ddl.py:118`, `:120`) with a paired-nullability check.

What is missing is any proof the snapshot behaves as a snapshot:

- No architecture test asserts that result writers populate `provider_name` from the run-time
  value rather than by joining `providers` at read time.
- No end-to-end test renames a provider after a completed run and asserts the historical UI still
  shows the original name.

`tests/architecture/test_results_reference_test_snapshot.py` is a near neighbour and does not cover
this — it pins the *test/role* snapshot, not the provider name.

Closing this needs the rename-after-run end-to-end test. It is cheap: rename a provider, reopen the
Result widget, assert the old name.

## R-016 — waived: the concurrency invariants are asserted in prose, not in tests

R-016 replaced R-001 as the concurrency risk, and carries three sub-invariants. The register states
that the finite-deadline invariant is architecture-tested. It is not — `tests/architecture/`
contains no test matching `deadline`.

| Sub-invariant                                 | Status                                                                                                                      |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Every blocking wait carries a finite deadline | No architecture test. The register's claim that one exists is incorrect.                                                    |
| Bounded force-quit                            | No artifact. `os._exit` does not appear anywhere in `src/`, so no bounded-escape hatch exists, and nothing tests the bound. |
| No raw threading outside audited modules      | No import-linter contract and no architecture test. `import threading` appears in ten `src/` modules, unconstrained.        |

The five import-linter contracts (`pyproject.toml:161-245`) cover layering, module privacy,
provider independence, and composition-root wiring. None of them covers threading.

This is the one row where the register is not merely silent but wrong, so it is the highest-value
waiver to close. Closing it needs an architecture test per line of the table above; the
no-raw-threading contract is expressible as an import-linter `forbidden` contract with an explicit
allowlist and is the cheapest of the three.
