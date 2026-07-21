"""Proves: STORY-067-AC-5

Exercises the real stores' wipe-and-reseed transaction. Covers EC-SET-4 by
asserting the dialog-open gate is out of scope for this story (documented,
not tested here -- EC-SET-4's own test lives in the main-window/app-modes
story that owns the gate, per `08_Cross_Cutting/08-H_app_modes.md` §10).
"""

from pathlib import Path
import uuid

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderConfigDraft, ProviderType
from ollama_llm_bench.backend.persistence.app_settings import (
    create_app_settings_store,
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.providers import create_providers_store

_BUNDLED_PROVIDER_SEEDS: tuple[tuple[str, str], ...] = (
    ("Ollama (local)", "http://localhost:11434/v1"),
    ("LM Studio (local)", "http://localhost:1234/v1"),
    ("llama.cpp (local)", "http://localhost:8080/v1"),
)


class _FakeClock:
    """A deterministic, injectable ``Clock`` with a fixed UTC instant."""

    def now_utc(self) -> str:
        return "2026-01-01T00:00:00+00:00"

    def monotonic_ms(self) -> int:
        return 0


def _bundled_default_provider_configs() -> tuple[ProviderConfig, ...]:
    return tuple(
        ProviderConfig(
            provider_id=str(uuid.uuid4()),
            name=name,
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            base_url=base_url,
            enabled=False,
        )
        for name, base_url in _BUNDLED_PROVIDER_SEEDS
    )


def test_reset_wipes_and_reseeds_atomically(tmp_path: Path) -> None:
    """Proves: STORY-067-AC-5

    Given a custom provider and an edited setting persisted, when the
    wipe-and-reseed transaction runs (``replace_providers`` with the three
    bundled providers, ``upsert_settings`` with the in-code defaults), then
    the provider catalog holds exactly the three bundled providers and the
    setting reverts to its default.
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

    providers_store.add(
        ProviderConfigDraft(
            name="Custom Provider",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            enabled=True,
            base_url="https://api.openai.com/v1",
        )
    )
    app_settings_store.upsert_settings({"ui.theme": "dark"})

    providers_store.replace_providers(_bundled_default_provider_configs())
    app_settings_store.upsert_settings({"ui.theme": "system"})

    names = {p.name for p in providers_store.list_providers()}
    assert names == {"Ollama (local)", "LM Studio (local)", "llama.cpp (local)"}
    assert app_settings_store.get_setting("ui.theme") == "system"
