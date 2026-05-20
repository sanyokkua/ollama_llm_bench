"""SQLite-backed implementation of ProviderConfigRepositoryApi for provider configuration storage."""

import logging

from ollama_llm_bench.backend.core.interfaces import DataApi
from ollama_llm_bench.backend.core.models import EmbeddingConfig, ProviderConfig

logger = logging.getLogger(__name__)


class SqliteProviderConfigRepository:
    """Thin adapter that exposes ProviderConfigRepositoryApi over DataApi.

    Implements ProviderConfigRepositoryApi structurally (Protocol).
    All persistence is delegated to the shared DataApi instance so that
    provider rows live in the same SQLite file as benchmark data.
    """

    def __init__(self, *, data_api: DataApi) -> None:
        """Initialize the repository with a shared DataApi.

        Args:
            data_api: The application-wide DataApi instance (e.g. SqLiteDataApi).
        """
        self._data_api = data_api

    def count(self) -> int:
        """Return the number of stored provider rows.

        Returns:
            Row count; 0 if the table is empty.
        """
        return self._data_api.count_providers()

    def load_all(self) -> list[ProviderConfig]:
        """Load all provider rows from persistent storage.

        Returns:
            List of ProviderConfig instances; empty list if no rows exist.
        """
        return self._data_api.load_all_providers()

    def save(self, provider: ProviderConfig) -> None:
        """Persist a provider, inserting or replacing the existing row.

        Args:
            provider: ProviderConfig instance to persist.
        """
        self._data_api.upsert_provider(provider)

    def delete(self, provider_id: str) -> None:
        """Remove a provider row by its identifier.

        Args:
            provider_id: The unique provider ID to delete.
        """
        self._data_api.delete_provider(provider_id)

    def load_embedding_config(self) -> EmbeddingConfig | None:
        """Load the singleton embedding config row.

        Returns:
            EmbeddingConfig if the row exists, None otherwise.
        """
        return self._data_api.load_embedding_config()

    def save_embedding_config(self, config: EmbeddingConfig) -> None:
        """Persist the singleton embedding config row.

        Args:
            config: EmbeddingConfig instance to persist.
        """
        self._data_api.upsert_embedding_config(config)

    def replace_all(self, providers: list[ProviderConfig]) -> None:
        """Replace all stored provider rows with the given list atomically.

        Args:
            providers: Replacement list of ProviderConfig instances.
        """
        self._data_api.replace_all_providers(providers)

    def set_last_test_status(self, provider_id: str, status: str, tested_at: str, message: str) -> None:
        """Persist the last health-check result for a provider.

        Args:
            provider_id: Provider to update.
            status: Health status string (e.g. "healthy" or "down").
            tested_at: ISO-8601 UTC timestamp of the test.
            message: Human-readable result message.
        """
        self._data_api.update_provider_test_status(provider_id, status, tested_at, message)
