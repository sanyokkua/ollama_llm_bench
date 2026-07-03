# Phase Breakdown

Thirteen phases, strictly ordered by the dependency DAG in
`docs/spec/14_Process_and_Traceability/01_MODULE_INVENTORY.md` §3 (after vendoring per
decision D2 — paths below assume the spec lives at `docs/spec/` in this repo; adjust if you
keep it external). Each phase lists: what it builds, which spec files govern it, which of the
62 inventory modules it covers, and its definition-of-done. Phases 2–7 are backend-only
(Qt-free, can be built and fully unit-tested with zero UI). Phases 8–10 require Phases 2–7
complete. Do not start a phase whose "Depends on" list isn't done — that's the #1 way to lose
requirements (building a widget against a service contract that later changes).

A phase is not "one story" — see `02_STORY_PROCESS.md` for how each phase splits into S/M/L
stories. The numbers in "~Stories" are an estimate to help scope a session, not a hard count.

---

## Phase 0 — Governance and scaffold (no application code)

**Goal:** repo is ready to receive the rewrite; nothing about the old app remains except what
decision D5 says to keep.

**Spec inputs:** `docs/spec/16_Engineering_Standards/01_PROJECT_STRUCTURE.md`,
`02_TOOLCHAIN.md`, `08_CICD_AND_PACKAGING.md`; `14_Process_and_Traceability/02_STORY_FORMAT.md`,
`03_TRACEABILITY.md`, `04_ADR_FORMAT.md`.

**Work:**
1. Vendor the spec (D2): copy `App_Specification_Ollama_Bench_Final/` → `docs/spec/`.
2. Delete `src/ollama_llm_bench/{backend,ui}/*` contents and `tests/{unit,integration,widget}/*`
   per D5, keeping empty `src/ollama_llm_bench/__init__.py` and `tests/__init__.py` as anchors.
3. Rewrite `pyproject.toml`: `uv_build` backend, full dependency table from `02_TOOLCHAIN.md`
   (runtime: PySide6 6.8+, msgspec, psygnal==0.15.*, structlog, icontract, ruamel.yaml,
   platformdirs, click, typing-extensions; dev: pytest-qt, pytest-archon, import-linter,
   pytest-httpserver, hypothesis, icontract-hypothesis, freezegun, pip-audit; build:
   pyinstaller), ruff config (line-length 100, the rule sets listed in §10 of the toolchain
   doc), mypy strict config.
4. Add `justfile` mirroring every CI step (`setup`, `lint`, `format`, `typecheck`,
   `import-check`, `arch-test`, `test`, `coverage-layers`, `trace`, `trace-check`, `check`).
5. Add `import-linter` config (4 contracts: core Qt-free, provider-adapter independence,
   compose.py-only-concrete-wiring, UI-imports-only-Protocols) per
   `01_PROJECT_STRUCTURE.md` §9.
6. Scaffold the full `src/ollama_llm_bench/` tree from `01_PROJECT_STRUCTURE.md`'s verbatim
   tree as **empty packages** (`__init__.py` with docstring only) — every `backend/*`,
   `adapters/*`, `ui/*` directory that Phase 2+ will fill in. This gives import-linter and
   pytest-archon something to validate from day one.
7. Scaffold `tests/{architecture,unit,integration,e2e,perf,typing_negative}/`.
8. Set up `docs/stories/`, `docs/adr/` (+ `docs/adr/README.md` index), `scripts/trace.py`,
   `scripts/validate_traceability.py` (per `03_TRACEABILITY.md` §3-4).
9. Ratify the 3 proposed ADRs (D4) as `docs/adr/0001..0003`.
10. Rewrite `.claude/CLAUDE.md` + the affected rule files per decision D3.
11. Replace `docs/*.md` (old architecture docs) with a stub `docs/architecture.md` pointing at
    `docs/spec/` as the authority until Phase 12 writes the real one.
12. Reset `CHANGELOG.md` `[Unreleased]` section; note the rewrite as a `Breaking` entry.
13. New GitHub Actions workflows per `08_CICD_AND_PACKAGING.md` (PR-gate: lint→typecheck→test;
    release-tag: + audit→build→release). Two triggers only — no schedule/dispatch (DD-36).

**Definition of done:** `uv sync` succeeds; `just check` runs (even though it has nothing to
lint yet beyond the empty scaffold) and is green; `import-linter` config validates against the
empty tree; CI workflow YAML is valid; `docs/adr/` has 3 accepted ADRs; `.claude/CLAUDE.md`
reflects the new stack with no contradictions left.

