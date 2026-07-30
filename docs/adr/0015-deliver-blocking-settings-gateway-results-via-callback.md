# ADR-0015 — Return immediately from every network-bound `SettingsGateway` method and deliver its result asynchronously

**Status:** accepted
**Date:** 2026-07-30
**Deciders:** project owner, architect
**Supersedes:** —
**Relates to:** ADR-0014, D-R-01, D-R-06, SPEC-074

## Context and problem statement

`08_Cross_Cutting/08-E_interfaces_contracts.md` §7b.6 pins each `SettingsGateway` method to a
verbatim synchronous signature, four of which return a value produced by a network call:
`test_provider(...) -> InferenceTestResult`, `discover_models(...) -> tuple[ModelName, ...]`,
`probe_all() -> AppReadinessSnapshot`, and `probe_embedding() -> AppReadinessSnapshot`. Their
collaborators are marked *blocking* by their own contracts — §10 says "`list_models`,
`probe_health`, `test_inference`, `chat`, `chat_stream`, and `embed` are *blocking* — synchronous
methods invoked only on a `TaskRunner` worker thread (they perform network I/O)", and §12 says
`probe_all` is "*blocking* and **orchestrated on the dispatcher thread** (DD-38/DD-40)". §4's
threading contract then states that such a method "is only ever invoked on a `TaskRunner` worker
thread — or, for the pipeline run loop itself, on the dispatcher thread — **never directly on the
GUI thread**."

