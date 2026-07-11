---
id: STORY-014
title: Resolve the three-layer settings hierarchy and build the frozen per-run snapshot
status: done
spec_clauses:
  - 08_Cross_Cutting/08-C_settings_hierarchy.md#2-resolution-order
  - 08_Cross_Cutting/08-C_settings_hierarchy.md#3-the-settings-accessor
  - 08_Cross_Cutting/08-C_settings_hierarchy.md#4-which-keys-are-per-run-overridable
  - 08_Cross_Cutting/08-C_settings_hierarchy.md#5-creating-the-per-run-snapshot
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#8-settings-service
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#8a-run-snapshot-builder
  - 08_Cross_Cutting/08-G_feature_flags.md#3-benchmark--benchmark-behaviour
  - 08_Cross_Cutting/08-G_feature_flags.md#4-feature--inference-and-analysis-behaviour
  - 08_Cross_Cutting/08-G_feature_flags.md#5-eval--evaluation-behaviour
modules:
  - backend/settings/
acceptance_criteria:
  - STORY-014-AC-1
  - STORY-014-AC-2
  - STORY-014-AC-3
  - STORY-014-AC-4
  - STORY-014-AC-5
  - STORY-014-AC-6
depends_on:
  - STORY-001
  - STORY-002
  - STORY-003
  - STORY-004
  - STORY-008
owner: coder
estimate: M
---

# STORY-014 — Resolve the three-layer settings hierarchy and build the frozen per-run snapshot

## Goal

Give the application its single typed accessor for every setting value, resolving each read
through the three-layer cascade (per-run snapshot, then user-saved, then in-code default), and
its builder that freezes the per-run-overridable keys into an immutable snapshot at run start.
Every widget and service reads settings only through this module — no other code touches
`app_settings` or a run's snapshot directly — so a run is reproducible from its own frozen inputs
and presentation preferences stay live.

## In scope

- The in-code **`DEFAULTS` map** — one entry for every `benchmark.*`, `feature.*`, `eval.*`,
  `embedding.*`, `ui.*`, `logging.*`, and `task_editor.*` key in the registry, with its default
  value and its logical type, per `08-G_feature_flags.md` §3–§9. This is the floor: a resolved
  read never returns absent.
- The **`PER_RUN_OVERRIDABLE` registry** — the exact set of keys whose Per-Run column is `✓` in
  `08-G_feature_flags.md` (every `benchmark.*` key except `benchmark.last_mode`, every `feature.*`
  key except the live `ui.stream_tokens_to_log` key, and every `eval.*` key).
- The `SettingsService` Protocol and its concrete implementation: `get_str` / `get_bool` /
  `get_int` / `get_float` (each taking an optional `run`), `set`, and `upsert`, resolving per
  `08-C_settings_hierarchy.md` §2 and coercing per the `08-E` §8 SPEC-110 rule.
- The `RunSnapshotBuilder` Protocol and its concrete implementation: `build_snapshot()` captures
  the `User-Saved ▶ Default` value of every `PER_RUN_OVERRIDABLE` key into the frozen
  `BenchmarkRunSettingEntry` tuple.
- The `_app_settings_changed` event emission on every `upsert` (and `set`), carrying the set of
  changed keys, published on the Qt-free `EventBus`.
- The `make_settings_service` and `make_run_snapshot_builder` factory functions on the module's
  `api.py`, guarded by `icontract` on programmer invariants only.

## Out of scope

- Applying the New Benchmark form's per-run overrides (`RunStartRequest.setting_overrides`) onto
  the captured snapshot — that is the benchmark-pipeline run-creation use case's step (DD-47,
  `08-C` §5 step 2), a later phase; this story captures the `User-Saved ▶ Default` base snapshot
  the use case then overlays.
- The provider/embedding name snapshot (`judge_provider_name`, `embedding_provider_name`, …)
  captured alongside the settings snapshot — owned by the run-creation use case (`08-E` §8a
  closing note), not by `RunSnapshotBuilder`.
- The `AppSettingsStore` write connection, schema lifecycle, and `app_settings`/`app_meta` row
  logic — owned by STORY-008; this story consumes that store's Protocol.