---

## Phase 1 — Domain, errors, events, infra (the Qt-free foundation)

**Depends on:** Phase 0.

**Spec inputs:** `docs/spec/10_Domain_and_Data/01_DOMAIN_MODEL.md`, `02_DTOS_AND_ENUMS.md`,
`08_REDACTION_PATTERNS.md`; `08_Cross_Cutting/08-E_interfaces_contracts.md` §5-6, §22 (Clock,
Subscription, EventBus, ApplicationContext); `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md`;
`16_Engineering_Standards/03_CODING_STANDARDS.md`, `05_ERROR_HANDLING_STANDARD.md`,
`06_LOGGING_STANDARD.md`; `08_Cross_Cutting/08-Q_event_payload_schemas.md`.

**Modules:** `backend/domain/`, `backend/errors/`, `backend/events/`, `backend/infra/`,
`backend/platform/`, `backend/concurrency/`, `backend/retry/` (7 modules).

**Work:** every `msgspec.Struct` and `StrEnum` in `02_DTOS_AND_ENUMS.md` (23 enums + every
domain record); the 4-category/20+-leaf exception hierarchy + `redact`/`redact_for_log`; the
`EventBus` Protocol + all ~34 event payload structs from `08-Q`; `Clock` Protocol +
`configure_logging` (structlog, two-namespace `run.*`/`app.*` split per `06_LOGGING_STANDARD.md`);
`PlatformDetector`; `CancellationToken` (two-level, DD-39) + `TaskRunner` Protocol port;
retry-policy primitives (backoff formula, per-category tables from `18_RETRY_POLICY.md`).

**Definition of done:** 100% Qt-free (import-linter contract passes); every Struct verified
`frozen=True, kw_only=True, gc=False` by an architecture test; ≥90% branch coverage (backend
floor); `icontract` on every public `api.py` function; no `asyncio`/`anyio` import anywhere
(architecture test, D-R-01).

---

## Phase 2 — Persistence (6 stores + schema)

**Depends on:** Phase 1.

**Spec inputs:** `docs/spec/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` (full DDL — the
authoritative source); `08_Cross_Cutting/08-O_persistence_schema.md` (bridging clarifications);
`08_Cross_Cutting/08-E_interfaces_contracts.md` §7 (6 Store Protocols);
`12_Quality_and_NFRs/06_DATA_INTEGRITY.md`; `04_ERROR_RECOVERY.md`.

**Modules:** `backend/persistence/{runs,tasks,results,providers,model_capabilities,app_settings}/`
(6 modules).

**Work:** all 15 tables + 15 indexes + FKs + pragmas exactly as specified; single-writer
discipline (DD-41, one connection + one `threading.Lock`, `BEGIN IMMEDIATE`); schema-version
check + additive-only evolution (DD-53, **no migration framework**); crash-recovery sweep
(`recover_in_flight_results`); seed data (3 bundled providers, `app_meta`).

**Definition of done:** every store has integration tests against a `tmp_path` SQLite file
(never in-memory); a property/Hypothesis test proves the additive-only schema-evolution rule;
an explicit test proves the "run header write comes last" durability ordering invariant
(`12_Quality_and_NFRs/06_DATA_INTEGRITY.md` §2); crash-recovery sweep has a dedicated test per
each of the 4 non-terminal `ResultStatus` values it must reset.

---

## Phase 3 — Settings, reactive stores, readiness

**Depends on:** Phase 2.

**Spec inputs:** `docs/spec/08_Cross_Cutting/08-C_settings_hierarchy.md`,
`08-G_feature_flags.md` (every settings key); `11_Services_and_Algorithms/09_READINESS_PROBE.md`;
`08_Cross_Cutting/08-E_interfaces_contracts.md` §8, §13 (SettingsService, RunSnapshotBuilder,
InferenceActivityStore).

**Modules:** `backend/settings/`, `backend/stores/` (incl. `inference_activity/`),
`backend/readiness/` (3 modules — listed as 4 in the inventory's stratum count but
`inference_activity` is a sub-package of `stores`).

**Work:** three-layer settings resolution (snapshot ▶ user-saved ▶ default); the full
per-run-overridable key registry from `08-G`; `InferenceActivityStore` single-inference gate
(DD-50 lease-owned `try_acquire`/`release`, watchdog auto-release per activity); readiness
aggregation algorithm (READY/DEGRADED/NOT_READY/CHECKING, embedding handshake-only per DD-48).

