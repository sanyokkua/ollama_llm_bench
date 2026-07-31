"""The ``ProvidersStore`` contract owned by this module.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7.4.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderConfigDraft, ProviderId

__all__: list[str] = [
    "ProvidersStore",
]


class ProvidersStore(Protocol):
    """The provider catalog. Owns ``provider_id`` generation (DD-33).

    fast-synchronous: every method is a quick SQLite read/write under WAL and
    may be called from either the GUI thread or the dispatcher thread.
    """

    def list_providers(self) -> tuple[ProviderConfig, ...]:
        """Return every configured provider in display order, each with its
        manual model list.

        Raises:
            PersistenceError: The underlying read failed.
        """
        ...

    def get_by_name(self, name: str) -> ProviderConfig | None:
        """Return the provider whose ``name`` matches ``name``, or ``None``
        when no provider in the catalog has that name. Used by the Provider
        Edit sub-dialog and the importer to pre-check duplicate names before
        attempting ``add`` / ``update``.

        Raises:
            PersistenceError: The underlying read failed.
        """
        ...

    def add(self, draft: ProviderConfigDraft) -> ProviderId:
        """Insert a new provider. The store generates the ``provider_id``
        UUID4 on insert and returns it only after commit.

        Raises:
            PersistenceError: A row with ``draft.name`` already exists (the
                ``UNIQUE`` constraint is the backstop; ``get_by_name`` is the
                caller's friendly-error pre-check), or the underlying write
                failed.
        """
        ...

    def update(self, provider_id: ProviderId, config: ProviderConfig) -> None:
        """Update an existing provider. ``provider_id`` is immutable — every
        other column (including ``name``) on the matching row is updated.

        Raises:
            PersistenceError: No row with ``provider_id`` exists, the update
                would duplicate another row's ``name``, or the underlying
                write failed.
        """
        ...

    def delete(self, provider_id: ProviderId) -> None:
        """Delete the provider with the given internal id. Cascades to its
        ``provider_models`` and ``model_capabilities`` rows. Run-history rows
        are unaffected (the ``provider_id`` link is logical, not a FK; the
        run keeps its snapshot per DD-33).

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...

    def replace_providers(self, configs: tuple[ProviderConfig, ...]) -> None:
        """Replace the entire provider catalog atomically. Used by the
        Settings dialog's Save flow and the import flow.

        Raises:
            PersistenceError: ``configs`` contains a duplicate ``name``, or
                the underlying write failed.
        """
        ...

    def replace_providers_in_open_transaction(self, configs: tuple[ProviderConfig, ...]) -> None:
        """Replace the entire provider catalog against an already-open transaction.

        Must be called only by a caller that already holds the write lock
        and has an open transaction on the shared write connection --
        used exclusively by ``backend.settings``'s ``SettingsAtomicWriter``.
        Ordinary callers use ``replace_providers`` instead.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...
