"""SettingsService + RunSnapshotBuilder Protocols.

Resolves every setting read through the three-layer cascade (per-run snapshot, then
user-saved, then in-code default) and builds the frozen per-run-overridable snapshot
captured at run start.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-C_settings_hierarchy.md``;
``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md`` §8, §8a;
``docs/v3_specification/08_Cross_Cutting/08-G_feature_flags.md`` §3-9.
"""

from ollama_llm_bench.backend.settings.api import (
    DEFAULTS,
    PER_RUN_OVERRIDABLE,
    RunSnapshotBuilder,
    SettingsAtomicWriter,
    SettingsService,
    make_run_snapshot_builder,
    make_settings_atomic_writer,
    make_settings_service,
)
from ollama_llm_bench.backend.settings.models import BenchmarkRunSettingEntry, RunSettingsSnapshot

__all__: list[str] = [
    "DEFAULTS",
    "PER_RUN_OVERRIDABLE",
    "BenchmarkRunSettingEntry",
    "RunSettingsSnapshot",
    "RunSnapshotBuilder",
    "SettingsAtomicWriter",
    "SettingsService",
    "make_run_snapshot_builder",
    "make_settings_atomic_writer",
    "make_settings_service",
]
