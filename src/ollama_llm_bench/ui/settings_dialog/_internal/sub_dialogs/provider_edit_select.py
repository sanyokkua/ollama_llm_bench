"""Pure derivation functions for the Provider Edit sub-dialog (STORY-066).

Zero Qt involvement -- directly unit-testable with no ``QApplication``. Source of
truth: ``docs/v3_specification/06_Settings_Dialog/sub_dialogs/provider_edit.md``
§5.1 (env-var-name entry validation), §5.2 (diagnostic), §8.2 (inference-test
gating), §9 (Name-uniqueness validation).
"""

import re

from ollama_llm_bench.backend.domain import InferenceActivity

__all__: list[str] = [
    "DUPLICATE_NAME_MESSAGE",
    "duplicate_name_conflict",
    "env_var_diagnostic",
    "env_var_name_error",
    "gate_button_state",
    "is_valid_env_var_name_or_empty",
    "run_inference_test_enabled",
]

_ENV_VAR_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_INVALID_ENV_VAR_MESSAGE = (
    "Enter the NAME of an environment variable that holds the key "
    "(e.g. OPENAI_API_KEY) — not the key itself."
)
DUPLICATE_NAME_MESSAGE = "A provider with this name already exists."
_GATE_BUSY_TOOLTIP = "Another inference activity is in flight — please wait."
_NO_MODEL_TOOLTIP = "Select or type a model name first."


def is_valid_env_var_name_or_empty(value: str) -> bool:
    """Return whether `value` is a valid environment-variable name, or empty (§5.1).

    Args:
        value: The raw text currently typed into the API-key secret card.

    Returns:
        ``True`` when `value` is empty or matches ``[A-Za-z_][A-Za-z0-9_]*``.
    """
    return value == "" or bool(_ENV_VAR_NAME_PATTERN.match(value))


def env_var_name_error(value: str) -> str | None:
    """Return the API-key field's inline error message, or ``None`` when valid.

    Args:
        value: The raw text currently typed into the API-key secret card.

    Returns:
        The §5.1 guidance string when `value` is neither empty nor a valid
        environment-variable name; ``None`` otherwise.
    """
    if is_valid_env_var_name_or_empty(value):
        return None
    return _INVALID_ENV_VAR_MESSAGE


def env_var_diagnostic(*, name: str, resolved: bool) -> str:
    """Render the API-key field's one-line env-var diagnostic (§5.2).

    Args:
        name: The current API-key field text.
        resolved: Whether the named variable currently resolves to a
            non-empty value in the process environment. Ignored when `name`
            is empty or is not itself a valid variable name.

    Returns:
        ``""`` for an empty name, the §5.1 error text for an invalid name,
        ``"✓ resolved <redacted>"`` when set and resolving, or ``"⚠ not set"``
        when named but unresolved.
    """
    if name == "":
        return ""
    if not is_valid_env_var_name_or_empty(name):
        return "✗ name invalid"
    return "✓ resolved <redacted>" if resolved else "⚠ not set"


def duplicate_name_conflict(
    *,
    name: str,
    editing_provider_id: str | None,
    other_working_names: tuple[str, ...],
    persisted_match_provider_id: str | None,
) -> bool:
    """Decide whether `name` collides with another provider (§9; EC-PROV-10/11).

    Args:
        name: The Name field's current (not-yet-trimmed) text.
        editing_provider_id: The row being edited's id, or ``None`` for Add.
        other_working_names: Every other working row's current Name.
        persisted_match_provider_id: The `provider_id` of the persisted row
            `SettingsGateway.get_provider_by_name` returned for the trimmed
            name, or ``None`` when no persisted row shares that name.

    Returns:
        ``True`` when the trimmed name is non-empty and collides with either
        a working row's name or a persisted row that is not the row itself.
    """
    trimmed = name.strip()
    if not trimmed:
        return False
    if trimmed in other_working_names:
        return True
    return (
        persisted_match_provider_id is not None
        and persisted_match_provider_id != editing_provider_id
    )


def gate_button_state(activity: InferenceActivity) -> tuple[bool, str]:
    """Derive the Test reachability / Test inference buttons' gate-driven
    ``(enabled, tooltip)`` pair (§8.4; EC-PROV-5b), before any other rule.

    Args:
        activity: The single-inference gate's current holder.

    Returns:
        ``(True, "")`` when the gate is free or held by this dialog's own
        ``PROVIDER_TEST`` activity; ``(False, <tooltip>)`` otherwise.
    """
    if activity in (InferenceActivity.IDLE, InferenceActivity.PROVIDER_TEST):
        return True, ""
    return False, _GATE_BUSY_TOOLTIP


def run_inference_test_enabled(
    *,
    dropdown_model: str | None,
    manual_entry_enabled: bool,
    manual_text: str,
    gate_activity: InferenceActivity,
) -> tuple[bool, str]:
    """Derive the Run inference test button's ``(enabled, tooltip)`` pair
    (§8.2; STORY-066-AC-4, AC-5; EC-PROV-5b, EC-PROV-5c).

    Args:
        dropdown_model: The model dropdown's current selection, or ``None``.
        manual_entry_enabled: Whether "Enter model name manually" is checked.
        manual_text: The manual-entry input's current text.
        gate_activity: The single-inference gate's current holder.

    Returns:
        ``(False, <gate tooltip>)`` when the gate is held by a foreign
        activity; ``(False, <no-model tooltip>)`` when no model is named;
        ``(True, "")`` otherwise.
    """
    gate_ok, gate_tooltip = gate_button_state(gate_activity)
    if not gate_ok:
        return False, gate_tooltip
    model_named = bool(manual_text.strip()) if manual_entry_enabled else dropdown_model is not None
    if not model_named:
        return False, _NO_MODEL_TOOLTIP
    return True, ""
