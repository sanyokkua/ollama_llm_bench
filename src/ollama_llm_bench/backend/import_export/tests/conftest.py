"""Shared fixtures and local test doubles for ``backend/import_export/`` tests.

Neither ``ProvidersStore`` nor ``AppSettingsStore`` has an existing ``testing.py``
fake importable here (both live under ``backend/persistence/*`` — not a declared
dependency of any downstream ``testing.py``), so this module defines its own
local doubles, matching the shape of ``FakeProvidersStore`` in
``backend/provider_registry/tests/conftest.py`` and ``FakeAppSettingsStore`` in
``backend/settings/tests/conftest.py``. Unlike those read-mostly fakes, this
module's own tests exercise the *full* ``ProvidersStore``/``AppSettingsStore``
surface the importer actually calls (``get_by_name``, ``replace_providers``,
``upsert_settings``), so both doubles behave for real against an in-memory
dict rather than raising ``NotImplementedError``.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from ollama_llm_bench.backend.domain import (
    ProviderConfig,
    ProviderConfigDraft,
    ProviderId,
    ProviderType,
    SettingKey,
)
from ollama_llm_bench.backend.events.protocols import EventBus, Subscription
from ollama_llm_bench.backend.import_export.api import make_import_export_service
from ollama_llm_bench.backend.import_export.protocols import ImportExportService
from ollama_llm_bench.backend.persistence.app_settings.protocols import AppSettingsStore
from ollama_llm_bench.backend.persistence.providers.protocols import ProvidersStore

__all__: list[str] = [
    "FakeAppSettingsStore",
    "FakeEventBus",
    "FakeProvidersStore",
    "make_provider_config",
    "make_service",
    "write_yaml_mapping",
    "write_yaml_text",
]

_yaml = YAML()
_yaml.default_flow_style = False


class FakeProvidersStore:
    """A fully in-memory ``ProvidersStore`` double, keyed by ``name``.

    ``get_by_name`` and ``replace_providers`` behave for real (the importer
    pre-checks duplicates via the former and the confirmed apply calls the
    latter); ``add``/``update``/``delete`` are unused by this module's tests
    and raise ``NotImplementedError`` if exercised by mistake.
    """

    def __init__(self, *, providers: tuple[ProviderConfig, ...] = ()) -> None:
        self._providers: dict[str, ProviderConfig] = {p.name: p for p in providers}
        self.replace_calls: list[tuple[ProviderConfig, ...]] = []

    def list_providers(self) -> tuple[ProviderConfig, ...]:
        """Return the catalog in insertion order."""
        return tuple(self._providers.values())

    def get_by_name(self, name: str) -> ProviderConfig | None:
        """Return the provider named ``name``, or ``None`` if absent."""
        return self._providers.get(name)

    def add(self, draft: ProviderConfigDraft) -> ProviderId:
        """Unused by ``import_export`` tests."""
        raise NotImplementedError("add is not exercised by import_export tests")

    def update(self, provider_id: ProviderId, config: ProviderConfig) -> None:
        """Unused by ``import_export`` tests."""
        raise NotImplementedError("update is not exercised by import_export tests")

    def delete(self, provider_id: ProviderId) -> None:
        """Unused by ``import_export`` tests."""
        raise NotImplementedError("delete is not exercised by import_export tests")

    def replace_providers(self, configs: tuple[ProviderConfig, ...]) -> None:
        """Record the call and replace the catalog wholesale."""
        self.replace_calls.append(configs)
        self._providers = {p.name: p for p in configs}


class FakeAppSettingsStore:
    """A minimal in-memory ``AppSettingsStore`` double (mirrors
    ``backend/settings/tests/conftest.py::FakeAppSettingsStore``)."""

    def __init__(self, *, initial_values: dict[SettingKey, str] | None = None) -> None:
        self._values: dict[SettingKey, str] = dict(initial_values or {})
        self.upsert_calls: list[dict[SettingKey, str]] = []

    def get_setting(self, key: SettingKey) -> str | None:
        """Return the stored value for ``key``, or ``None`` if unset."""
        return self._values.get(key)

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        """Record the call and write every value into the in-memory layer."""
        self.upsert_calls.append(dict(values))
        self._values.update(values)

    def list_settings(self) -> dict[SettingKey, str]:
        """Return every stored key/value pair."""
        return dict(self._values)

    def get_schema_version(self) -> int:
        """Return a fixed schema version; unused by import/export."""
        return 1


class FakeEventBus:
    """A minimal in-memory ``EventBus`` double recording every ``emit`` call."""

    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []

    def subscribe(
        self, signal_name: str, handler: Callable[[object], None], owner: object | None = None
    ) -> Subscription:
        """Unused by ``import_export`` tests; present only to satisfy the Protocol shape."""
        raise NotImplementedError("subscribe is not exercised by import_export tests")

    def emit(self, signal_name: str, payload: object) -> None:
        """Record the emitted ``(signal_name, payload)`` pair."""
        self.emitted.append((signal_name, payload))


def make_provider_config(  # noqa: PLR0913  # test builder must expose every seedable field
    *,
    provider_id: str = "11111111-1111-4111-8111-111111111111",
    name: str = "provider",
    provider_type: ProviderType = ProviderType.OPENAI_COMPATIBLE,
    enabled: bool = True,
    base_url: str | None = "http://localhost:11434/v1",
    api_key_raw: str | None = None,
) -> ProviderConfig:
    """Build a minimal, otherwise-arbitrary ``ProviderConfig`` for seeding a fake store."""
    return ProviderConfig(
        provider_id=provider_id,
        name=name,
        provider_type=provider_type,
        enabled=enabled,
        base_url=base_url,
        api_key_raw=api_key_raw,
    )


def make_service(
    *,
    providers_store: ProvidersStore | None = None,
    app_settings_store: AppSettingsStore | None = None,
    event_bus: EventBus | None = None,
) -> ImportExportService:
    """Build an ``ImportExportService`` over fakes, any of which may be overridden."""
    return make_import_export_service(
        providers_store=providers_store if providers_store is not None else FakeProvidersStore(),
        app_settings_store=(
            app_settings_store if app_settings_store is not None else FakeAppSettingsStore()
        ),
        event_bus=event_bus if event_bus is not None else FakeEventBus(),
    )


def write_yaml_text(tmp_path: Path, text: str, *, name: str = "import.yaml") -> str:
    """Write raw text content to ``tmp_path/name`` and return its absolute path.

    Used for file-level cases (bad extension, malformed YAML, non-mapping
    root) where the exact byte content, not a structured mapping, is the point.
    """
    file_path = tmp_path / name
    file_path.write_text(text, encoding="utf-8")
    return str(file_path)


def write_yaml_mapping(
    tmp_path: Path, document: dict[str, Any], *, name: str = "import.yaml"
) -> str:
    """Serialize ``document`` to ``tmp_path/name`` as plain YAML and return its path."""
    file_path = tmp_path / name
    with file_path.open("w", encoding="utf-8") as handle:
        _yaml.dump(document, handle)
    return str(file_path)
