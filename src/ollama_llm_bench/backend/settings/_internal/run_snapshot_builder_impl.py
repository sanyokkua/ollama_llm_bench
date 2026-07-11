"""Concrete ``RunSnapshotBuilder`` implementation.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-C_settings_hierarchy.md``
§5; ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md`` §8a.
"""

from ollama_llm_bench.backend.domain import BenchmarkRunSettingEntry
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.settings._internal.registry import PER_RUN_OVERRIDABLE
from ollama_llm_bench.backend.settings._internal.resolver import resolve_typed
from ollama_llm_bench.backend.settings.models import RunSettingsSnapshot


class RunSnapshotBuilderImpl:
    """Captures the frozen ``User-Saved -> Default`` snapshot at run creation.

    Iterates every key in ``PER_RUN_OVERRIDABLE`` and resolves each with
    ``run=None``, so the snapshot layer is never consulted while building
    itself — this is the base snapshot the run-creation use case later
    overlays with the New Benchmark form's per-run overrides (out of this
    module's scope, `08-C` §5 step 2).
    """

    def __init__(self, *, store: AppSettingsStore) -> None:
        self._store = store

    def build_snapshot(self) -> RunSettingsSnapshot:
        """Capture every per-run-overridable key. See ``RunSnapshotBuilder.build_snapshot``."""
        return tuple(
            BenchmarkRunSettingEntry(
                setting_key=key,
                setting_value=resolve_typed(key, None, self._store, str),
            )
            for key in sorted(PER_RUN_OVERRIDABLE)
        )
