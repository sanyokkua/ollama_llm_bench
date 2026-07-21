"""The cross-tab validation cascade (``06_Settings_Dialog/description.md`` §15).

Runs across both tabs before a Save commits; producing the hard-error / soft-
warning findings and computing Save enablement.
"""

import os

from ollama_llm_bench.backend.domain import ProviderConfig, SettingKey
from ollama_llm_bench.ui.settings_dialog._internal.general_tab.field_binders import (
    FIELD_REGISTRY,
    validate_stored_text,
)
from ollama_llm_bench.ui.settings_dialog.models import Severity, ValidationFinding

__all__: list[str] = ["save_enabled", "validate_all"]

# (min key, max key, the max field's display label) -- description.md §15.1's two
# timeout-pair hard-error rules.
_TIMEOUT_PAIRS: tuple[tuple[SettingKey, SettingKey, str], ...] = (
    (
        "benchmark.min_timeout_seconds",
        "benchmark.max_timeout_seconds",
        "Inference timeout — maximum (seconds)",
    ),
    (
        "eval.judge_timeout_min_seconds",
        "eval.judge_timeout_max_seconds",
        "Judge timeout — maximum (seconds)",
    ),
)


def _duplicate_name_findings(
    providers: tuple[ProviderConfig, ...],
) -> tuple[ValidationFinding, ...]:
    seen: dict[str, int] = {}
    for provider in providers:
        seen[provider.name] = seen.get(provider.name, 0) + 1
    return tuple(
        ValidationFinding(
            severity=Severity.HARD_ERROR,
            target=f"providers[{provider.name}].name",
            message="A provider with this name already exists.",
        )
        for provider in providers
        if seen[provider.name] > 1
    )


def _missing_env_findings(providers: tuple[ProviderConfig, ...]) -> tuple[ValidationFinding, ...]:
    return tuple(
        ValidationFinding(
            severity=Severity.SOFT_WARNING,
            target=f"providers[{provider.name}].api_key_raw",
            message=f"Environment variable '{provider.api_key_raw}' is not currently set.",
        )
        for provider in providers
        if provider.api_key_raw and not os.environ.get(provider.api_key_raw)
    )


def _general_field_findings(general_values: dict[SettingKey, str]) -> tuple[ValidationFinding, ...]:
    # A key absent from `general_values` is not validated here -- the caller
    # (GeneralTabController.values_for_save()) always supplies every registry
    # key in production; a caller validating a narrower subset (e.g. a
    # focused test) gets findings scoped to only the keys it passed.
    findings: list[ValidationFinding] = []
    for spec in FIELD_REGISTRY:
        if spec.setting_key not in general_values:
            continue
        finding = validate_stored_text(spec, general_values[spec.setting_key])
        if finding is not None:
            findings.append(finding)
    return tuple(findings)


def _timeout_pair_findings(general_values: dict[SettingKey, str]) -> tuple[ValidationFinding, ...]:
    findings: list[ValidationFinding] = []
    for min_key, max_key, max_label in _TIMEOUT_PAIRS:
        min_text, max_text = general_values.get(min_key, ""), general_values.get(max_key, "")
        if not min_text or not max_text:
            continue  # already reported by _general_field_findings (EC-SET-3)
        try:
            if int(max_text) < int(min_text):
                findings.append(
                    ValidationFinding(
                        severity=Severity.HARD_ERROR,
                        target=max_key,
                        message=f"{max_label} must not be less than the minimum.",
                    )
                )
        except ValueError:
            continue  # already reported by _general_field_findings
    return tuple(findings)


def validate_all(
    *, providers: tuple[ProviderConfig, ...], general_values: dict[SettingKey, str]
) -> tuple[ValidationFinding, ...]:
    """Run the full cross-tab validation cascade (STORY-067-AC-2).

    Args:
        providers: The working provider catalog (Providers tab).
        general_values: The working General-tab value map, keyed by registry
            setting key.

    Returns:
        Every hard-error/soft-warning finding across both tabs, in no
        particular order; empty when nothing is wrong.
    """
    return (
        _duplicate_name_findings(providers)
        + _missing_env_findings(providers)
        + _general_field_findings(general_values)
        + _timeout_pair_findings(general_values)
    )


def save_enabled(findings: tuple[ValidationFinding, ...], *, is_dirty: bool) -> bool:
    """Whether Save Changes should be enabled (STORY-067-AC-2).

    Args:
        findings: The cascade's full finding set (from ``validate_all``).
        is_dirty: Whether the dialog currently has any unsaved edit.

    Returns:
        ``True`` only when the dialog is dirty and no ``HARD_ERROR`` finding
        exists; soft warnings never block Save.
    """
    has_hard_error = any(finding.severity is Severity.HARD_ERROR for finding in findings)
    return is_dirty and not has_hard_error
