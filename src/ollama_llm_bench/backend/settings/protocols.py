"""``SettingsService`` and ``RunSnapshotBuilder`` — the two independently-injected
settings Protocols.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§8 (Settings Service) and §8a (Run Snapshot Builder); resolution mechanics in
``docs/v3_specification/08_Cross_Cutting/08-C_settings_hierarchy.md``.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import BenchmarkRun, SettingKey
from ollama_llm_bench.backend.settings.models import RunSettingsSnapshot

__all__: list[str] = [
    "RunSnapshotBuilder",
    "SettingsService",
]


class SettingsService(Protocol):
    """Typed access to the three-layer settings hierarchy (`08-C` §2-3).

    Every read resolves ``Per-Run Snapshot -> User-Saved -> Default`` for a
    per-run-overridable key read with a ``run``, or ``User-Saved -> Default``
    otherwise. Only the user-saved layer is mutable through this service — there
    is no API to mutate a snapshot after a run exists.
    """

    def get_str(self, key: SettingKey, run: BenchmarkRun | None = None) -> str:
        """Resolve a string setting.

        Args:
            key: The dotted registry key to resolve.
            run: When given and ``key`` is per-run-overridable, its frozen
                settings snapshot is consulted first.

        Returns:
            The resolved value; never absent (the default layer is a total
            floor over the registry).

        Raises:
            ConfigurationError: ``key`` is not a member of the registry.
        """
        ...

    def get_bool(self, key: SettingKey, run: BenchmarkRun | None = None) -> bool:
        """Resolve a boolean setting.

        An unknown key raises ``ConfigurationError``. A non-coercible
        user-saved value is treated as absent: the in-code default is returned
        and a warning is logged naming the key (SPEC-110). A non-coercible
        per-run snapshot value is a ``ProgrammerError`` — snapshots are
        app-written from validated input and cannot legitimately be malformed.

        Args:
            key: The dotted registry key to resolve.
            run: When given and ``key`` is per-run-overridable, its frozen
                settings snapshot is consulted first.

        Returns:
            The resolved value; never absent.

        Raises:
            ConfigurationError: ``key`` is not a member of the registry.
        """
        ...

    def get_int(self, key: SettingKey, run: BenchmarkRun | None = None) -> int:
        """Resolve an integer setting. Same coercion-failure rule as ``get_bool``.

        Args:
            key: The dotted registry key to resolve.
            run: When given and ``key`` is per-run-overridable, its frozen
                settings snapshot is consulted first.

        Returns:
            The resolved value; never absent.

        Raises:
            ConfigurationError: ``key`` is not a member of the registry.
        """
        ...

    def get_float(self, key: SettingKey, run: BenchmarkRun | None = None) -> float:
        """Resolve a float setting. Same coercion-failure rule as ``get_bool``.

        Args:
            key: The dotted registry key to resolve.
            run: When given and ``key`` is per-run-overridable, its frozen
                settings snapshot is consulted first.

        Returns:
            The resolved value; never absent.

        Raises:
            ConfigurationError: ``key`` is not a member of the registry.
        """
        ...

    def set(self, key: SettingKey, value: str) -> None:
        """Write one value to the user-saved layer and emit the changed-keys event.

        Args:
            key: The dotted registry key to write.
            value: The registry storage-form string to persist.

        Raises:
            ConfigurationError: ``key`` is not a member of the registry.
            PersistenceError: The underlying write failed.
        """
        ...

    def upsert(self, values: dict[SettingKey, str]) -> None:
        """Write several values to the user-saved layer atomically.

        Every key in ``values`` is validated against the registry before
        anything is written; an unknown key anywhere in the mapping aborts the
        whole call with no partial write. Exactly one changed-keys event is
        emitted afterward, carrying the keys passed to this call (not a diff
        against prior values).

        Args:
            values: The registry-keyed values to write.

        Raises:
            ConfigurationError: Any key in ``values`` is not a member of the
                registry.
            PersistenceError: The underlying write failed.
        """
        ...


class RunSnapshotBuilder(Protocol):
    """Capture the frozen settings snapshot for a new run (`08-C` §5; `08-E` §8a).

    Deliberately separate from ``SettingsService`` so the benchmark pipeline's
    run-creation use case, which only ever needs the snapshot, is not exposed
    to the broader typed-read/typed-write surface. Both Protocols live in this
    package and may share an internal resolver, but each is independently
    injected — neither depends on the other's public surface.
    """

    def build_snapshot(self) -> RunSettingsSnapshot:
        """Capture the resolved value of every per-run-overridable key.

        Each key in ``PER_RUN_OVERRIDABLE`` is resolved through the
        ``User-Saved -> Default`` cascade (as if reading with ``run=None``)
        before any New Benchmark form override is applied — that overlay is
        the run-creation use case's own later step, not this builder's.

        Returns:
            A frozen tuple containing exactly one ``BenchmarkRunSettingEntry``
            for every key in ``PER_RUN_OVERRIDABLE`` — never more, never
            fewer, and no key outside that set.

        Raises:
            PersistenceError: The underlying user-saved-layer read failed.
        """
        ...