- The Settings dialog UI and its working-copy/dirty-diff — a later UI phase.

## Spec inputs

- `08_Cross_Cutting/08-C_settings_hierarchy.md#2-resolution-order` — the two cascades: a
  per-run-overridable key with a run resolves `Per-Run Snapshot ▶ User-Saved ▶ Default`; every
  other read resolves `User-Saved ▶ Default`, skipping the snapshot layer.
- `08_Cross_Cutting/08-C_settings_hierarchy.md#3-the-settings-accessor` — the typed read/write
  method set and the calling convention (pipeline passes `run`, UI passes `None`).
- `08_Cross_Cutting/08-C_settings_hierarchy.md#4-which-keys-are-per-run-overridable` — the exact
  `PER_RUN_OVERRIDABLE` membership and the keys deliberately excluded.
- `08_Cross_Cutting/08-C_settings_hierarchy.md#5-creating-the-per-run-snapshot` — the exhaustive
  capture over `PER_RUN_OVERRIDABLE` that `build_snapshot()` performs before any override overlay.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#8-settings-service` — the `SettingsService`
  signatures, the `ConfigurationError`-on-unknown-key rule, and the SPEC-110 coercion-failure rule
  (malformed user-saved value falls through to the default with a logged warning; a malformed
  snapshot value is a `ProgrammerError`).
- `08_Cross_Cutting/08-E_interfaces_contracts.md#8a-run-snapshot-builder` — the `build_snapshot()`
  contract and the deliberate separation of the two Protocols in one package.
- `08_Cross_Cutting/08-G_feature_flags.md#3-benchmark--benchmark-behaviour` — every `benchmark.*`
  key, its type, default, and Per-Run flag.
- `08_Cross_Cutting/08-G_feature_flags.md#4-feature--inference-and-analysis-behaviour` — the
  `feature.*` keys and the live-not-overridable `ui.stream_tokens_to_log` key.
- `08_Cross_Cutting/08-G_feature_flags.md#5-eval--evaluation-behaviour` — every `eval.*` key,
  its type, default, and Per-Run flag.

## Design constraints

- `backend/settings/` is Qt-free and asyncio-free; it imports only `backend/infra`,
  `backend/persistence/app_settings` (`AppSettingsStore`), `backend/events`, `backend/errors`,
  `backend/domain`, and `msgspec` (`01_MODULE_INVENTORY.md` §4.2). No PySide6.
- `SettingsService` and `RunSnapshotBuilder` are two independently-injected Protocols in the one
  package; they may share an internal resolver in `_internal/` but neither depends on the other's
  public surface.
- Every cross-boundary value is a `msgspec.Struct(frozen=True, kw_only=True, gc=False)`; the
  captured snapshot is a tuple of `BenchmarkRunSettingEntry`.
- An unknown key is a `ConfigurationError` (programmer error, not user input). A non-coercible
  user-saved value falls through to the default with a logged warning (never raises); a
  non-coercible snapshot value is a `ProgrammerError`.
- Only the user-saved layer is mutable; there is no API to mutate a snapshot after a run exists.
- `icontract` on the `api.py` factory functions guards programmer invariants only — never a user
  value, a stored setting value, or a provider response.

## Acceptance criteria

### STORY-014-AC-1

For every setting key in the `DEFAULTS` map, given no user-saved value and no run, when the key
is read through its typed accessor, then the read returns the key's declared default and never
signals absence — the default layer is a total floor over the registry.

### STORY-014-AC-2

For every setting key, resolving it yields the first present value in the cascade order defined
by whether the key is per-run-overridable: a per-run-overridable key read with a run whose
snapshot holds it resolves at the snapshot layer; the same key read with `run=None`, or any
non-overridable key, skips the snapshot and resolves `User-Saved ▶ Default`; a user-saved value
overrides the default when no snapshot value applies.

### STORY-014-AC-3

Given a key that is not present in the `DEFAULTS` map, when any typed accessor or `set` is called
with that key, then it raises `ConfigurationError` and performs no read fall-through and no write.

### STORY-014-AC-4