**Definition of done:** a property test proves resolution-order correctness across all
registry keys; a concurrency test proves the gate is exclusive under concurrent `try_acquire`;
readiness aggregation has a table-driven test covering every `ProviderTestStatus` × overall
combination from `09_READINESS_PROBE.md` §6.5.

---

## Phase 4 — Provider adapters

**Depends on:** Phase 1 (domain/errors/events only — does not need persistence).

**Spec inputs:** `docs/spec/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md`,
`03_PROVIDER_REGISTRY.md`; `16_Engineering_Standards/07_TESTING_STANDARD.md` §7a (provider
wire-stub via `pytest-httpserver`).

**Modules:** `backend/provider_registry/`, `backend/provider_openai_compatible/`,
`backend/provider_anthropic/`, `backend/provider_gemini/` (4 modules).

**Work:** the `LLMClient` Protocol (`list_models`, `probe_health`, `test_inference`, `chat`,
`chat_stream` as THE execution surface per DD-51, `embed`, `supports_*`); TTFT measurement;
token-usage capture with the char/4 estimation fallback (DD-60); exception translation to the
Phase-1 error taxonomy; finite-deadline invariant (SPEC-015) on every call path; the
`ProviderRegistry` build-client algorithm incl. Azure four-field validation and atomic
commit-or-rollback `reload()`.

**Definition of done:** offline CI — every provider's `chat_stream`/`embed`/`probe_health`
tested against a local `pytest-httpserver` instance with canned SSE/error payloads (401, 404,
429, 500, malformed stream, mid-stream close), never a live model; a shared contract-test
suite runs against both the real adapter (vs. stub) and each adapter's `testing.py` fake to
prove fidelity (`07_TESTING_STANDARD.md` §6a).

---

## Phase 5 — Pipeline-support services

**Depends on:** Phases 1, 3, 4.

**Spec inputs:** `docs/spec/11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md`,
`08_CIRCUIT_BREAKER.md`, `10_MODE_VISIBILITY_POLICY.md`, `11_RUN_DRIFT_DETECTOR.md`;
`08_Cross_Cutting/08-B_benchmark_state_machine.md` §6-7.

**Modules:** `backend/adaptive_timeout/`, `backend/circuit_breaker/`, `backend/mode_visibility/`,
`backend/run_drift/`, `backend/model_helpers/` (5 modules).

**Work:** adaptive-timeout escalation ladder (verbatim formula in `07_ADAPTIVE_TIMEOUT.md`
§6.3) with independent `INFERENCE`/`JUDGE`/`RUN_ANALYSIS` buckets (DD-34, DD-65); circuit
breaker CLOSED/TRIPPED/PROBING state machine with the exact failure-counting rule (DD-64,
warmup counts, `FAILED_TIMEOUT` does not); mode-visibility policy as a pure total 3×10 lookup
table; run-drift detector's 4 checks (DD-57, environment-availability only).

**Definition of done:** the adaptive-timeout state machine and circuit-breaker state machine
each get a `RuleBasedStateMachine` Hypothesis test walking every legal transition; the
mode-visibility table is asserted total (every cell defined) by an architecture-style test.

---

## Phase 6 — Embedding, evaluation, benchmark pipeline (the core engine)

**Depends on:** Phases 1–5 (this is the most dependency-heavy phase — do not start early).

**Spec inputs:** `docs/spec/11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md`,
`04_EVALUATION_PIPELINE.md`, `16_CONCURRENCY_MODEL.md`;
`08_Cross_Cutting/08-P_judge_protocol.md`, `08-B_benchmark_state_machine.md` (full);
`16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`.

