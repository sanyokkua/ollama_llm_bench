"""``SettingsGateway`` Protocol (D-R-06), based on 08-E §7b.6 and extended by
STORY-067.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.6. The 13 methods declared there cover the Providers tab and General tab's
read/write surface (``list_providers``, ``get_provider_by_name``,
``test_provider``, ``discover_models``, ``probe_all``, ``readiness_snapshot``,
``get_setting``/``list_settings``, ``replace_providers``, ``upsert_settings``,
``get_resolved_str``, ``list_model_capabilities``, ``upsert_model_capability``,
``probe_embedding``) -- but 08-E §7b.6 lists **zero** Import/Export methods, a
confirmed spec gap (STORY-067 plan's "Resolved design gap" section; see the
story's own Notes). ``backend.import_export.protocols.ImportExportService``
already implements exactly what Import/Export needs but is never listed among
the seven 08-E §7b UI gateways, and ``ui/settings_dialog`` cannot import
``backend.import_export`` directly (outside the ``ui/*`` import-boundary
allow-list). STORY-067 therefore extends this Protocol with six methods
shaped after ``ImportExportService``'s real signatures
(``build_settings_import_preview``, ``apply_settings_import``,
``build_provider_import_preview``, ``apply_provider_import``,
``export_settings``, ``export_providers``), returning the locally-redeclared
DTOs in ``.models`` rather than ``backend.import_export.models``.

**Atomic Save/Reset (spec-conformance amendment).** Save and Reset each span
two independent stores (``ProvidersStore``/``AppSettingsStore``); calling
``replace_providers`` then ``upsert_settings`` as two independent Gateway
calls cannot express "all-or-nothing" -- a failure after the first call
commits leaves the two stores inconsistent. ``save_all``/``reset_to_defaults``
below give the concrete Phase 11 adapter a single call to wrap in one real
database transaction, making true atomicity possible where two void calls
could not; this UI module cannot enforce the concrete adapter's transaction
itself, but the Protocol's shape is what makes it possible.
"""

from typing import TYPE_CHECKING, Protocol

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    InferenceTestResult,
    ModelCapabilityRecord,
    ModelName,
    ProviderConfig,
    ProviderId,
    SettingKey,
)

if TYPE_CHECKING:
    # Deferred to break the models.py <-> protocols.py cycle: models.py needs
    # SettingsGateway as a real runtime type (a msgspec.Struct field
    # annotation), so protocols.py cannot import models.py eagerly. These four
    # names are used only as quoted (forward-reference) annotations below.
    from ollama_llm_bench.ui.settings_dialog.models import (
        ProviderImportPreview,
        ProviderImportResult,
        SettingsImportPreview,
        SettingsImportResult,
    )

__all__: list[str] = ["SettingsGateway"]


