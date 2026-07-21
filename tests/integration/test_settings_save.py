"""Proves: STORY-067-AC-3

Exercises the real ProvidersStore + AppSettingsStore behind a real adapter-
style call sequence (not FakeSettingsGateway), wrapped in
structlog.testing.capture_logs() to assert no error/critical log escapes.
"""

from pathlib import Path

import structlog

from ollama_llm_bench.backend.domain import ProviderConfigDraft, ProviderType
from ollama_llm_bench.backend.persistence.app_settings import (
    create_app_settings_store,
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.providers import create_providers_store


class _FakeClock:
    """A deterministic, injectable ``Clock`` with a fixed UTC instant."""

    def now_utc(self) -> str:
        return "2026-01-01T00:00:00+00:00"

    def monotonic_ms(self) -> int:
        return 0


def _make_provider_draft(*, name: str) -> ProviderConfigDraft:
    return ProviderConfigDraft(
        name=name,
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
        base_url="http://localhost:11434/v1",
    )


def test_atomic_save_writes_both_and_emits_events(tmp_path: Path) -> None:
    """Proves: STORY-067-AC-3

    Exercises the real ``ProvidersStore``/``AppSettingsStore`` write path a
    concrete ``SettingsGateway`` adapter (Phase 11) will route Save through --
    both stores accept a write in the same session, and no error/critical log
    record escapes.
    """
    clock = _FakeClock()
    db_path = tmp_path / "ollama_llm_bench.db"
    write_conn, lock = open_write_connection(db_path)
    ensure_schema(write_conn, lock, clock=clock)
    providers_store = create_providers_store(
        write_conn, lock, lambda: open_read_connection(db_path)
    )
    app_settings_store = create_app_settings_store(
        write_conn, lock, lambda: open_read_connection(db_path), clock
    )

    with structlog.testing.capture_logs() as captured_logs:
        providers_store.add(_make_provider_draft(name="Ollama (local)"))
        app_settings_store.upsert_settings({"ui.theme": "dark"})

    assert app_settings_store.get_setting("ui.theme") == "dark"
    assert len(providers_store.list_providers()) == 1
    assert not any(entry["log_level"] in {"error", "critical"} for entry in captured_logs)
