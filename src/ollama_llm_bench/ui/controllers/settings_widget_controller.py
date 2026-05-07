"""SettingsWidgetController — mediates between settings dialog widgets and backend services."""

import contextlib
import logging
import re
from collections.abc import Callable
from pathlib import Path

import yaml
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from ollama_llm_bench.backend.core.interfaces import (
    AppSettingsServiceApi,
    EventBus,
    LLMProviderApi,
    ProviderConfigLoaderApi,
    ProviderRegistryApi,
)
from ollama_llm_bench.backend.core.models import (
    AppSettingsChangedEvent,
    ProviderRegistryReloadedEvent,
    ProvidersConfig,
    ProviderType,
)
from ollama_llm_bench.backend.services.embedding_service import EmbeddingService
from ollama_llm_bench.backend.services.provider_registry import ProviderNotFoundError

logger = logging.getLogger(__name__)


def _connection_error_message(exc: Exception) -> str:
    """Extract a short, human-readable message from a connection exception.

    Args:
        exc: The exception raised during a provider connection test.

    Returns:
        A short, user-facing error string describing the failure cause.
    """
    msg = str(exc).lower()
    if "refused" in msg or "connect" in msg:
        return "Connection refused — is the server running?"
    if "401" in msg or "unauthorized" in msg or "authentication" in msg:
        return "Authentication failed — check your API key"
    if "timeout" in msg:
        return "Connection timed out"
    if "404" in msg:
        return "Endpoint not found — check the base URL"
    return f"Test failed: {exc.__class__.__name__}"


_ENV_VAR_RE: re.Pattern[str] = re.compile(r"^\$\{([A-Z_][A-Z0-9_]*)\}$")


