---
id: STORY-052
title: Provide the reusable provider and model dropdown sub-packages
status: done
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#9-provider-registry
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client
  - 08_Cross_Cutting/08-J_event_bus_catalog.md#56-settings-and-providers-changed
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#11-border-and-focus-tokens
  - 08_Cross_Cutting/08-L_ui_standardization.md#11-theme-handling
modules:
  - ui/shared/provider_dropdown/
  - ui/shared/model_dropdown/
acceptance_criteria:
  - STORY-052-AC-1
  - STORY-052-AC-2
  - STORY-052-AC-3
  - STORY-052-AC-4
  - STORY-052-AC-5
  - STORY-052-AC-6
depends_on:
  - STORY-003
  - STORY-017
  - STORY-040
  - STORY-049
adrs:
  - ADR-0001
owner: coder
estimate: M
---

# STORY-052 — Provide the reusable provider and model dropdown sub-packages

## Goal

Deliver the two sibling `QComboBox`-backed dropdown primitives every provider- or model-picking
surface reuses: one that lists the enabled providers and emits the selected `provider_id`, and
one that lists a chosen provider's models and emits the selected model name. Both accept an
optional filter, style themselves from theme roles, and stay current — the provider dropdown
rebuilds when the provider registry reloads. The consumer wires the two together; the widgets
carry no coupling between themselves.

## In scope

- `ui/shared/provider_dropdown/`: `make_provider_dropdown(...) -> QWidget` — a combo over
  `ProviderRegistry.list_enabled()` that displays each provider's user-facing name, accepts an
  optional `filter` callable, emits `provider_changed(provider_id: str)`, and rebuilds itself on
  the `_provider_registry_reloaded` event.
- `ui/shared/model_dropdown/`: `make_model_dropdown(...) -> QWidget` — a combo whose items come
  from `ProviderRegistry.get_client(provider_id).list_models()`, driven by the consumer's
  `set_provider(provider_id)`, accepts an optional `filter` callable, and emits
  `model_changed(model_name: str)`.

## Out of scope

- The `ProviderRegistry` and `LLMClient` Protocols and the concrete registry — owned by
  STORY-017; these widgets consume the Protocols.
- The `_provider_registry_reloaded` payload and its Qt-main-thread delivery — owned by STORY-003
  (payload) and STORY-040 (the Qt event-bus deliverer); this story subscribes to the delivered
  event.
- The theme tokens and QSS generator — owned by STORY-049; these widgets set theme role
  properties only.
- The base visual primitives (`BadgeLabel`, `HealthDot`, `MultiCheckFilterButton`) — owned by
  STORY-051; these dropdowns do not compose them.
- The consuming surfaces (New Benchmark test-model picker, Generate Analysis dialog) — later
  phases wire these dropdowns into them.

## Spec inputs

- `08-E §9 (#9-provider-registry)` — the `ProviderRegistry` surface the provider dropdown reads:
  `list_enabled()` returning the enabled `ProviderConfig` tuple, and `get_client(provider_id)`
  returning the routed `LLMClient`; both are fast-synchronous.
- `08-E §10 (#10-llm-client)` — the `LLMClient.list_models()` surface the model dropdown reads,
  and the rule that `list_models` is a *blocking* method invoked only on a `TaskRunner` worker
  thread (it performs network I/O).
- `08-J §5.6 (#56-settings-and-providers-changed)` — the `_provider_registry_reloaded` event
  (payload `ProviderRegistryReloadedEvent`, `UI → UI` delivery) that every widget listing
  providers or models re-reads on; the provider dropdown rebuilds its items on it.
- `08-D §16 (#16-the-theme-module-contract)` — appearance is set through theme role dynamic
  properties resolved by `ui/theme`; the widget never calls `setStyleSheet` or embeds a literal.
- `08-D §11 (#11-border-and-focus-tokens)` — the focus ring the focusable combo renders on focus.
- `08-L §11 (#11-theme-handling)` — the widget repaints correctly on a runtime theme change with
  no loss of its current selection.

## Design constraints

- `ui/shared/provider_dropdown/` and `ui/shared/model_dropdown/` are independent sibling
  sub-packages with no coupling between them; the consumer connects `provider_changed` to the
  model dropdown's `set_provider` (`01_MODULE_INVENTORY.md` §6).
- `provider_id` is the internal UUID emitted on the `provider_changed` signal; the combo shows
  the provider's user-facing `name`, never the `provider_id`.
