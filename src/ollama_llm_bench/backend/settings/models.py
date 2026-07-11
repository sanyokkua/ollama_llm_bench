"""Module-owned type aliases for the settings hierarchy.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§8a and ``08_Cross_Cutting/08-C_settings_hierarchy.md`` §5. ``BenchmarkRunSettingEntry``
itself is owned by ``backend/domain`` (STORY-001) and is re-exported here only for
caller convenience — it is never redefined.
"""

from ollama_llm_bench.backend.domain import BenchmarkRunSettingEntry

__all__: list[str] = [
    "BenchmarkRunSettingEntry",
    "RunSettingsSnapshot",
]

type RunSettingsSnapshot = tuple[BenchmarkRunSettingEntry, ...]
"""The frozen per-run settings snapshot captured at run creation (`08-C` §5): exactly
one ``BenchmarkRunSettingEntry`` for every key in ``PER_RUN_OVERRIDABLE``."""