Given a user-saved value that cannot be coerced to the accessor's requested type, when the typed
accessor reads it, then it returns the key's in-code default, logs a warning naming the key, and
does not raise (SPEC-110); given a per-run snapshot value that cannot be coerced, the accessor
raises a `ProgrammerError`.

### STORY-014-AC-5

Given a set of setting values, when `upsert` writes them, then the values are written to the
user-saved layer atomically and exactly one `_app_settings_changed` event is emitted carrying the
set of changed keys.

### STORY-014-AC-6

When `build_snapshot()` is called, then the returned frozen tuple contains exactly one
`BenchmarkRunSettingEntry` for every key in `PER_RUN_OVERRIDABLE` — no more and no fewer — each
carrying that key's `User-Saved ▶ Default` resolved value, and no key outside `PER_RUN_OVERRIDABLE`
appears in the snapshot.

## Test plan

- STORY-014-AC-1 — property (Hypothesis over every registry key), colocated
  `src/ollama_llm_bench/backend/settings/tests/test_defaults_floor.py`,
  `test_default_layer_is_total_over_registry`.
- STORY-014-AC-2 — property (Hypothesis over every key × layer-presence combination), colocated
  `src/ollama_llm_bench/backend/settings/tests/test_resolution_order.py`,
  `test_resolution_returns_first_present_layer_in_order`. This is the Phase-level
  resolution-order-correctness property test.
- STORY-014-AC-3 — unit, colocated
  `src/ollama_llm_bench/backend/settings/tests/test_settings_service.py`,
  `test_unknown_key_raises_configuration_error_without_side_effects`.
- STORY-014-AC-4 — unit, same file,
  `test_malformed_user_value_falls_through_and_malformed_snapshot_is_programmer_error`.
- STORY-014-AC-5 — unit, same file,
  `test_upsert_writes_atomically_and_emits_settings_changed_with_changed_keys`.
- STORY-014-AC-6 — unit, colocated
  `src/ollama_llm_bench/backend/settings/tests/test_run_snapshot_builder.py`,
  `test_build_snapshot_captures_exactly_the_per_run_overridable_keys`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-014.
- [x] A Hypothesis property test proves resolution-order correctness across all registry keys
  (STORY-014-AC-2).
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/settings/`.
- [x] An architecture test confirms `backend/settings/` imports no Qt and no `asyncio`.
- [x] The traceability record validates with no orphan clause and no orphan test for STORY-014.
- [x] The module inventory is unchanged.

## Notes

- `just trace-check` still fails on five pre-existing, STORY-014-unrelated gaps
  (`EC-PERSIST-6` dangling row; `EC-PROV-1a`/`EC-RUN-1a` uncovered; `EC-RUN-13`/`EC-RUN-14`
  named by draft STORY-016/STORY-015 with no test yet) — confirmed present in the
  `186b896` commit ("Phase 3. Created user stories") before this story's work began, and
  already documented as the same pre-existing gap by STORY-003/STORY-005/STORY-010/STORY-013's
  own Notes sections. The first three trace to a permanent cross-reference gap between the
  read-only vendored `08-I_edge_cases.md` catalog and `06_EDGE_CASE_TO_TEST_MAPPING.md` (neither
  file may be edited in place per `repository-documentation.md`); the last two will close once
  STORY-015/STORY-016 are implemented. STORY-014 itself has zero orphan clauses/ACs/tests —
  verified directly against the regenerated `traceability.yaml`.
- Independent spec-conformance review (read-only) returned CONFORMS WITH CONCERNS, both
  non-blocking: (1) `_internal/registry.py`'s `benchmark.*` block comment ("12 keys, all
  per-run-overridable except `last_mode`") was flagged as possibly conflating total-vs-overridable
  counts, but on inspection the phrasing is accurate as written (12 total, 11 of which are
  overridable) and needed no change; (2) `SettingsService.set` also emits
  `_app_settings_changed`, which `08-E` §8's literal text documents only for `upsert` — this is
  a deliberate, story-sanctioned choice (`In scope` explicitly says "on every `upsert` (and
  `set`)"), not a deviation.