The already-shipped Settings dialog does the opposite. Three graphical-thread slots call
`test_provider` inline and consume its return value on the very next line —
`ui/settings_dialog/_internal/providers_tab/controller.py:172`
(`result = self._gateway.test_provider(config.provider_id, "")`) and
`ui/settings_dialog/_internal/sub_dialogs/provider_edit_view.py:306` and `:320`. It only appears to
work because the only implementation in the tree is the fake in `testing.py`, which returns
instantly. Wired to a real provider call it would freeze the window for the full provider timeout —
the exact row `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` §12 forbids ("A blocking call on
the GUI thread | Freezes the UI | Run all blocking work on a worker via the `TaskRunner`"), and the
rule §8 restates ("Blocking is expected on workers, forbidden on the GUI thread… it must never make
a blocking backend call directly"). ADR-0014 recorded the collision in its Neutral consequence —
"Those three clauses cannot all hold for a method that is *blocking* and returns synchronously.
Settling it needs its own ADR; STORY-110 (the Settings gateway) records the conflict and may not
move to `ready` before that ADR exists" — and deliberately left it open.

So: **when a Settings-dialog click triggers a provider call, how does the result get back to the
widget without the graphical thread blocking, and what signature does the gateway method carry?**

## Decision drivers

- The specification's own user-experience text already assumes the call is *not* instantaneous.
  `06_Settings_Dialog/description.md` §3.3 says of the row Test-connection action: "The Health Dot
  shows `TESTING` while in flight, then the final status." `sub_dialogs/provider_edit.md` §8.2 says
  "Between the moment the Run inference test button is clicked and the moment `test_inference`
  returns, the Run-button area is replaced by a **live indicator** driven by the
  `_inference_progress` event", refreshed repeatedly *during* the call. A graphical thread blocked
  inside the call can neither repaint a spinner nor process the progress events that drive it.
- `04_CONCURRENCY_STANDARD.md` §12's anti-pattern table forbids both halves of the alternative: a
  blocking call on the graphical thread, and blocking on a unit's `Future` from the graphical
  thread.
- §7b of `08-E` **already contains this pattern** for two other gateways, so adopting it makes §7b
  internally consistent rather than deviating from it. §7b.1 declares
  `def reprobe(self) -> None: """Trigger a readiness re-probe (on a worker thread) on a dot click."""`
  and §7b.5 declares
  `def regenerate_run_analysis(self, run_id: RunId) -> None: """Regenerate the consolidated run analysis (worker thread)."""`
  — both blocking operations behind a `None`-returning method.
- Two shipped implementations already realise it: `MainWindowGateway.reprobe()` (STORY-105) submits
  to the dispatcher and returns before the probe completes (asserted by STORY-105-AC-2), with the
  snapshot arriving on `_app_readiness_changed`; `ResultGateway.regenerate_run_analysis(...)`
  (STORY-108) submits to the `TaskRunner` and delivers its terminal result through an `on_complete`
  callback marshalled onto the graphical thread.
- No sanctioned way to block-wait on the graphical thread exists anywhere in the specification. No
  nested `QEventLoop`, `QFutureWatcher`, or busy-cursor wait appears in `04_CONCURRENCY_STANDARD.md`
  or elsewhere, and §11 binds the project to "stdlib + Qt only — no asyncio, no anyio".
- `08-J_event_bus_catalog.md` §6 rule 2 constrains the delivery channel: data "needed by exactly one
  widget and never crosses a widget boundary" must stay in that widget's own local signal mechanism
  rather than becoming a new bus channel. So "publish a bus event" is not automatically the right
  answer for every one of the four methods.
- The correction must be as small as possible. `docs/v3_specification/` is read-only, and only the
  methods whose collaborators are genuinely *blocking* should change shape; every fast-synchronous
  method must keep its direct return value.

## Considered options

- Option A — Every network-bound method returns immediately; its result is delivered afterwards on
  the graphical thread (by an already-catalogued bus event where one exists, otherwise by an
  `on_complete` callback), following the shipped STORY-105 / STORY-108 precedent.
- Option B — Treat a short, bounded provider probe as an explicitly blessed exception and let it
  block the graphical thread, guarded by a busy cursor and a short timeout.
- Option C — Keep the synchronous signature and implement it as a nested `QEventLoop` (or
  `QFutureWatcher`) that spins the Qt event loop while waiting on the worker's `Future`.

## Decision outcome

Chosen option: **Option A**, because it is the only option that satisfies §4's "never directly on
the GUI thread" and §12's anti-pattern table simultaneously, it is the only shape that can render
the `TESTING` dot and the in-flight live indicator the specification's own user-experience text
requires, and it is already the shipped, tested pattern for the two other §7b gateways that face the
same problem.

Concretely:

1. **Scope — exactly four methods change shape.** Re-deriving each §7b.6 method against §4's
   definitions, only these four have a *blocking* collaborator:

   | Gateway method    | Collaborator contract that makes it blocking                    | New signature                                                                                           |
   | ----------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
   | `test_provider`   | `LLMClient.test_inference` / `probe_health` — `08-E` §10        | `test_provider(provider_id, model_name, *, on_complete: Callable[[InferenceTestResult], None]) -> None` |
   | `discover_models` | `LLMClient.list_models` — `08-E` §10                            | `discover_models(provider_id, *, on_complete: Callable[[tuple[ModelName, ...]], None]) -> None`         |
   | `probe_all`       | `ReadinessService.probe_all` — `08-E` §12                       | `probe_all() -> None`                                                                                   |
   | `probe_embedding` | the embedding capability call — `06_EMBEDDING_SERVICE.md` §6.6a | `probe_embedding() -> None`                                                                             |

1. **Every other method stays fast-synchronous with its direct return value.** `list_providers`,
   `get_provider_by_name`, `replace_providers`, `get_setting`, `list_settings`, `upsert_settings`,
   `get_resolved_str`, `list_model_capabilities`, `upsert_model_capability`, `readiness_snapshot`,
   `save_all`, `reset_to_defaults`, and the six import/export methods are unchanged. `08-E` §7
   states of all six persistence stores: "**Threading.** Fast-synchronous. SQLite under WAL is fast
   enough that these reads/writes return quickly… All writes go through the single DB writer… and
   run synchronously on the calling thread"; §8's `SettingsService` is likewise "Synchronous; called
   on the main thread for UI reads and writes". This **contradicts the current docstring markers in
   `ui/settings_dialog/protocols.py`**, which label `replace_providers`, `upsert_settings`,
   `upsert_model_capability`, `save_all`, `reset_to_defaults` and all six import/export methods
   *blocking*; those markers are wrong and are corrected to *fast-synchronous* by STORY-110.

1. **Where the work is submitted.** A fan-out batch that itself submits to the pool and joins —
   `probe_all` — is submitted to the **pipeline-dispatcher thread**, never to the `TaskRunner` pool,
   because `04_CONCURRENCY_STANDARD.md` §4a names it as one of only two sanctioned dispatcher
   orchestrations and forbids a pool worker from submitting-and-waiting on the pool. This is
   STORY-105's finding for `reprobe()`, and the same reasoning applies unchanged. A leaf call —
   `test_provider`, `discover_models`, `probe_embedding` — is submitted to a `TaskRunner` worker.

1. **How the result comes back — two delivery channels, chosen by `08-J` §6.**

   - `probe_all` and `probe_embedding` need **no** callback and no new channel: `ReadinessService`
     already "emit[s] the readiness-changed signal" itself (`08-E` §12), `_app_readiness_changed`
     is already catalogued with the Settings dialog as a subscriber (`08-J` §5.7), and the Settings
     controller already subscribes to it and already discards `probe_all()`'s return value. This is
     `MainWindowGateway.reprobe()` exactly.
   - `test_provider` and `discover_models` deliver through an `on_complete` callback keyword
     argument, invoked on the graphical thread with the typed result, following
     `ResultGateway.regenerate_run_analysis`. A new bus channel is **not** added: `08-J` §6 rule 2
     keeps single-widget data out of the bus, and routing `test_provider`'s outcome through the
     gateway would change `_provider_inference_test_completed`'s catalogued emitter from "the
     controller that ran the test" to the adapter. Keeping the callback lets the Provider Edit
     controller go on emitting `_provider_inference_test_completed` itself, exactly as `08-J` §5.6
     specifies, so the catalog needs no edit.

1. **No correlation token.** The callback closure carries the correlation (which row, which dialog,
   which model) by construction — the same reason `regenerate_run_analysis` needs none. Adding a
   request token would be unused machinery: the two callback-bearing methods are triggered by
   controls the single-inference gate already prevents from overlapping (`08-E` §13; the
   `PROVIDER_TEST` activity is held for the call's full duration).

### Consequences

- Positive — The graphical thread never blocks on a provider call, so the `TESTING` health dot
  (`description.md` §3.3) and the `_inference_progress`-driven live indicator
  (`provider_edit.md` §8.2) become renderable at all; today they are unimplementable by
  construction. §4, §12 and SPEC-074 all hold simultaneously.
- Positive — `SettingsGateway` now matches the two §7b gateways that already solved this, so there
  is one asynchronous shape in the adapter layer rather than two, and the existing gateway tests are
  a direct template.
- Negative — Four §7b.6 signatures no longer match the specification verbatim: three return types
  are dropped to `None` and two methods gain a keyword-only `on_complete` parameter. Every future
  reader comparing `ui/settings_dialog/protocols.py` against §7b.6 will see the divergence and must
  find this ADR; the Protocol's docstrings must cite it.
- Negative — Callers become two-step. A controller that used to read a result on the next line now
  needs an in-flight visual state and a completion handler, which is more code and one more state
  per action to get wrong (a callback firing after the dialog closes, for instance, must be
  tolerated — `ResultGateway`'s relay pattern already handles this).
- Negative (accepted risk) — The six import/export methods stay synchronous on the graphical thread
  even though they do local file I/O and a YAML parse, which `04_CONCURRENCY_STANDARD.md` §8 would
  put on a worker. This is accepted because §7b.6 does not contain those methods at all (they are a
  STORY-067 extension over a documented specification gap), because
  `06_Settings_Dialog/description.md` §7 and §8 describe both flows as step-by-step synchronous
  sequences ending in a toast with no in-flight state, and because a settings YAML is a small local
  file. If a large-file freeze is ever observed, it is a separate story, not a reopening of this
  ADR.
- Neutral — The `_inference_progress`-driven live indicator of `provider_edit.md` §8.2 becomes
  *possible* but is still not *built*. STORY-066 already records it as unimplemented and unowned; it
  remains unowned after this ADR and needs its own story.
- Neutral — ADR-0014's Neutral consequence cites the anti-pattern table as
  `04_CONCURRENCY_STANDARD.md` §11; the table is actually §12 (§11 is the no-asyncio section). The
  substance of ADR-0014's observation is unaffected, and an accepted ADR is immutable, so the
  correction is recorded here rather than edited into ADR-0014.

## Pros and cons of the options

### Option A — Return immediately; deliver the result asynchronously

- Good — The only option compatible with §4, §12's anti-pattern table, and §8 at the same time.
- Good — Already specified for two sibling gateways (§7b.1 `reprobe`, §7b.5
  `regenerate_run_analysis`) and already shipped and tested (STORY-105, STORY-108), so it costs no
  new concept.
- Good — Makes the specification's own in-flight user-experience states (`TESTING` dot, live
  indicator) achievable.
- Bad — Four §7b.6 signatures diverge from the specification's verbatim text.
- Bad — Each affected call site grows an in-flight state and a completion handler.

### Option B — Bless a bounded graceful blocking call on the graphical thread

- Good — No signature changes at all; every call site keeps its one-line shape.
- Bad — Contradicts the specification's own user-experience description. A blocked graphical thread
  cannot paint a `TESTING` spinner or process the `_inference_progress` events §8.2 requires during
  the call, so §3.3 and §8.2 would both become undeliverable.
- Bad — No textual support anywhere. §4, §8 and §12 each state the rule without exception, and no
  "short probe" carve-out exists in any specification file.
- Bad — The bound is not real. A provider probe's worst case is the configured provider timeout, so
  "short" is an assumption about a remote host, not a guarantee.

### Option C — Nested `QEventLoop` / `QFutureWatcher` wait behind the synchronous signature

- Good — Preserves §7b.6's signatures byte-for-byte, so nothing downstream changes shape.
- Bad — It is an event loop used to await a future, which is precisely the model D-R-01 removed;
  `04_CONCURRENCY_STANDARD.md` §11 binds the project to "stdlib + Qt only — no asyncio, no anyio"
  and CLAUDE.md's non-negotiable constraints ban `asyncio`/`anyio`/`qasync` anywhere in `src/`.
  Re-entering the Qt loop to wait is the same hazard under a different name.
- Bad — Re-entrancy bugs. While the nested loop spins, the user can close the dialog, click Test
  again, or start a run; the outer slot then resumes against destroyed widgets.
- Bad — Still blocks the *calling slot*, so the widget cannot be repainted from within it — the
  `TESTING` state and live indicator remain undeliverable, exactly as in Option B.

## Links

- Related ADRs: ADR-0014 (housed the seven gateways in `adapters/ui_gateways/` and recorded this
  conflict as deliberately unsettled)
- Spec clauses: `08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract`,
  `08_Cross_Cutting/08-E_interfaces_contracts.md#7b6-settingsgateway`,
  `08_Cross_Cutting/08-E_interfaces_contracts.md#7b1-mainwindowgateway`,
  `08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway`,
  `08_Cross_Cutting/08-E_interfaces_contracts.md#7-persistence-stores`,
  `08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client`,
  `08_Cross_Cutting/08-E_interfaces_contracts.md#12-readiness-service`,
  `08_Cross_Cutting/08-J_event_bus_catalog.md#6-when-to-add-a-new-event`,
  `08_Cross_Cutting/08-J_event_bus_catalog.md#56-settings-and-providers-changed`,
  `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#12-anti-patterns`,
  `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#8-thread-boundary-rules`,
  `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#4a-the-dispatcher-thread-dd-38`,
  `06_Settings_Dialog/description.md#33-per-row-actions`,
  `06_Settings_Dialog/sub_dialogs/provider_edit.md#82-test-inference`
- Stories: STORY-110 applies this decision; STORY-105 and STORY-108 established the precedent it
  generalises
