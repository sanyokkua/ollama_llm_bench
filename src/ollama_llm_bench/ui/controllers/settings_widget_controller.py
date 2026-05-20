"""SettingsWidgetController — mediates between settings dialog widgets and backend services."""

import contextlib
import importlib.resources
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
    ProviderConfigRepositoryApi,
    ProviderRegistryApi,
)
from ollama_llm_bench.backend.core.models import (
    AppReadinessChangedEvent,
    AppSettingsChangedEvent,
    EmbeddingConfig,
    ProviderConfig,
    ProviderRegistryReloadedEvent,
    ProvidersConfig,
    ProviderType,
)
from ollama_llm_bench.backend.services.embedding_model_classifier import EmbeddingModelClassifier
from ollama_llm_bench.backend.services.embedding_service import EmbeddingService
from ollama_llm_bench.backend.services.provider_registry import ProviderNotFoundError
from ollama_llm_bench.backend.services.providers.openai_embedding_provider import OpenAIEmbeddingProvider

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
        embedding_classifier: EmbeddingModelClassifier,
        config_repository: ProviderConfigRepositoryApi | None = None,
    ) -> None:
        self._provider_registry = provider_registry
        self._provider_config_loader = provider_config_loader
        self._app_settings = app_settings
        self._providers_yaml_path = providers_yaml_path
        self._embedding_service = embedding_service
        self._event_bus = event_bus
        self._embedding_classifier = embedding_classifier
        self._config_repository = config_repository
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
        *,
        parent: QObject | None = None,
    ) -> None:
        """Test the embedding configuration by encoding a short test string off the main thread.

        Args:
            provider_id: ID of the provider to use for embedding.
            model: Embedding model name to test.
            on_result: Callback invoked on the main thread with (is_working, vector_dim, message).
            parent: Optional QObject parent to own the internal signal object, preventing
                premature garbage collection when the calling widget is still alive.
        """
        config = self._provider_registry.get_config()
        if config is None:
            on_result(False, 0, "No providers loaded")
            return
        matching = next((p for p in config.providers if p.provider_id == provider_id), None)
        if matching is None:
            on_result(False, 0, "Provider not found in config")
            return
        if matching.provider_type != ProviderType.OPENAI_COMPATIBLE:
            on_result(False, 0, "Embedding provider must be openai_compatible type")
            return
        try:
            embedding_client = OpenAIEmbeddingProvider(
                base_url=matching.base_url or "",
                api_key=matching.api_key,
                model=model,
            )
            embedding_service = EmbeddingService(provider=embedding_client)
        except Exception as exc:
            logger.warning("embedding_test_service_build_failed", exc_info=True)
            on_result(False, 0, f"Failed to build embedding client: {exc.__class__.__name__}")
            return

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

        signals = _EmbedSignals(parent)
        self._pending_signals.append(signals)

        def _cleanup(ok: bool, dim: int, _msg: str) -> None:
            with contextlib.suppress(ValueError):
                self._pending_signals.remove(signals)

        signals.done.connect(on_result)
        signals.done.connect(_cleanup)

        QThreadPool.globalInstance().start(_EmbedWorker(signals=signals))

    def get_models_for_provider(
        self,
        provider_id: str,
        on_result: Callable[[list[str]], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """Fetch available model names for a provider off the main thread.

        Args:
            provider_id: ID of the provider to query.
            on_result: Callback invoked on the main thread with a list of model name strings.
                       Called with an empty list if the provider is unknown or unavailable.
            parent: Optional QObject parent to own the internal signal object, preventing
                premature garbage collection when the calling widget is still alive.
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

        signals = _Signals(parent)
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
        """Reload the providers registry from the database."""
        try:
            self._provider_registry.reload()
        except Exception:
            logger.warning("provider_registry_reload_failed")

    def get_bundled_providers_config(self) -> ProvidersConfig | None:
        """Load and return the bundled default providers.yaml without modifying storage.

        Returns:
            ProvidersConfig from the bundled YAML, or None if loading fails.
        """
        try:
            bundled = importlib.resources.files("ollama_llm_bench").joinpath("providers.yaml")
            with importlib.resources.as_file(bundled) as bundled_path:
                return self._provider_config_loader.load(bundled_path)
        except Exception:
            logger.warning("load_bundled_providers_yaml_failed")
            return None

    def reset_providers_to_defaults(self) -> None:
        """Reset all providers and embedding config to factory defaults.

        Loads the bundled providers.yaml, replaces all DB rows with the bundled
        content, reloads the registry, and emits a registry-reloaded event.
        """
        if self._config_repository is None:
            return
        config = self.get_bundled_providers_config()
        if config is None:
            return
        self._config_repository.replace_all(list(config.providers))
        self._config_repository.save_embedding_config(config.embedding)
        try:
            self._provider_registry.reload()
        except Exception:
            logger.warning("provider_registry_reload_after_reset_failed")
        self._event_bus.emit_provider_registry_reloaded(ProviderRegistryReloadedEvent())

    def load_providers_yaml(self, path: Path) -> bool:
        """Load providers config from a YAML file, sync it to the DB, and reload the registry.

        Args:
            path: Path to the providers.yaml file to load.

        Returns:
            True on success; False if the file could not be loaded or parsed.
        """
        try:
            config = self._provider_config_loader.load(path)
        except (ValueError, OSError):
            logger.warning("load_providers_yaml_failed", extra={"path": str(path)})
            return False
        self._providers_yaml_path = path
        if self._config_repository is not None:
            try:
                self._config_repository.replace_all(list(config.providers))
                self._config_repository.save_embedding_config(config.embedding)
            except Exception:
                logger.exception("load_providers_yaml_db_sync_failed")
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
        raw = self._provider_config_loader.serialize_config(config)
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

    def _save_config_to_db(self, config: ProvidersConfig) -> bool:
        """Write all providers and embedding config to the SQLite repository.

        Deletes any rows not present in config before upserting, so removed
        providers do not linger as orphans.

        Args:
            config: ProvidersConfig to persist in the database.

        Returns:
            True on success; False if the repository is absent or a DB error occurs.
        """
        if self._config_repository is None:
            return False
        try:
            new_ids = {p.provider_id for p in config.providers}
            existing_ids = {p.provider_id for p in self._config_repository.load_all()}
            for pid in existing_ids - new_ids:
                self._config_repository.delete(pid)
            for provider in config.providers:
                self._config_repository.save(provider)
            self._config_repository.save_embedding_config(
                EmbeddingConfig(
                    provider_id=config.embedding.provider_id,
                    model=config.embedding.model,
                )
            )
        except Exception:
            logger.exception("settings_controller_db_save_failed")
            return False
        return True

    def save_providers_config_to_standard_path(self, config: ProvidersConfig) -> bool:
        """Save providers config to DB (primary) then to YAML (backup), then reload registry.

        DB is the authoritative write target; YAML write failure is non-fatal.

        Args:
            config: The ProvidersConfig to serialize and save.

        Returns:
            True if the DB write succeeded; False if the DB write failed.
        """
        db_ok = self._save_config_to_db(config)
        ok = self.save_providers_yaml(self._providers_yaml_path, config)
        if not ok:
            logger.warning("providers_yaml_backup_failed", extra={"path": str(self._providers_yaml_path)})
        try:
            self._provider_registry.reload()
        except Exception:
            logger.warning("provider_registry_reload_after_save_failed")
        self._event_bus.emit_provider_registry_reloaded(ProviderRegistryReloadedEvent())
        return db_ok

    def get_provider_instance(self, provider_id: str) -> LLMProviderApi | None:
        """Return the live provider instance for provider_id, or None if not found.

        Args:
            provider_id: ID of the provider to retrieve.

        Returns:
            Live LLMProviderApi instance, or None if the provider_id is unknown.
        """
        try:
            return self._provider_registry.get_provider(provider_id)
        except ProviderNotFoundError:
            return None

    def is_embedding_model(self, model_name: str) -> bool:
        """Return True if model_name matches a known embedding-model pattern.

        Args:
            model_name: The model name string to classify.

        Returns:
            True if the name matches a known embedding pattern.
        """
        return self._embedding_classifier.is_embedding_model(model_name)

    def set_last_test_status(self, provider_id: str, status: str, tested_at: str, message: str) -> None:
        """Persist the last health-check result for a provider.

        Args:
            provider_id: Provider to update.
            status: Health status string (e.g. "healthy" or "down").
            tested_at: ISO-8601 UTC timestamp of the test.
            message: Human-readable result message.
        """
        if self._config_repository is None:
            return
        try:
            self._config_repository.set_last_test_status(provider_id, status, tested_at, message)
        except Exception:
            logger.warning("set_last_test_status_failed", extra={"provider_id": provider_id})

    def subscribe_to_provider_registry_reloaded(
        self,
        callback: Callable[[], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """Subscribe callback to provider-registry reload events.

        Args:
            callback: Function to invoke when the registry is reloaded.
        """
        self._event_bus.subscribe_to_provider_registry_reloaded(lambda _event: callback(), parent=parent)

    def subscribe_to_app_readiness_changed(
        self,
        callback: Callable[[AppReadinessChangedEvent], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """Subscribe to app readiness changed events.

        Args:
            callback: Function to invoke with the new readiness snapshot.
        """
        self._event_bus.subscribe_to_app_readiness_changed(callback, parent=parent)

    def get_default_provider_config(self, provider_id: str) -> ProviderConfig | None:
        """Return the YAML default config for provider_id, or None if not found.

        Reads from providers_yaml_path if it exists. Returns None if the file is
        absent (e.g. after first-run migration rename) or provider_id is not found.

        Args:
            provider_id: ID of the provider to look up in the YAML defaults.

        Returns:
            ProviderConfig from YAML defaults, or None if absent.
        """
        if not self._providers_yaml_path.exists():
            return None
        try:
            defaults = self._provider_config_loader.load(self._providers_yaml_path)
            return next((p for p in defaults.providers if p.provider_id == provider_id), None)
        except Exception:
            logger.warning("get_default_provider_config_failed", extra={"provider_id": provider_id})
            return None