- `LLMClient.list_models()` is a blocking network call; the model dropdown must fetch models off
  the GUI thread (through the `TaskRunner`) and never block the event loop — aligned with the
  concurrency standard, not a Qt-side abort.
- Appearance comes from theme role dynamic properties only; no `setStyleSheet`, no colour literal
  (ADR-0001, 08-D §16) — enforced by an architecture test.
- **Design decision (recorded here, not escalated per the investigator's noted convention):** each
  dropdown is a single `make_*(...) -> QWidget` factory whose signals are declared on the returned
  widget; the exact factory keyword arguments (registry access, optional `filter`, initial
  selection) are an implementation judgment consistent with the module's factory convention.
- No `asyncio`.

## Acceptance criteria

### STORY-052-AC-1

Given a `ProviderRegistry` whose `list_enabled()` returns a set of enabled providers, when
`make_provider_dropdown(...)` builds the widget, then the combo is populated with one entry per
enabled provider, each displaying that provider's user-facing `name` (never its `provider_id`).

### STORY-052-AC-2

Given a populated provider dropdown, when the user selects a provider, then the widget emits
`provider_changed(provider_id)` carrying the selected provider's internal `provider_id`.

### STORY-052-AC-3

Given a `filter` callable passed to `make_provider_dropdown(...)`, when the widget is built, then
only the providers for which `filter(provider)` returns `True` appear in the combo.

### STORY-052-AC-4

Given a built provider dropdown, when a `_provider_registry_reloaded` event is delivered, then
the widget rebuilds its items from the updated `ProviderRegistry.list_enabled()` result.

### STORY-052-AC-5

Given a `filter` callable and a `model_dropdown`, when the consumer calls
`set_provider(provider_id)`, then the combo is populated from
`ProviderRegistry.get_client(provider_id).list_models()`, restricted to the models for which
`filter(model)` returns `True`.

### STORY-052-AC-6

Given a populated model dropdown, when the user selects a model, then the widget emits
`model_changed(model_name)` carrying the selected model's name.

## Test plan

- STORY-052-AC-1 — unit (`pytest-qt`, fake `ProviderRegistry`), colocated
  `src/ollama_llm_bench/ui/shared/provider_dropdown/tests/test_provider_dropdown.py`,
  `test_populates_from_list_enabled_showing_names`.
- STORY-052-AC-2 — unit (`pytest-qt`), same file,
  `test_selection_emits_provider_changed_with_provider_id`.
- STORY-052-AC-3 — unit (`pytest-qt`), same file,
  `test_filter_restricts_visible_providers`.
- STORY-052-AC-4 — integration (`pytest-qt`),
  `tests/integration/test_provider_dropdown_reload.py`,
  `test_rebuilds_items_on_provider_registry_reloaded`.
- STORY-052-AC-5 — unit (`pytest-qt`, fake registry + fake client), colocated
  `src/ollama_llm_bench/ui/shared/model_dropdown/tests/test_model_dropdown.py`,
  `test_set_provider_populates_from_list_models_with_filter`.
- STORY-052-AC-6 — unit (`pytest-qt`), same file,
  `test_selection_emits_model_changed_with_model_name`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-052.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/shared/provider_dropdown/` and
  `ui/shared/model_dropdown/`.
- [x] An architecture test confirms neither sub-package references `setStyleSheet` or embeds a
  colour literal, that they do not import each other, and that they import no `asyncio`.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory is unchanged.

## Notes

- AC-4's test (`tests/integration/test_provider_dropdown_reload.py::test_rebuilds_items_on_provider_registry_reloaded`)
  passed in isolation but flaked in a full-suite run: Qt lazily populates its font-family-alias
  cache once per process and logs a one-time diagnostic naming whichever font family first
  triggers it, which the root `_qt_parity_rig` fixture (`tests/conftest.py`) then attributed to
  whichever unrelated test happened to run first in `pytest-randomly` order. Root-caused and
  fixed at the test-infrastructure level (not this story's production code, and not a
  per-test suppression): a session-scoped warm-up fixture forces the one-time font-alias
  population before any test's parity-rig window opens, and a new autouse fixture restores the
  shared `QApplication`'s stylesheet/palette after every test so a theme applied by one test
  (e.g. `make_theme_manager` in the theme module's own tests) never leaks into a later test's
  font resolution. See `tests/conftest.py` and `src/ollama_llm_bench/ui/conftest.py`.