class SettingsWidgetController:
    """Controller for the settings dialog.

    Mediates between the settings UI and the provider registry,
    config loader, app settings service, and providers YAML file.
    Provider connection tests run on a background QThreadPool thread.
    """

    def __init__(
        self,
        *,
        provider_registry: ProviderRegistryApi,
        provider_config_loader: ProviderConfigLoaderApi,
        app_settings: AppSettingsServiceApi,
        providers_yaml_path: Path,
        embedding_service: EmbeddingService,
        event_bus: EventBus,
    ) -> None:
        self._provider_registry = provider_registry
        self._provider_config_loader = provider_config_loader
        self._app_settings = app_settings
        self._providers_yaml_path = providers_yaml_path
        self._embedding_service = embedding_service
        self._event_bus = event_bus
        self._pending_signals: list[QObject] = []

    def get_providers_config(self) -> ProvidersConfig | None:
        """Return the currently loaded ProvidersConfig, or None if not loaded."""
        return self._provider_registry.get_config()

    def test_provider_connection(
        self,
        provider_id: str,
        on_result: Callable[[bool, int, str], None],
    ) -> None:
        """Test connectivity to a provider by listing its available models off the main thread.

        Args:
            provider_id: ID of the provider to test.
            on_result: Callback invoked on the main thread with (is_live, model_count, message).
                       Called immediately with (False, 0, reason) if provider_id is unknown
                       or a required API key is missing.
        """
        try:
            provider = self._provider_registry.get_provider(provider_id)
        except ProviderNotFoundError:
            on_result(False, 0, "Provider not found")
            return

        providers_config = self._provider_registry.get_config()
        if providers_config is not None:
            for pc in providers_config.providers:
                if pc.provider_id == provider_id:
                    if pc.provider_type in (ProviderType.ANTHROPIC, ProviderType.GEMINI) and not pc.api_key:
                        on_result(False, 0, "No API key configured")
                        return
                    break

        class _Signals(QObject):
            done: Signal = Signal(bool, int, str)

        class _Worker(QRunnable):
            def __init__(self, *, provider: LLMProviderApi, signals: _Signals) -> None:
                super().__init__()
                self._provider = provider
                self._signals = signals
                self.setAutoDelete(True)

            @Slot()
            def run(self) -> None:
                try:
                    models = self._provider.get_available_models()
                    self._signals.done.emit(True, len(models), f"Connected — {len(models)} models available")
                except Exception as exc:
                    logger.exception("provider_connection_test_failed", extra={"provider_id": provider_id})
                    msg = _connection_error_message(exc)
                    self._signals.done.emit(False, 0, msg)

        signals = _Signals()
        self._pending_signals.append(signals)

        def _cleanup(is_live: bool, model_count: int, _msg: str, _pid: str = provider_id) -> None:
            with contextlib.suppress(ValueError):
                self._pending_signals.remove(signals)

        signals.done.connect(on_result)
        signals.done.connect(_cleanup)

        worker = _Worker(provider=provider, signals=signals)
        QThreadPool.globalInstance().start(worker)

    def test_embedding_connection(
        self,
        provider_id: str,
        model: str,
        on_result: Callable[[bool, int, str], None],
    ) -> None:
        """Test the embedding configuration by encoding a short test string off the main thread.

        Args:
            provider_id: ID of the provider to use for embedding.
            model: Embedding model name to test.
            on_result: Callback invoked on the main thread with (is_working, vector_dim, message).
        """
        embedding_service = self._embedding_service

        class _EmbedSignals(QObject):
            done: Signal = Signal(bool, int, str)

        class _EmbedWorker(QRunnable):
            def __init__(self, *, signals: _EmbedSignals) -> None:
                super().__init__()
                self._signals = signals
                self.setAutoDelete(True)

            @Slot()
            def run(self) -> None:
                try:
                    vector = embedding_service.encode_single("embedding connectivity test")
                    dim = len(vector)
                    if dim == 0:
                        self._signals.done.emit(False, 0, "Embedding returned empty vector")
                    else:
                        self._signals.done.emit(True, dim, f"Embedding working — {dim}-dim vectors")
                except Exception as exc:
                    logger.exception("embedding_connection_test_failed")
                    self._signals.done.emit(False, 0, f"Embedding failed: {exc.__class__.__name__}")

        signals = _EmbedSignals()
        self._pending_signals.append(signals)

        def _cleanup(ok: bool, dim: int, _msg: str) -> None:
            with contextlib.suppress(ValueError):
                self._pending_signals.remove(signals)

        signals.done.connect(on_result)
        signals.done.connect(_cleanup)

        worker = _EmbedWorker(signals=signals)
        QThreadPool.globalInstance().start(worker)

    def get_models_for_provider(
        self,
        provider_id: str,
        on_result: Callable[[list[str]], None],
    ) -> None:
        """Fetch available model names for a provider off the main thread.

        Args:
            provider_id: ID of the provider to query.
            on_result: Callback invoked on the main thread with a list of model name strings.
                       Called with an empty list if the provider is unknown or unavailable.
        """
        try:
            provider = self._provider_registry.get_provider(provider_id)
        except ProviderNotFoundError:
            on_result([])
            return

        class _Signals(QObject):
            done: Signal = Signal(list)

        class _Worker(QRunnable):
            def __init__(self, *, provider: LLMProviderApi, signals: _Signals) -> None:
                super().__init__()
                self._provider = provider
                self._signals = signals
                self.setAutoDelete(True)

            @Slot()
            def run(self) -> None:
                try:
                    descriptors = self._provider.get_available_models()
                    names = [d.model_name for d in descriptors]
                    self._signals.done.emit(names)
                except Exception:
                    logger.warning("fetch_models_for_provider_failed", extra={"provider_id": provider_id})
                    self._signals.done.emit([])

        signals = _Signals()
        self._pending_signals.append(signals)

        def _cleanup(names: list[str]) -> None:
            with contextlib.suppress(ValueError):
                self._pending_signals.remove(signals)

        signals.done.connect(on_result)
        signals.done.connect(_cleanup)

        worker = _Worker(provider=provider, signals=signals)
        QThreadPool.globalInstance().start(worker)

    def reset_settings(self) -> None:
        """Reset all application settings to their built-in default values."""
        self._app_settings.reset_to_defaults()

    def reload_providers(self) -> None:
        """Reload the providers registry from the current YAML path."""
        try:
            self._provider_registry.reload()
        except Exception:
            logger.warning("provider_registry_reload_failed")

    def load_providers_yaml(self, path: Path) -> bool:
        """Load providers config from a YAML file and reload the registry.

        Args:
            path: Path to the providers.yaml file to load.

        Returns:
            True on success; False if the file could not be loaded or parsed.
        """
        try:
            self._provider_config_loader.load(path)
        except (ValueError, OSError):
            logger.warning("load_providers_yaml_failed", extra={"path": str(path)})
            return False
        self._providers_yaml_path = path
        self._provider_registry.reload()
        return True

    def save_providers_yaml(self, path: Path, config: ProvidersConfig) -> bool:
        """Serialize a ProvidersConfig to YAML and write it to disk.

        Args:
            path: Destination path for the YAML file.
            config: ProvidersConfig to serialize.

        Returns:
            True on success; False if the file could not be written.
        """
        raw: dict[str, object] = {
            "providers": [
                {
                    "id": p.provider_id,
                    "label": p.label,
                    "type": p.provider_type.value,
                    "api_key": p.api_key_raw,
                    "enabled": p.enabled,
                    **({"base_url": p.base_url} if p.base_url is not None else {}),
                    **({"default_models": list(p.default_models)} if p.default_models else {}),
                    **({"azure_deployment": p.azure_deployment} if p.azure_deployment is not None else {}),
                    **({"azure_api_version": p.azure_api_version} if p.azure_api_version is not None else {}),
                }
                for p in config.providers
            ],
            "embedding": {
                "provider_id": config.embedding.provider_id,
                "model": config.embedding.model,
            },
        }
        try:
            path.write_text(yaml.dump(raw, default_flow_style=False, allow_unicode=True), encoding="utf-8")
        except OSError:
            logger.warning("save_providers_yaml_failed", extra={"path": str(path)})
            return False
        return True

    def get_setting(self, key: str) -> str | None:
        """Return the stored string value for key, or None if absent."""
        return self._app_settings.get(key)

    def set_setting(self, key: str, value: str) -> None:
        """Persist a string value for key."""
        self._app_settings.set(key, value)

    def get_setting_bool(self, key: str, *, default: bool = False) -> bool:
        """Return the stored setting parsed as bool."""
        return self._app_settings.get_bool(key, default)

    def get_setting_int(self, key: str, *, default: int = 0) -> int:
        """Return the stored setting parsed as int."""
        return self._app_settings.get_int(key, default)

    def get_setting_float(self, key: str, *, default: float = 0.0) -> float:
        """Return the stored setting parsed as float."""
        return self._app_settings.get_float(key, default)

    def emit_settings_changed(self, changed_keys: list[str]) -> None:
        """Emit AppSettingsChangedEvent for the given changed setting keys."""
        self._event_bus.emit_app_settings_changed(AppSettingsChangedEvent(changed_keys=tuple(changed_keys)))

    def save_providers_config_to_standard_path(self, config: ProvidersConfig) -> bool:
        """Save providers config to the standard providers.yaml location and reload the registry.

        Args:
            config: The ProvidersConfig to serialize and save.

        Returns:
            True on success; False if the file could not be written.
        """
        ok = self.save_providers_yaml(self._providers_yaml_path, config)
        if ok:
            try:
                self._provider_registry.reload()
            except Exception:
                logger.warning("provider_registry_reload_after_save_failed")
            self._event_bus.emit_provider_registry_reloaded(ProviderRegistryReloadedEvent())
        return ok

    def get_provider_instance(self, provider_id: str) -> LLMProviderApi | None:
        """Return the live provider instance for provider_id, or None if not found.

        Args:
            provider_id: ID of the provider to retrieve.

        Returns:
            Live LLMProviderApi instance, or None if the provider_id is unknown.
        """
        try:
            return self._provider_registry.get_provider(provider_id)
        except KeyError:
            return None
