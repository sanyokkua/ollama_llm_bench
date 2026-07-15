"""Proves: STORY-038-AC-6 — export assembly detail (06_IMPORT_FORMATS.md §3, §9)."""

from ollama_llm_bench.backend.import_export.tests.conftest import FakeAppSettingsStore, make_service


def test_export_settings_renders_blank_allowed_float_as_empty_string() -> None:
    """Proves: STORY-038-AC-6

    A stored blank value for a float setting whose spec allows blank
    (``benchmark.temperature``) exports as an empty string, not ``0.0``.
    """
    settings_store = FakeAppSettingsStore(initial_values={"benchmark.temperature": ""})
    service = make_service(app_settings_store=settings_store)

    exported = service.export_settings().decode("utf-8")

    assert "benchmark.temperature: ''" in exported or 'benchmark.temperature: ""' in exported


def test_export_settings_skips_keys_not_in_the_catalog() -> None:
    """Proves: STORY-038-AC-6

    A stored key the settings catalog does not recognise (e.g. a retired or
    internal key) is silently excluded from the export, never written out.
    """
    settings_store = FakeAppSettingsStore(
        initial_values={"ui.theme": "dark", "internal.not_user_importable": "x"}
    )
    service = make_service(app_settings_store=settings_store)

    exported = service.export_settings().decode("utf-8")

    assert "internal.not_user_importable" not in exported
    assert "ui.theme: dark" in exported