class SettingsGateway(Protocol):
    """Adapter gateway for the Settings Dialog (D-R-06)."""

    def list_providers(self) -> tuple[ProviderConfig, ...]:
        """Read the provider catalog for the Providers tab.

        fast-synchronous.
        """
        ...

    def get_provider_by_name(self, name: str) -> ProviderConfig | None:
        """Look up a provider by display name for live duplicate-name validation.

        fast-synchronous.
        """
        ...

    def replace_providers(self, configs: tuple[ProviderConfig, ...]) -> None:
        """Replace the entire provider catalog atomically (Save / Import / Reset).

        blocking.
        """
        ...

    def get_setting(self, key: SettingKey) -> str | None:
        """Read one user-saved setting, including the embedding selection keys
        (``embedding.selected_provider_name`` / ``embedding.selected_model_name``).

        fast-synchronous.
        """
        ...

    def list_settings(self) -> dict[SettingKey, str]:
        """Read the full user-saved settings row set for the working copy.

        fast-synchronous.
        """
        ...

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        """Write several settings atomically (the settings half of Save / Reset).

        blocking.
        """
        ...

    def get_resolved_str(self, key: SettingKey) -> str:
        """Resolve the current effective value of a general-tab key (initial copy).

        fast-synchronous.
        """
        ...

    def list_model_capabilities(
        self, provider_id: ProviderId, model_name: ModelName
    ) -> tuple[ModelCapabilityRecord, ...]:
        """Read cached capability records for a model (capability hints).

        fast-synchronous.
        """
        ...

    def upsert_model_capability(self, record: ModelCapabilityRecord) -> None:
        """Persist a user-overridden capability record.

        blocking.
        """
        ...

    def test_provider(self, provider_id: ProviderId, model_name: ModelName) -> InferenceTestResult:
        """Run the per-row Test-connection inference probe for a provider/model.

        blocking; acquires the ``PROVIDER_TEST`` single-inference gate.
        """
        ...

    def discover_models(self, provider_id: ProviderId) -> tuple[ModelName, ...]:
        """Discover a provider's models for the embedding-section picker.

        blocking.
        """
        ...

    def probe_all(self) -> AppReadinessSnapshot:
        """Run the auto-check on open; emits readiness-changed.

        blocking.
        """
        ...

    def probe_embedding(self) -> AppReadinessSnapshot:
        """Run the Test-Embedding probe behind the embedding section.

        blocking; acquires the ``PROVIDER_TEST`` single-inference gate.
        """
        ...

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        """Read the current snapshot for the Health Dots.

        fast-synchronous.
        """
        ...

    def build_settings_import_preview(self, file_path: str) -> "SettingsImportPreview":
        """Parse and fully validate a settings YAML file into a preview.

        blocking (file I/O + parse); routed by the concrete Phase 11 adapter to
        ``backend.import_export.ImportExportService.build_settings_import_preview``
        on a ``TaskRunner`` worker thread -- this Protocol method's own call site
        may be invoked directly from the controller exactly like the existing
        ``test_provider``/``probe_all`` methods; the threading marshalling is the
        concrete adapter's responsibility (D-R-06), not this UI module's.

        Args:
            file_path: The absolute path chosen via ``NativePickers.open_file``.

        Returns:
            The full validated preview; nothing is written yet.

        Raises:
            TaskFileError: The file could not be parsed at all.
            ConfigurationError: A schema-shape hard error aborted the import.
        """
        ...

    def apply_settings_import(self, preview: "SettingsImportPreview") -> "SettingsImportResult":
        """Write a confirmed settings-import preview's resolved values.

        blocking; merges -- only ``preview.resolved_values`` keys are written.

        Args:
            preview: A preview previously returned by
                ``build_settings_import_preview`` and confirmed by the user.

        Returns:
            The count of keys applied and skipped.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...

    def build_provider_import_preview(self, file_path: str) -> "ProviderImportPreview":
        """Parse and fully validate a provider-configuration YAML file into a preview.

        blocking (file I/O + parse).

        Args:
            file_path: The absolute path chosen via ``NativePickers.open_file``.

        Returns:
            The full validated preview; nothing is written yet.

        Raises:
            TaskFileError: The file could not be parsed at all.
            ConfigurationError: A schema-shape hard error aborted the import
                (duplicate name within the file, unmatched embedding provider,
                every entry dropped).
        """
        ...

    def apply_provider_import(self, preview: "ProviderImportPreview") -> "ProviderImportResult":
        """Replace the provider registry wholesale with a confirmed preview.

        blocking; this is a **replace**, not a merge.

        Args:
            preview: A preview previously returned by
                ``build_provider_import_preview`` and confirmed by the user.

        Returns:
            The count of providers applied and skipped.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...

    def export_settings(self) -> bytes:
        """Serialize every user-saved setting to the canonical settings YAML.

        blocking. The disk write itself is owned by ``FileSystemActions``/
        ``NativePickers`` at the dialog level -- this call returns the payload only.

        Returns:
            The UTF-8-encoded YAML document.

        Raises:
            PersistenceError: The underlying read failed.
        """
        ...

    def export_providers(self) -> bytes:
        """Serialize the provider catalog and embedding selection to YAML.

        blocking. ``provider_id`` never appears in the payload (DD-33).

        Returns:
            The UTF-8-encoded YAML document.

        Raises:
            PersistenceError: The underlying read failed.
        """
        ...

    def save_all(
        self, *, providers: tuple[ProviderConfig, ...], settings_values: dict[SettingKey, str]
    ) -> None:
        """Commit the working provider catalog and settings values in one
        atomic transaction (``description.md`` §6; STORY-067-AC-3).

        blocking. All-or-nothing: the concrete Phase 11 adapter wraps both the
        ``ProvidersStore.replace_providers`` write and the
        ``AppSettingsStore.upsert_settings`` write in one real database
        transaction. On failure, neither store is modified -- this is a
        contract the concrete adapter must honor; this Protocol method's
        single-call shape is what makes that atomicity possible, where two
        independent void calls (``replace_providers`` then
        ``upsert_settings``) could not express "all-or-nothing".

        Args:
            providers: The full working provider catalog to persist.
            settings_values: The full General-tab working-copy value map to
                merge into ``AppSettingsStore`` (the settings half of Save).

        Raises:
            PersistenceError: The underlying write failed; neither store was
                modified.
        """
        ...

    def reset_to_defaults(self, *, bundled_providers: tuple[ProviderConfig, ...]) -> None:
        """Wipe and re-seed the whole configuration in one atomic transaction
        (``sub_dialogs/reset_confirmation.md`` §4, §6, §7; STORY-067-AC-5).

        blocking. All-or-nothing: the concrete Phase 11 adapter deletes every
        ``providers`` and ``app_settings`` row, then re-seeds
        ``bundled_providers`` and re-seeds **every** ``app_settings`` key to
        its in-code default -- not only the General tab's own registry keys.
        The exhaustive in-code defaults table already exists as
        ``backend.settings._internal.registry.DEFAULTS`` (currently
        ``_internal``-only, not part of ``backend.settings``'s public
        surface); the concrete adapter is expected to reseed against that
        table (or an equivalent it promotes to a public export), covering
        every opaque UI-state key (``ui.window_geometry``,
        ``benchmark.last_mode``, ``ui.splitter_sizes``, etc.) this UI module
        has no visibility into -- this UI module supplies only the bundled
        provider drafts; it is not able to enumerate the full settings
        registry itself.

        Args:
            bundled_providers: The three freshly-seeded bundled local
                providers (``sub_dialogs/reset_confirmation.md`` §6).

        Raises:
            PersistenceError: The underlying write failed; the prior
                configuration is left intact.
        """
        ...
