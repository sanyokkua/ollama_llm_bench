# Risk Register

**Status:** Draft
**Owner:** human-reviewer
**Audience:** human, architect
**Last Updated:** 2026-06-06
**Cross-references:** [02_OPEN_QUESTIONS.md](02_OPEN_QUESTIONS.md), [03_PROPOSED_ADRS.md](03_PROPOSED_ADRS.md), [../11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md](../11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md), [../13_Distribution_and_Release/](../13_Distribution_and_Release/), [../10_Domain_and_Data/](../10_Domain_and_Data/), [../08_Cross_Cutting/](../08_Cross_Cutting/)

This document catalogs the implementation, operational, and distribution risks of Ollama LLM Bench that can plausibly affect delivery, correctness, or the end-user experience. Each risk states a probability, an impact, a concrete mitigation plan, the responsible owner, and the trigger conditions that should escalate the risk into active management. The register is a living artifact: it is reviewed at the start of every phase and updated whenever a mitigation lands or a trigger fires.

---

## Table of Contents

1. [Scope and Method](#1-scope-and-method)
2. [Risk Scoring Scale](#2-risk-scoring-scale)
3. [Risk Summary Matrix](#3-risk-summary-matrix)
4. [Risk Details](#4-risk-details)
   - [R-001 — qasync event-loop stability on Python 3.13](#r-001--qasync-event-loop-stability-on-python-313)
   - [R-002 — Unsigned binary distribution UX (Gatekeeper / SmartScreen)](#r-002--unsigned-binary-distribution-ux-gatekeeper--smartscreen)
   - [R-003 — GitHub Actions free-tier CI minute exhaustion (macOS arm64)](#r-003--github-actions-free-tier-ci-minute-exhaustion-macos-arm64)
   - [R-004 — Adaptive-timeout mis-tuning stalls or wastes runs](#r-004--adaptive-timeout-mis-tuning-stalls-or-wastes-runs)
   - [R-005 — Local LLM memory pressure when many models load](#r-005--local-llm-memory-pressure-when-many-models-load)
   - [R-006 — Long-running batched pipeline holding partial results](#r-006--long-running-batched-pipeline-holding-partial-results)
   - [R-007 — SQLite WAL corruption and crash recovery](#r-007--sqlite-wal-corruption-and-crash-recovery)
   - [R-008 — Provider SDK breaking changes under a latest-versions policy](#r-008--provider-sdk-breaking-changes-under-a-latest-versions-policy)
   - [R-009 — Embedding-model availability for Graded Benchmark](#r-009--embedding-model-availability-for-full-grading)
   - [R-010 — Large result sets in tables and charts](#r-010--large-result-sets-in-tables-and-charts)
   - [R-011 — Cross-platform packaging drift (PyInstaller)](#r-011--cross-platform-packaging-drift-pyinstaller)
   - [R-012 — Cross-thread signal marshalling defects](#r-012--cross-thread-signal-marshalling-defects)
   - [R-013 — Secret leakage through an un-redacted egress path](#r-013--secret-leakage-through-an-un-redacted-egress-path)
   - [R-014 — Unbounded dependency surface from latest-version pinning](#r-014--unbounded-dependency-surface-from-latest-version-pinning)
   - [R-015 — Provider renamed after a completed run is referenced in historical UI](#r-015--provider-renamed-after-a-completed-run-is-referenced-in-historical-ui)
   - [R-016 — Worker-thread lifecycle and cooperative-cancellation correctness](#r-016--worker-thread-lifecycle-and-cooperative-cancellation-correctness)
5. [Review Cadence](#5-review-cadence)

---

## 1. Scope and Method

The risks below are derived from the binding technical decisions, the research corpus, and the confirmed project decisions (decision log D-001 through D-029). They cover four categories:

- **Concurrency and runtime** — the qasync event loop, cancellation, the batched pipeline.
- **Data integrity** — SQLite WAL behaviour, crash recovery, large result sets.
- **External dependencies** — provider SDKs, local model runtimes, embedding models.
- **Distribution and operations** — unsigned binaries, CI budget, cross-platform packaging.

Each risk is assigned a stable identifier (`R-NNN`). Identifiers are never reused. A retired risk keeps its number with a `Retired` status.

## 2. Risk Scoring Scale

**Probability** — likelihood the risk materializes during the build or first year of operation:

- **Low** — unlikely; would require an unusual confluence of conditions.
- **Medium** — plausible; expected to occur at least once if unmitigated.
- **High** — expected to occur, possibly repeatedly, without active mitigation.

**Impact** — severity if the risk materializes:

- **Low** — local inconvenience; recoverable within the same session.
- **Medium** — lost work, degraded UX, or a delayed milestone; recoverable with effort.
- **High** — data loss, blocked release, or a defect reaching users.

## 3. Risk Summary Matrix

| ID | Risk | Probability | Impact | Owner |
|------|------|-------------|--------|-------|
| R-001 | qasync event-loop stability on Python 3.13 — **RETIRED / superseded by D-R-01**; replaced by R-016 | — | — | Concurrency lead |
| R-002 | Unsigned binary distribution UX | High | Medium | Release engineer |
| R-003 | GitHub Actions free-tier CI minute exhaustion | Medium | Medium | Release engineer |
| R-004 | Adaptive-timeout mis-tuning | Medium | Medium | Concurrency lead |
| R-005 | Local LLM memory pressure | Medium | High | Provider-integration lead |
| R-006 | Long pipeline holding partial results | Medium | High | Concurrency lead |
| R-007 | SQLite WAL corruption / crash recovery | Low | High | Persistence lead |
| R-008 | Provider SDK breaking changes | High | Medium | Provider-integration lead |
| R-009 | Embedding-model availability for Graded Benchmark | Medium | Medium | Provider-integration lead |
| R-010 | Large result sets in tables and charts | Medium | Medium | UI lead |
| R-011 | Cross-platform packaging drift | Medium | Medium | Release engineer |
| R-012 | Cross-thread signal marshalling defects | Medium | High | Architecture lead |
| R-013 | Secret leakage through an un-redacted egress path | Low | High | Architecture lead |
| R-014 | Unbounded dependency surface from latest-version pinning | Medium | Medium | Architecture lead |
| R-015 | Provider renamed after a completed run is referenced in historical UI | Low | Low | Architecture lead |
| R-016 | Worker-thread lifecycle & cooperative-cancellation correctness (the new concurrency model) | Medium | High | Concurrency lead |

## 4. Risk Details

### R-001 — qasync event-loop stability on Python 3.13

> **CLOSED / SUPERSEDED by D-R-01 (2026-06-04); replaced by R-016 (SPEC-069).** This risk no longer applies: the application no longer uses `asyncio` or `qasync`. Concurrency is a synchronous backend on a Qt `QThreadPool` `TaskRunner` (`16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`). The residual concurrency risk is now worker-thread lifecycle + cooperative-cancellation correctness (a force-quit abandoning a worker, a missed `raise_if_cancelled()` checkpoint, a stuck blocking read), covered by the concurrency test matrix; track that as the replacement risk. The original description is retained below for the record.

**Description (historical).** The application runs a single asyncio loop on the Qt main thread through qasync. qasync is a small community-maintained library; the project targets an exact Python 3.13.3 interpreter. A qasync defect, an incompatibility with a 3.13 asyncio change, or a regression in a future qasync release could destabilize the loop — manifesting as dropped tasks, unhandled-exception leakage, slot/coroutine scheduling glitches, or a hung shutdown.

**Probability:** Medium. **Impact:** High — the loop is the spine of every run; instability is non-local.

**Mitigation plan.**
- Pin qasync to a known-good release and treat upgrades as a deliberate, tested change rather than an automatic latest-version bump.
- Install the loop exactly once in the composition root before any worker starts, and register a loop exception handler that routes programmer errors to the terminal hook and redacts the rest.
- Maintain a dedicated suite of concurrency tests — including a property-based stop/pause state machine — exercised on every CI run against the pinned interpreter.
- Keep a thin internal seam around loop installation so an alternative loop strategy can be substituted without touching call sites.
- Run a smoke test that performs a full start/run/pause/stop/shutdown cycle headlessly in CI.

**Owner:** Concurrency lead.

**Trigger conditions.** Any CI concurrency-test failure not attributable to test code; a hung-shutdown report; an unhandled-exception leak from the loop; a qasync or CPython 3.13 patch release that changes asyncio scheduling semantics.

---

### R-002 — Unsigned binary distribution UX (Gatekeeper / SmartScreen)

**Description.** The application ships unsigned: macOS builds are ad-hoc signed only (no Developer ID, no notarization) and Windows is distributed as a portable `.zip` with no installer and no Authenticode certificate (decisions D-028, D-029). First-run users encounter macOS Gatekeeper blocks and Windows SmartScreen warnings, and antivirus engines may raise false positives on the PyInstaller-bundled executable. This is a UX and trust risk, not a code defect.

**Probability:** High — unsigned binaries reliably trigger these prompts. **Impact:** Medium — users can proceed, but adoption and trust suffer.

**Mitigation plan.**
- Document the exact first-run unblock steps per OS in the distribution material and the README install templates, including screenshots of the prompts.
- Publish a `SHA256SUMS` checksum file alongside every release so users can verify a download is intact independently of OS signing. Per the release-integrity decision (D-R-11b), checksums are the **sole** release-side integrity record; the binaries are unsigned and there is no GPG or Ed25519 signing. Checksums published on the HTTPS GitHub Releases page provide integrity (corruption detection), with the Releases page itself as the trust anchor; cryptographic artifact authenticity is a deferred option re-evaluated only at a sustained user-base milestone (see the certificate note below).
- Track antivirus false-positive reports; submit reclassification requests when they exceed a defined threshold.
- Keep code-signing certificates as an explicitly deferred option, to be re-evaluated only at a sustained user-base milestone.

**Owner:** Release engineer.

**Trigger conditions.** More than a defined number of antivirus false positives per month; repeated user reports of being unable to launch the app; a platform change that hardens unsigned-binary execution.

---

### R-003 — GitHub Actions free-tier CI minute exhaustion (macOS arm64)

**Description.** CI runs on the GitHub Actions free tier. macOS arm64 runners carry a 10× minute multiplier. The PR-gate matrix spans multiple operating systems. Sustained development can exhaust the monthly minute allowance, blocking PR validation and releases. (Per DD-36 there is no scheduled / nightly workflow; the only CI triggers are PRs and release-tag pushes.)

**Probability:** Medium. **Impact:** Medium — CI stalls slow delivery but cause no data loss.

**Mitigation plan.**
- Order the PR gate cheapest-first (lint, format, type-check, architecture tests) so most failures abort before expensive matrix legs.
- Cache the resolved dependency set keyed on the lockfile.
- Use `concurrency.cancel-in-progress` so superseded PR pushes do not consume minutes.
- Keep slow tests out of the PR-gate suite entirely (they run locally on demand), so the PR gate stays lean.
- Monitor monthly macOS arm64 consumption; if it crosses a defined threshold, drop the arm64 leg from the PR matrix and rely on the release-tag build for arm64 artifact coverage.

**Owner:** Release engineer.

**Trigger conditions.** Monthly macOS arm64 consumption above the defined threshold; a CI run failing to start because the minute quota is exhausted.

---

### R-004 — Adaptive-timeout mis-tuning stalls or wastes runs

**Description.** The entire time-budget model is an adaptive per-(provider, model, **role**) timeout — DD-34 extended the model to **per-role** state buckets, so two parallel escalation ladders are now in play. The role=INFERENCE ladder is parameterised by `benchmark.min_timeout_seconds`, `benchmark.max_timeout_seconds`, `benchmark.retry_count`, and `benchmark.consecutive_max_timeouts_to_exclude` (decision D-023); the role=JUDGE ladder is parameterised by `eval.judge_timeout_min_seconds`, `eval.judge_timeout_max_seconds`, `eval.judge_timeout_escalation_steps`, and `eval.judge_timeout_consecutive_threshold`. There is no global per-phase wall-clock cap. If either ladder's parameters are mis-tuned, a slow-but-healthy model can be excluded prematurely **at that role**, or a genuinely stuck request can consume the full maximum timeout repeatedly before exclusion — stalling or wasting long runs. Embedding uses a separate fixed budget (`eval.embedding_timeout_seconds`) — mis-tuning that value can produce excess per-task cosine degradation but never excludes the embedding model.

**Probability:** Medium. **Impact:** Medium — wasted run time, missing results for a model at one role, or a judge model excluded mid-run while still healthy at the inference role (or vice versa).

**Mitigation plan.**
- Specify both ladders' escalation algorithms, default minimum/maximum bounds, retry/escalation counts, and exclusion thresholds explicitly in the adaptive-timeout document (`11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md`) with the rationale for each default.
- Make every per-role timeout parameter a registered, user-exposed setting so operators can tune for their hardware without a rebuild — surfaced in **Settings → General → Inference (§4.1)** and **Settings → General → Judge timeouts and embedding timeout (§4.3a)**.
- Log every timeout escalation, retry, and exclusion decision **with the role** to the per-run log so post-run analysis can show whether tuning was correct per role.
- Surface an in-progress indication when a test model is approaching its role=INFERENCE exclusion threshold so the user is not surprised by missing results; emit `_judge_model_excluded` once when the role=JUDGE bucket crosses its threshold and render the Event Log warning line.
- Cover both ladders' escalation and exclusion logic with deterministic unit tests using a fake clock.
- The per-role independence rule — a role=JUDGE exclusion does NOT affect role=INFERENCE for the same `(provider, model)` and vice versa — is the primary safety net against cross-contamination of state.

**Owner:** Concurrency lead.

**Trigger conditions.** Post-run logs showing healthy models excluded at either role; user reports of runs stalling on a test model OR a judge model; repeated maximum-timeout retries before exclusion at either role; user reports of FAILED_JUDGE_TIMEOUT swamping a run.

---

### R-005 — Local LLM memory pressure when many models load

**Description.** Benchmarking against a local runtime (Ollama, LM Studio, llama.cpp) loads models into host memory or VRAM. A run that sweeps many models, or large models, can exceed available memory — causing the runtime to thrash, swap, fail to load, or be killed by the OS. The application does not control the host's memory headroom.

**Probability:** Medium. **Impact:** High — the run produces wrong or missing results, or the host becomes unresponsive.

**Mitigation plan.**
- Benchmark models sequentially per provider rather than concurrently loading the full model set.
- Translate runtime out-of-memory and load-failure responses into the application error taxonomy at the provider-adapter boundary, surfaced as a per-result-row error rather than a silent skip.
- Document the recommended practice of relying on the runtime's own model-unload behaviour between models, and document host memory expectations for the user.
- Treat a model-load failure as a transient-then-permanent condition: retry within the timeout budget, then exclude the model and continue the run.
- Record the failure reason in the result row so the user can distinguish a memory failure from a content failure.

**Owner:** Provider-integration lead.

**Trigger conditions.** Runtime load-failure or out-of-memory responses during a run; user reports of host unresponsiveness during benchmarking.

---

### R-006 — Long-running batched pipeline holding partial results

**Description.** The benchmark pipeline executes in five batched phases and a long sweep can run for hours. Partial results accumulate across the run. If the pipeline holds intermediate results only in memory, a crash, an OS sleep, or an accidental quit late in a run loses substantial work.

**Probability:** Medium. **Impact:** High — hours of compute and provider cost lost.

**Mitigation plan.**
- Persist each task result to SQLite as soon as the task completes — never buffer a whole phase in memory before writing.
- On Pause and auto-pause, let the in-flight task finish and be saved, then halt before the next task with fully resumable application state (decision D-019).
- Persist run status as `INCOMPLETE` / `COMPLETED` / `FAILED` / `STOPPED`; treat `RUNNING` and `PAUSED` as in-memory-only derived states (decision D-015) so an interrupted run is unambiguously resumable.
- Run a crash-recovery sweep at startup that marks queued or running runs as interrupted and makes them available to resume.
- Cover resume-from-partial as an explicit end-to-end test scenario.

**Owner:** Concurrency lead.

**Trigger conditions.** A crash during a long run; a resumed run showing duplicated or missing tasks; partial results not appearing in the result table mid-run.

---

### R-007 — SQLite WAL corruption and crash recovery

**Description.** Persistence uses a single SQLite database in WAL mode with a two-connection model (one writer, one reader). A hard crash, a power loss, a non-local-disk database location (NFS/SMB), or an incorrect file operation on the WAL set (for example a naive file copy) can corrupt the database or its WAL files. Windows WAL file-locking adds platform-specific risk.

**Probability:** Low. **Impact:** High — corruption can render historical runs unreadable.

**Mitigation plan.**
- Use `BEGIN IMMEDIATE` for all writes, `synchronous=NORMAL`, a busy timeout, and a single locked writer connection.
- Place the database via the platform data directory and document the local-disk requirement; detect and warn if the database path appears to be on a network share.
- Run the crash-recovery sweep before the writer accepts work at startup.
- Checkpoint and truncate the WAL before close; never copy a live WAL database file directly — use the SQLite backup or `VACUUM INTO` APIs for snapshots.
- Treat a schema-version mismatch as a clear, hard startup error rather than an automatic migration (decision D-017).

**Owner:** Persistence lead.

**Trigger conditions.** A SQLite corruption or malformed-database error at startup; a failed crash-recovery sweep; user reports of lost run history.

---

### R-008 — Provider SDK breaking changes under a latest-versions policy

**Description.** The dependency policy uses the latest stable version of every dependency at the time of work (decision D-024). The OpenAI, Anthropic, and Gemini SDKs evolve rapidly, occasionally with breaking changes to streaming shapes, usage reporting, or exception types. A latest-version bump can break a provider adapter without warning.

**Probability:** High — provider SDKs change often. **Impact:** Medium — one provider degrades; others keep working.

**Mitigation plan.**
- Confine each provider SDK to its owning provider module's internals; the rest of the application sees only the application's own `LLMClient` protocol and error taxonomy.
- Wrap every provider/library-specific exception into the application error taxonomy at the first point it can occur (decision D-026).
- Keep an integration-test layer per provider — the **provider wire stub** of `16_Engineering_Standards/07_TESTING_STANDARD.md` §7a (`pytest-httpserver`; real adapter + real SDK against canned local HTTP responses) — that exercises the streaming, usage, and error paths deterministically offline, so a breaking SDK change fails CI rather than reaching users. This stub also serves as the `LLMClient` contract-suite real leg (§6a).
- Disable all SDK-internal retry logic so retry behaviour is owned solely by the application's retry controller and is not silently changed by an SDK update.
- Record the exact provider SDK versions in the consolidated version table and bump them deliberately, with the integration suite as the gate.

**Owner:** Provider-integration lead.

**Trigger conditions.** A provider integration test failing after a dependency bump; a provider streaming or usage field disappearing; a new SDK exception type not mapped in the taxonomy.

---

### R-009 — Embedding-model availability for Graded Benchmark

**Description.** Graded Benchmark combines keyword, cosine-similarity, and judge phases. The cosine phase requires an embedding model to produce the numeric similarity stored in the database. If the configured embedding model is unavailable — not pulled locally, unsupported by the provider, or removed from a provider's API — the cosine phase cannot run and Graded Benchmark is degraded.

**Probability:** Medium. **Impact:** Medium — grading degrades to the available phases.

**Mitigation plan.**
- Probe embedding-model availability before a Graded Benchmark run starts and surface a clear, actionable error if the model is missing, naming the model and the provider.
- Define the verdict cascade so that, when the cosine phase cannot run, the run degrades predictably to the enabled phases rather than failing silently (decision D-012).
- Document the embedding-model prerequisite for Graded Benchmark in the user-facing material and the settings UI.
- Validate the configured embedding-model setting at registration time.
- Cover the missing-embedding-model path as an explicit edge-case test.

**Owner:** Provider-integration lead.

**Trigger conditions.** A Graded Benchmark run starting with no reachable embedding model; cosine results absent for tasks expected to have them; a provider deprecating an embedding endpoint.

---

### R-010 — Large result sets in tables and charts

**Description.** A benchmark sweep over many tasks, models, and providers can produce very large result sets. Rendering 100k or more rows in the result table, or aggregating them for the analytics charts, can exhaust memory or freeze the UI thread.

**Probability:** Medium. **Impact:** Medium — degraded responsiveness; recoverable.

**Mitigation plan.**
- Back the result table with a model/view architecture over the database; push filtering and sorting into SQL rather than holding all rows in a Python list.
- Use incremental row fetching so the table loads visible rows on demand instead of materializing the whole set.
- Re-aggregate chart data in the backend and push a versioned, debounced frame to the chart widgets; charts update data in place rather than rebuilding.
- Persist per-run table filters, column visibility, and column order (decision D-010) so a large run opens in a usable, pre-filtered state.
- Cover the large-result-set rendering paths with integration tests that exercise a representative fixture dataset, asserting the UI remains responsive (no synchronous database or aggregation work on the GUI loop) and that chart aggregation runs in an executor worker.

**Owner:** UI lead.

**Trigger conditions.** UI freezes when opening a large run; memory growth proportional to result-set size; chart aggregation visibly stalling the GUI loop.

---

### R-011 — Cross-platform packaging drift (PyInstaller)

**Description.** The application is packaged with PyInstaller `--onedir` separately for macOS arm64 (Apple-silicon only — Intel x86_64 is no longer built, DD-69), Windows, and Linux. A hidden import, a missing data file, a Qt plugin omission, or a platform-specific bundling quirk can produce a build that passes CI tests (run from source) but fails to launch from the packaged artifact on one platform.

**Probability:** Medium. **Impact:** Medium — a broken release for one platform.

**Mitigation plan.**
- Maintain one PyInstaller spec file per OS with the same entry point and explicit hidden-import and data-file declarations.
- Add a post-build smoke test in the release workflow that launches the packaged artifact and exercises a minimal start/shutdown cycle on each OS.
- Pin PyInstaller and the Qt binding to known-good versions and bump them deliberately.
- Use reproducible-build settings so a build is tamper-evident and comparable across runs.
- Exclude test-only packages from the bundle to reduce surface area and size.

**Owner:** Release engineer.

**Trigger conditions.** A packaged artifact failing its post-build smoke test; a user report of a missing module or plugin at launch on one OS only; a PyInstaller or Qt-binding version bump.

---

### R-012 — Cross-thread signal marshalling defects

**Description.** Cross-widget state lives in scoped reactive stores and one-shot domain events travel on a typed event bus; the adapter layer marshals signals from background work onto the Qt main thread (decision D-021). A missed marshalling step — touching a widget from a worker, or delivering a store update on the wrong thread — produces intermittent crashes, repaint glitches, or silent UI staleness that is hard to reproduce.

**Probability:** Medium. **Impact:** High — intermittent, hard-to-diagnose defects.

**Mitigation plan.**
- Centralize the cross-thread boundary in the adapter layer; never let backend code touch a widget directly.
- Marshal worker-to-UI updates through the documented delivery mechanism and coalesce high-frequency updates so the UI thread is not flooded.
- Add architecture tests asserting that widget code never imports concurrency or provider internals and that subscriptions are owned by their widget.
- Run a Qt-warning parity rig in tests that fails any test emitting a Qt or binding warning, catching wrong-thread access early.
- Cover the pause/stop and live-update paths with widget tests driven on the real event loop.

**Owner:** Architecture lead.

**Trigger conditions.** Intermittent UI crashes under load; a test emitting a Qt threading warning; stores observed updating from a non-main thread.

---

### R-013 — Secret leakage through one of the two redaction surfaces being bypassed

**Description.** The application handles provider API keys and base URLs. The redaction module is applied at two surfaces (`10_Domain_and_Data/08_REDACTION_PATTERNS.md` §1, DD-31, D-R-17): app-log records (`app.*` structlog processor) and provider SDK error-message wrapping at the adapter boundary. If one of those two surfaces fails to apply redaction — a missing `redact(text)` wrap at a new provider adapter, or a structlog processor that is silently disabled — credentials can leak into `app.log` or into an `AppError.message` that ends up on a user-shared surface.

**Probability:** Low. **Impact:** High — leaked credentials in shareable artifacts.

**Mitigation plan.**
- Enforce by architecture test that every provider adapter wraps every SDK exception path through `redact(text)` before constructing `AppError`.
- Enforce by architecture test that the `app.*` log namespace has the `redact_for_log` structlog processor attached at composition time.
- Fuzz the redaction module with property-based tests asserting no denylist pattern survives the adapter wrap or the structlog processor.
- Keep the denylist and never-log key set in one place so additions are reviewed centrally.
- Treat user-authored prompts, user-machine model responses, the run-log panel/file, CSV/Markdown exports, the Run Analysis tab, and clipboard content as **out of scope** for this risk — the threat model accepts that the user reads and shares their own data on their own machine (`12_Quality_and_NFRs/02_SECURITY_MODEL.md` §1, DD-31).

**Owner:** Architecture lead.

**Trigger conditions.** A secret pattern found in `app.log`; a new provider adapter added without an SDK exception-wrap test; a redaction fuzz test failure.

---

### R-014 — Unbounded dependency surface from latest-version pinning

**Description.** A CVE in a transitive dependency is only caught by the release-tag `uv run pip-audit` gate (SPEC-063), not at PR time (no PR-gate or scheduled scan — DD-36), so a vulnerable dependency can sit in `main` until the next release attempt. This late-discovery window is an accepted cost of the no-background-jobs + implementation-time-currency policy. Decision D-024 keeps every dependency at its latest stable version. While this avoids stale dependencies, it widens the window for transitive breakage, new CVEs, and license drift. A latest-version bump of a transitive dependency can break a build or introduce a non-approved license.

**Probability:** Medium. **Impact:** Medium — a delayed milestone or an unplanned remediation.

**Mitigation plan.**
- Commit the resolved lockfile so every build is reproducible even though the policy is latest-version.
- Run a CVE scan against the exported dependency set as a manual / local maintainer task (or as a step in the PR-gate pipeline); there is no nightly workflow (DD-36).
- Maintain the consolidated version table as the single record of intended versions and bump it deliberately, not silently.
- Keep an approved-license list and check new and bumped dependencies against it.
- Treat every dependency upgrade as a change gated by the full CI suite, including architecture and integration tests.

**Owner:** Architecture lead.

**Trigger conditions.** A CVE scan flagging a dependency; a build failing after a transitive bump; a dependency arriving with a non-approved license.

---

### R-015 — Provider renamed after a completed run is referenced in historical UI

**Description.** Per DD-33 (`08_Cross_Cutting/08-F_spec_issues_log.md`), the user enters a unique provider `name` and the data layer auto-generates an internal `provider_id` (UUID4). Historical run rows snapshot the `name` at run start (`BenchmarkRun.judge_provider_name`, `benchmark_run_providers.name`, `BenchmarkResult.provider_name`); the FK linkage column `provider_id` stays stable across a later rename. The risk is a defect in the snapshot-vs-live rendering rule (`11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md` §1.1): if a historical UI surface accidentally re-resolves the current `name` from the `ProviderRegistry` instead of reading the snapshot field on the run-data row, a user renaming a provider after the run completes would see the run's historical label silently rewrite — a quiet correctness failure rather than a crash.

**Probability:** Low — the snapshot/registry boundary is named and tested. **Impact:** Low — the user notices a quiet relabel and the data on disk is unaffected; correcting the affected surface is a one-line read-from-snapshot fix.

**Mitigation plan.**
- Tag every UI surface that renders a provider name as either "live" (Settings provider table, in-flight Progress widget, inference-test panel) or "historical" (Resume widget run list, Result widget tabs, exports, run-log file) in the widget's `implementation_structure.md`.
- Add an architecture test that any read of a provider's display name from inside a historical-surface controller must come from a run-snapshot field (`BenchmarkRun.judge_provider_name`, `BenchmarkRun.embedding_provider_name`, `BenchmarkRun.embedding_model_name`, `BenchmarkResult.provider_name`, `benchmark_run_providers.name`) and never from `ProviderRegistry` / `ProvidersStore`.
- Cover the rename-after-run scenario with an end-to-end test: create a `GRADED` run, complete it, rename the test provider in Settings, reopen the run, and assert the snapshot name is still shown.
- Document the rule in DD-33's "Snapshot rendering rule" paragraph (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §6.7 `BenchmarkRun`) so a reviewer notices the violation in code review.

**Owner:** Architecture lead.

**Trigger conditions.** A widget test asserting a historical provider name after a rename observes the new name instead of the snapshot; a code review surfaces a `ProviderRegistry` read inside a historical-surface controller.

### R-016 — Worker-thread lifecycle and cooperative-cancellation correctness

**Description.** The replacement for the retired R-001 (`SPEC-069`). The application's concurrency is a synchronous Qt-free backend driven by a `QThreadPool` `TaskRunner` and a single dedicated dispatcher thread, with a two-level `CancellationToken` (DD-38, DD-39, DD-40, `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`). The residual concurrency risk is no longer event-loop stability but the correctness of that model under stress: a force-quit that abandons an in-flight worker (`os._exit`, SPEC-034), a missing `raise_if_cancelled()` checkpoint that lets a unit ignore a pause/stop, a provider call that wedges in a blocking read despite the finite-deadline invariant (SPEC-015), the hard-cancel hook failing to close a stream within `provider.hard_cancel_max_ms` (DD-39), or a gate left held by a dead activity (mitigated by the lease-owned watchdog, DD-50).

**Probability:** Medium — concurrency defects are easy to introduce and hard to reproduce. **Impact:** High — a wedged dispatcher or an abandoned worker can stall a run or, worst case, require the bounded force-quit.

**Mitigation plan.**
- The concurrency test matrix (`16_Engineering_Standards/07_TESTING_STANDARD.md`, `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` §11) exercises pause/stop/shutdown, the dispatcher `Future`-handoff, hard-cancel bounds, and gate lease/watchdog behaviour.
- The architecture-tested finite-deadline invariant (SPEC-015) guarantees no provider call path can block forever.
- The bounded force-quit (SPEC-034) guarantees the application always exits even if a worker is wedged; the next-launch recovery sweep repairs indeterminate rows.
- Architecture tests forbid raw `threading.Thread` for work units and require the single `CancellationToken` model (no per-feature cancellation booleans).

**Owner:** Concurrency lead.

**Trigger conditions.** A concurrency test flakes or deadlocks; a force-quit is observed in normal use (it should be a genuine last resort); a run fails to pause/stop within the documented latency bounds.

---

## 5. Review Cadence

- Review the full register at the start of every implementation phase.
- Update a risk entry whenever a mitigation lands, a trigger fires, or probability/impact changes.
- When a risk is fully mitigated or no longer applicable, set its status to `Retired` and keep its identifier.
- A fired trigger that cannot be mitigated within the phase is escalated to the human reviewer and, if it requires an architectural choice, recorded as a proposed ADR in [03_PROPOSED_ADRS.md](03_PROPOSED_ADRS.md).