**Modules:** `backend/embedding/`, `backend/evaluation/`, `backend/benchmark_pipeline/`
(3 modules — the smallest module count of any phase but the largest by behavioral surface;
consider splitting into 2 Claude Code sessions: evaluation+embedding first, pipeline
orchestration second). `backend/performance_task_generator/` is deferred to Phase 7 (it
belongs to the inventory's presentation-support group, not the pipeline group, even though
it's pipeline-adjacent).

**Work:** cosine-similarity service with LRU cache; the 5-phase batched pipeline (init →
inference → keyword → cosine → judge) with provider-then-model grouping and the
fully-drain-before-next-phase rule; sanity pre-check; keyword/cosine/judge evaluators and the
final-verdict cascade table (§11 of `08-P`); the dedicated dispatcher thread (DD-38); two-level
cancellation (soft/hard, DD-39) with the outcome-derivation atomic-snapshot rule (DD-42); the
single-inference gate integration; pause/resume/stop semantics; judge model exclusion
(DD-34/DD-66 stage-preserving retry); the `emit_progress_during()` shared helper across all 4
inference-class call sites; embedding fail-fast probe (DD-48) and consecutive-failure
short-circuit (DD-70); `PerformanceTaskGenerator`'s 5×5×repeats expansion.

**Definition of done:** a concurrency test matrix exercises pause/stop/shutdown against a fake
`LLMClient` with controllable latency, proving: no partial result ever persists on hard cancel,
in-flight task always finishes+persists on soft cancel, resume always reuses the frozen
settings snapshot; the verdict-cascade table from `08-P` §11.5 is exercised as a table-driven
test (every {phases-enabled} × {force-judge} combination); the 10 state-machine invariants in
`08-B_benchmark_state_machine.md` §12 each have a named test.

---

## Phase 7 — Presentation-support & data-exchange backend modules

**Depends on:** Phases 1, 2, 6 (needs `BenchmarkResult` shape and a populated DB to serialize).

**Spec inputs:** `docs/spec/11_Services_and_Algorithms/12_YAML_FORMATTER.md`,
`13_CHART_AGGREGATORS.md`, `19_TABLE_SERIALIZATION.md`, `20_HTML_RENDERING.md`,
`21_PERFORMANCE_TASK_GENERATOR.md`, `22_RUN_ANALYSIS_SERVICE.md`, `15_LOG_FORMATTING.md`,
`14_VALIDATION_CASCADE.md`; `10_Domain_and_Data/04_YAML_TASK_FORMAT.md`, `05_EXPORT_FORMATS.md`,
`06_IMPORT_FORMATS.md`.

**Modules:** `backend/task_files/`, `backend/yaml_formatter/`, `backend/charts/`,
`backend/csv_export/`, `backend/import_export/`, `backend/html_rendering/`,
`backend/run_analysis/`, `backend/performance_task_generator/`, `backend/log_formatting/`,
`backend/log_file_writer/` (10 modules — the largest module count of any phase but each is
individually small/independent; parallelizable across multiple Claude Code sessions since they
don't depend on each other, only on Phase 1/2/6).

**Work:** comment-preserving `ruamel.yaml` formatter with canonical field order and
atomic-write; loader-tolerant vs. editor-strict task-file readers; all 12 chart aggregators
with the 5-filter pipeline, minimum-sample-size guard, and outlier handling; CSV/Markdown
table serializer (13-col Summary, 17/18/24-col Details depending on doc — reconcile against
`05_EXPORT_FORMATS.md` as authoritative, verbatim no-redaction policy); settings/provider
import-export with the preview-before-apply flow and `D-R-18` env-var-name-only validation;
HTML result-detail + log-line rendering with mandatory escaping; the consolidated
`RunAnalysisService` (one narrative field, mode-aware prompt framing, own `RUN_ANALYSIS`
adaptive-timeout bucket); `PerformanceTaskGenerator`'s 5×5×repeats deterministic expansion for
`SYNTHETIC` mode; two-stream log formatting.

**Definition of done:** YAML round-trip property test (parse→serialize→parse is identity
modulo canonical reordering); each of the 12 chart kinds has a fixture-based snapshot test;
export filename sanitization (SPEC-064 path-traversal guard) has a dedicated test; HTML
renderer has an XSS-style test asserting no `<script>`/`on*` ever escapes unescaped.

---

## Phase 8 — Adapters layer (Qt-binding glue)

**Depends on:** Phases 1–7 complete (this layer wraps everything backend exposes).

**Spec inputs:** `docs/spec/14_Process_and_Traceability/01_MODULE_INVENTORY.md` §5;
`08_Cross_Cutting/08-E_interfaces_contracts.md` §7b (the 7 per-widget Gateway Protocols),
§19-21 (WorkspaceController, NotificationService, NativePickers, Clipboard, FileSystemActions);
`16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` (TaskRunner/QRunnable wiring).

**Modules:** `adapters/qt_event_bus/`, `adapters/qt_benchmark_flow/`,
`adapters/qt_table_models/`, `adapters/qt_runnables/`, `adapters/store_qt_bridge/`,
`adapters/qt_inference_activity_bridge/`, `adapters/workspace_controller/`,
`adapters/notification_service/`, `adapters/native_pickers/`, `adapters/clipboard/`,
`adapters/file_system_actions/` (11 modules).

**Work:** Qt signal/slot bridge for the Qt-free event bus; `QRunnable` wrapper that sets a
stdlib `Future`'s result directly on the worker thread (no Qt signal in the completion path —
critical correctness point, see the dispatcher-deadlock anti-pattern in
`04_CONCURRENCY_STANDARD.md`); per-table `QAbstractTableModel` adapters (validated with
`QAbstractItemModelTester`); the 7 Gateway Protocols (`MainWindowGateway`,
`NewBenchmarkGateway`, `ResumeGateway`, `ProgressGateway`, `ResultGateway`, `SettingsGateway`,
`TaskEditorGateway`) — **these are the only things a UI controller is allowed to hold**
(D-R-06); per-OS native pickers/clipboard/file-system-actions.

**Definition of done:** every adapter is tested with `pytest-qt`; a dedicated test proves a
`QRunnable` completing while no Qt event loop is spun (the dispatcher's actual operating mode)
still resolves its `Future`; import-linter contract "UI imports no concrete backend, only
Protocols + adapters" passes.

---

## Phase 9 — UI foundation (theme + shared primitives)

**Depends on:** Phase 8 (needs `ProviderRegistry`/event-bus adapters for the dropdowns).

**Spec inputs:** `docs/spec/08_Cross_Cutting/08-D_color_palette_and_typography.md`,
`08-L_ui_standardization.md`.

**Modules:** `ui/theme/`, `ui/shared/` (incl. `provider_dropdown/`, `model_dropdown/`)
(2 modules, but `ui/theme` is unusually high-stakes — see note).

**Work:** every design token (dark + light, verbatim hex values) as typed Python objects; the
single `setStyleSheet`-calling QSS generator; theme switching (system/dark/light, live OS
tracking); platform-aware font chains; `BadgeLabel`, `HealthDot`,
`MultiCheckFilterButton`, and the two reusable dropdowns.

**Definition of done:** an architecture test (AST walker) fails the build if `setStyleSheet`
or a literal colour appears anywhere outside `ui/theme/`; a WCAG-contrast test machine-checks
the full contrast matrix from `08-D` §14 for both themes.

**Note:** because every later UI module depends on `ui/theme`, treat this phase as a hard gate
— do not let any Phase 10 widget session start before `ui/theme`'s architecture test is green.

---

## Phase 10 — UI widgets and screens

**Depends on:** Phase 9. Each widget is independent of the others (siblings, not a chain) once
its Gateway (Phase 8) and the theme (Phase 9) exist — **this phase can run as multiple parallel
Claude Code sessions**, one per widget, provided each session's prompt is scoped to exactly one
widget folder as below.

| Sub-phase | Spec folder | Module(s) | Notes |
|---|---|---|---|
| 10a | `01_Main_Window/` + `08-H_app_modes.md` | `ui/main_window/` | Build first within this phase — every other widget mounts inside it; can be a thin shell initially with the others stubbed. |
| 10b | `02_New_Benchmark_Widget/` + `mode_specifics/` | `ui/new_benchmark/` | Needs `ModeVisibilityPolicy` (Phase 5) and `RunValidator` logic. |
| 10c | `03_Resume_Benchmark_Widget/` | `ui/resume_benchmark/` | Needs `RunDriftDetector` (Phase 5). |
| 10d | `04_Progress_Widget/` | `ui/progress/` | Highest event-bus fan-out (~15 signals) — split into the 4 sub-controllers the spec already prescribes (Counters/CurrentTask/Log/Stability). |
| 10e | `05_Result_Widget/` + `tabs/` | `ui/results/` | 4 independent tab sub-features; consider one session per tab after the shell + footer exist. |
| 10f | `06_Settings_Dialog/` + `sub_dialogs/` | `ui/settings_dialog/` | Needs `ImportExportService` (Phase 7). |
| 10g | `09_Task_Editor/` | `ui/task_editor/` | Needs `YamlFormatter`/`TaskFileValidator` (Phase 7) and the validation cascade (Phase 7). |
| 10h | `07_Common_Dialogs/` | `ui/common_dialogs/` | Build alongside whichever widget first needs a given dialog (e.g. Run Summary Dialog with 10b, Resume Summary + Retry Selection with 10c, Generate Analysis with 10e); finish any stragglers last. |

**Definition of done (per widget):** `pytest-qt` test suite at ≥60% branch coverage (widget
floor) hitting every state in the widget's `state_machine.md`; the widget's controller depends
only on its Gateway Protocol (architecture test); every edge case in `08-I` tagged to that
screen in `08-R_screen_index_and_traceability.md` §3 has a passing test.

---

## Phase 11 — Composition root and entry point

**Depends on:** Phases 1–10 all complete (this wires literally everything).

**Spec inputs:** `docs/spec/14_Process_and_Traceability/01_MODULE_INVENTORY.md` §7;
`08_Cross_Cutting/08-M_app_lifecycle.md`.

**Modules:** `compose.py`, `__main__.py`.

**Work:** the 11-step launch sequence verbatim (platform detect → logging → data dir → DB
open/schema-check → seed → QApplication → composition root build → theme → main window show →
deferred readiness probe → event loop); the 7-step quit sequence (running-benchmark confirm →
unsaved-editor confirm → persist UI state → close DB → exit); single-instance advisory lock.

**Definition of done:** an `tests/e2e/` smoke test launches the real app headlessly (offscreen
Qt platform), reaches `Idle`, and shuts down cleanly; `compose.py` stays within the spec's
50-200 line budget (a longer file signals a wiring mistake, not thoroughness).

---

## Phase 12 — NFR hardening and traceability closure

**Depends on:** Phase 11.

**Spec inputs:** `docs/spec/12_Quality_and_NFRs/*` (all 8 files);
`14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md`; `08_Cross_Cutting/08-I_edge_cases.md`.

**Work:** run `just trace-check` and close every gap it reports (uncovered spec clause,
uncovered `08-I`/scoped-catalog edge case, orphan test); verify the two-surface redaction
boundary with property/fuzz tests (R-013's mitigation); verify per-layer coverage targets
(backend ≥90%, view-models/controllers ≥85%, widgets ≥60%) via `just coverage-layers`; verify
the accessibility floor's 10 release-blocking requirements; verify resource-limit numbers
(log rotation/pruning, buffer caps) against `07_RESOURCE_LIMITS.md`; write the real
`docs/architecture.md`, `docs/data-model.md`, etc. (per this project's own
`repository-documentation.md` rule, now describing the new architecture).

**Definition of done:** `just trace-check` exits 0 with zero gaps; `just check` (full CI
mirror) is green; the 16 risks in the risk register each have their stated mitigation
verifiably in place (spot-check, not exhaustive).

---

## Phase 13 — Packaging, CI release path, distribution docs

**Depends on:** Phase 12.

**Spec inputs:** `docs/spec/16_Engineering_Standards/08_CICD_AND_PACKAGING.md`;
`13_Distribution_and_Release/*` (all 7 files).

**Work:** one PyInstaller `--onedir` spec per OS (macOS arm64-only `.dmg`, Windows portable
`.zip`, Linux AppImage); SHA256SUMS generation; the release-tag GitHub Actions job
(audit → build → release); user-facing install/first-run/uninstall docs matching the spec's
distribution folder content (these can be largely copied/adapted from
`13_Distribution_and_Release/`, which is already written for end users).

**Definition of done:** a release-tag dry run (e.g. `v0.0.0-test` on a fork/branch) produces
three OS artifacts + checksums via the workflow; each artifact smoke-launches on its OS per
the release workflow's post-build check.

---

## Summary dependency graph

```
Phase 0 (scaffold)
  └─ Phase 1 (domain/errors/events/infra)
       ├─ Phase 2 (persistence) ──────────┐
       ├─ Phase 4 (providers)             │
       └─ Phase 3 (settings/stores/readiness, needs Phase 2)
                │                          │
                └──────────┬───────────────┘
                            ├─ Phase 5 (timeout/breaker/mode-visibility/drift)
                            └─ Phase 6 (embedding/evaluation/pipeline) ── needs 1,2,3,4,5
                                  └─ Phase 7 (charts/export/import/html/analysis/log)
                                        └─ Phase 8 (adapters)
                                              └─ Phase 9 (theme/shared) ── hard gate
                                                    └─ Phase 10 (widgets, parallelizable)
                                                          └─ Phase 11 (compose.py)
                                                                └─ Phase 12 (NFR/traceability)
                                                                      └─ Phase 13 (packaging)
```
