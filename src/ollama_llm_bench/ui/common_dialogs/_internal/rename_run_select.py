"""Pure V-1..V-5 validation for the Rename Run dialog (STORY-056-AC-6).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/rename_run_dialog.md``
§5 (Validation Rules). No Qt -- directly unit-testable.
"""

import unicodedata

__all__: list[str] = ["ValidationResult", "validate_name"]

_MAX_LENGTH = 80
_ALLOWED_PUNCTUATION = frozenset("_-.:()[]/ ")
_MAX_CONTROL_CHAR = 0x1F
_DEL_CHAR = 0x7F

_TOO_LONG_MESSAGE = "Name is too long (maximum 80 characters)."
_DISALLOWED_CHARACTERS_MESSAGE = "Name contains characters that are not allowed."


class ValidationResult:
    """The outcome of one live-validation pass over a trimmed candidate name.

    Attributes:
        is_valid: Whether the candidate may be committed (either a passing
            non-empty name, or the empty-input default-intent case).
        is_default_intent: Whether the trimmed input is empty -- committing
            now persists ``None`` rather than a custom name.
        message: The first failing rule's message, or ``None`` when valid.
    """

    def __init__(self, *, is_valid: bool, is_default_intent: bool, message: str | None) -> None:
        self.is_valid = is_valid
        self.is_default_intent = is_default_intent
        self.message = message


def validate_name(
    raw_input: str, *, existing_names: frozenset[str], excluded_run_id_name: str | None
) -> ValidationResult:
    """Validate a candidate run name per V-1..V-5 (rename_run_dialog.md §5).

    Args:
        raw_input: The unstripped text currently in the input field.
        existing_names: Every OTHER run's non-``None`` custom name, already
            lower-cased by the caller for the V-5 comparison, with the run
            being renamed's own current name already excluded.
        excluded_run_id_name: The run being renamed's own current custom
            name (also already lower-cased), documented so a future caller
            cannot forget to exclude it from ``existing_names`` -- unused
            directly here since the caller performs the exclusion.

    Returns:
        A ``ValidationResult``: empty trimmed input is default-intent
        (valid, commits ``None``); a non-empty trimmed value failing any
        rule is invalid with the first failing rule's message; otherwise
        valid.
    """
    del excluded_run_id_name  # documented caller contract only, see docstring
    trimmed = raw_input.strip()
    if not trimmed:
        return ValidationResult(is_valid=True, is_default_intent=True, message=None)
    if len(trimmed) > _MAX_LENGTH:
        return ValidationResult(is_valid=False, is_default_intent=False, message=_TOO_LONG_MESSAGE)
    if any(ord(ch) <= _MAX_CONTROL_CHAR or ord(ch) == _DEL_CHAR for ch in trimmed):
        return ValidationResult(
            is_valid=False, is_default_intent=False, message=_DISALLOWED_CHARACTERS_MESSAGE
        )
    if not _has_only_allowed_characters(trimmed):
        return ValidationResult(
            is_valid=False, is_default_intent=False, message=_DISALLOWED_CHARACTERS_MESSAGE
        )
    if trimmed.lower() in existing_names:
        return ValidationResult(
            is_valid=False,
            is_default_intent=False,
            message=f'A run named "{trimmed}" already exists.',
        )
    return ValidationResult(is_valid=True, is_default_intent=False, message=None)


def _has_only_allowed_characters(trimmed: str) -> bool:
    """V-4: Unicode letters, Unicode digits, space, or ``_-.:()[]/``."""
    for ch in trimmed:
        if ch in _ALLOWED_PUNCTUATION:
            continue
        category = unicodedata.category(ch)
        if not category.startswith(("L", "N")):
            return False
    return True
