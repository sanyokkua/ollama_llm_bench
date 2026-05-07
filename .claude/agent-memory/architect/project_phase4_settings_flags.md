---
name: Phase 4 — Settings & Feature Flags design decisions (2026-04-16)
description: Architectural decisions for Phase 4 settings dialog, DragDropHandler, tokens.py, SettingsWidgetController, and DI wiring
type: project
---

Phase 4 plan saved to `docs/v2_plans/PLAN_DOCUMENT_PHASE_4.md` on 2026-04-16.

**Why:** Phase 4 adds the settings dialog (Providers tab + General/Flags tab), DragDropHandler, and design token module.

## Key decisions

**SettingsWidgetController owns threading for connection tests.** Runs `get_available_models()` in a one-shot `QRunnable` on `QThreadPool.globalInstance()` using a nested `_Signals(QObject)` + `_Worker(QRunnable)` defined inside the method body. No separate `qt_classes/` wrapper needed for this one-off pattern.

**`get_config()` added to `ProviderRegistryApi` Protocol.** Returns `ProvidersConfig | None` — no `_guard_loaded()` call, caller handles `None`. This is additive-only; existing Protocol users are unaffected.

**`SettingsWidgetControllerApi` Protocol lives in `backend/core/ui_controllers.py`.** Consistent with existing controller protocols. Imports `ProvidersConfig` and `Path` — both are stdlib/core-layer imports, so the pure-Python constraint is maintained.

**`ui/style/tokens.py` — data layer only in Phase 4.** No `.qss` files, no `theme_loader.py`. Those are deferred until the QSS pipeline task. Phase 4 only creates the Python dicts (`DARK_TOKENS`, `LIGHT_TOKENS`, `SHARED_TOKENS`) and `get_tokens(theme: str) -> dict[str, str]`.

**`DragDropHandler` is a `QObject` with `install_on(widget)`.** No subclassing of the target widget required. Calls `widget.setAcceptDrops(True)` inside `install_on`. Pattern is reusable for task-file panel in a later phase.

**No `theme_loader.py` or QSS application in Phase 4.** Theme setting is persisted to `app_settings` but live switching deferred.

**`save_providers_yaml` uses manual dict serialization.** Converts frozen `ProvidersConfig` dataclass to a plain dict matching the `ProviderConfigLoader.load()` input format, then calls `yaml.dump()`. No new library needed.

## DI wiring path

`_create_app_context()` → `SettingsWidgetController(provider_registry=registry, provider_config_loader=config_loader, app_settings=app_settings, providers_yaml_path=providers_yaml_path)` → stored in `ApplicationContext._settings_widget_controller` → exposed via `AppContext.get_settings_widget_controller() -> SettingsWidgetControllerApi` → used by `MainWindow._open_settings()`.

## Thread safety note (open question)

`_Signals(QObject)` created on main thread inside `test_provider_connection` may be GC'd before signal fires. Mitigation: store in `self._pending_signals: list[QObject]` and pop in callback. Coder must verify this.

**How to apply:** When any future task involves provider health checking or one-shot background calls from a controller (not the benchmark pipeline), use this same nested `_Signals` + `_Worker` pattern inside the method body.
