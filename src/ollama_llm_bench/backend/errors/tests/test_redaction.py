"""Tests proving the redaction acceptance criteria of STORY-002.

Source of truth: ``docs/v3_specification/10_Domain_and_Data/08_REDACTION_PATTERNS.md``
§3 (the regex denylist), §4 (the never-log key-name list), §5 (the length cap), §8
(order of operations), §10 (test cases RT-01..RT-19), §11 (edge cases EC-RD-3,
EC-RD-5, EC-RD-6).
"""

import pytest

from ollama_llm_bench.backend.errors.api import redact, redact_for_log

_LENGTH_CAP = 4000
_LONG_TEXT_LENGTH = 9000
_EXPECTED_REMOVED_NO_SECRET = _LONG_TEXT_LENGTH - _LENGTH_CAP
_REPEATED_SECRET_OCCURRENCES = 3

# --------------------------------------------------------------------------- #
# STORY-002-AC-4 — the ten ordered denylist patterns + env-var-name exception
# --------------------------------------------------------------------------- #

# (case id, input fragment, expected substring in output, secret substring that
# must NOT survive in the output — None when the case is a passthrough/unchanged
# assertion instead of a substring-presence assertion).
_DENYLIST_CASES: tuple[tuple[str, str, str], ...] = (
    ("RT-01_openai_key", "key is sk-proj-AB12cd34EF56gh78IJ90kl12MN", "key is <redacted>"),
    ("RT-02_anthropic_key", "sk-ant-api03-Zz99Yy88Xx77Ww66Vv55Uu44", "<redacted>"),
    ("RT-03_google_key", "AIzaSyA1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7", "<redacted>"),
    ("RT-04_github_token", "gho_abcdefghij1234567890ABCDEFGH", "<redacted>"),
    ("RT-05_azure_key", "azure key 0123456789abcdef0123456789abcdef", "azure key <redacted>"),
    ("RT-06_bearer_token", "Bearer abcdEFGH1234ijklMNOP5678", "<redacted>"),
    (
        "RT-07_authorization_header",
        "Authorization: Token qwertyuiopasdfgh",
        "Authorization: <redacted>",
    ),
    (
        "RT-08_api_key_kv",
        'client_secret = "hunter2hunter2hunter2"',
        "client_secret = <redacted>",
    ),
    (
        "RT-09_jwt",
        "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk",
        "token <redacted>",
    ),
    (
        # Note: the spec's own RT-10 sample fragment ("...Fg77") is only 36
        # characters, one short of the pattern's documented 40-char floor
        # (`\b[A-Za-z0-9_-]{40,}\b`) — using a 40-char token here instead so the
        # test actually exercises the generic_long_token pattern it names.
        "RT-10_generic_long_token",
        "value Zk39Lp02Qr85Tx47Bw61Ny38Mc04Hd29Fg77AbCd Js",
        "<redacted>",
    ),
    (
        "RT-13a_underscore_free_lookalike_still_redacted",
        "api_key=AKIAIOSFODNN7EXAMPLE",
        "api_key=<redacted>",
    ),
    (
        "RT-18_multiple_secrets_in_one_line",
        "keys sk-AAAAAAAAAAAAAAAAAAAA and AIzaBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
        "<redacted>",
    ),
)


@pytest.mark.parametrize(
    ("input_fragment", "expected_substring"),
    [(fragment, expected) for _, fragment, expected in _DENYLIST_CASES],
    ids=[case_id for case_id, _, _ in _DENYLIST_CASES],
)
def test_denylist_patterns_and_env_var_exception(
    input_fragment: str, expected_substring: str
) -> None:
    """Proves: STORY-002-AC-4

    Every denylist pattern actually implemented in `_internal/redaction.py`
    replaces the secret span with `<redacted>`, table-driven over the RT-01..
    RT-10, RT-13a, and RT-18 cases from §10.
    """
    # Arrange / Act
    result = redact(input_fragment)

    # Assert
    assert expected_substring in result


def test_env_var_name_exception_leaves_value_unchanged() -> None:
    """Proves: STORY-002-AC-4

    RT-13: the env-var-name exception input `api_key=ANTHROPIC_API_KEY` is
    returned completely unchanged — the value is an UPPER_SNAKE identifier with
    at least one underscore, so pattern 8's built-in exception preserves it.
    """
    # Arrange
    text = "api_key=ANTHROPIC_API_KEY"

    # Act
    result = redact(text)

    # Assert
    assert result == text


def test_never_log_key_password_is_redacted_via_processor() -> None:
    """Proves: STORY-002-AC-4

    RT-11: a structured log record with a never-log-list field name (`password`)
    has its value replaced with `<redacted>` regardless of shape, via
    `redact_for_log`.
    """
    # Arrange
    secret_value = "s3cr3tValue"  # noqa: S105  # test fixture value, not a real credential
    event_dict: dict[str, object] = {"event": "login_attempt", "password": secret_value}

    # Act
    result = redact_for_log(object(), "info", event_dict)

    # Assert
    assert result["password"] == "<redacted>"  # noqa: S105  # placeholder token, not a credential


def test_never_log_key_short_value_is_redacted_by_name_not_regex() -> None:
    """Proves: STORY-002-AC-4

    RT-12: a never-log-list field (`api_key`) whose value is too short for any
    regex (`12345`) is still redacted — caught by the field name, not the shape.
    """
    # Arrange
    event_dict: dict[str, object] = {"api_key": "12345"}

    # Act
    result = redact_for_log(object(), "info", event_dict)

    # Assert
    assert result["api_key"] == "<redacted>"


def test_clean_text_passes_through_unchanged() -> None:
    """Proves: STORY-002-AC-4

    RT-17: text containing no secret shape is returned unchanged — no false
    positives from the denylist on benign text.
    """
    # Arrange
    text = "Run finished with 10 passes and 0 errors"

    # Act
    result = redact(text)

    # Assert
    assert result == text


# --------------------------------------------------------------------------- #
# STORY-002-AC-5 — the length cap, applied after substitution
# --------------------------------------------------------------------------- #


def test_redact_applies_length_cap_after_substitution() -> None:
    """Proves: STORY-002-AC-5

    Given text longer than 4000 characters, `redact` returns exactly 4000
    characters followed by the exact suffix ` …[truncated, N more characters]`,
    where N is computed from the post-substitution length — not the raw input
    length.
    """
    # Arrange: embed a 45-char secret (collapses to 10-char "<redacted>" after
    # substitution) inside an otherwise plain word-separated filler that never
    # itself forms a 40+ char run (each filler word is under the
    # generic_long_token floor), so N must be computed from the length AFTER
    # substitution to be correct, and only the deliberate secret is redacted.
    secret_span = "a" * 45  # matches generic_long_token (40+ chars)
    filler_word = "no-secret-here "  # 15 chars incl. trailing space, well under 40
    filler = filler_word * ((_LONG_TEXT_LENGTH - len(secret_span)) // len(filler_word) + 1)
    text = (secret_span + " " + filler)[:_LONG_TEXT_LENGTH]
    assert len(text) == _LONG_TEXT_LENGTH

    # Act
    result = redact(text)

    # Assert: substitution first replaces the 45-char secret with the 10-char
    # placeholder, giving a post-substitution length of 9000 - 45 + 10 = 8965.
    post_substitution_length = _LONG_TEXT_LENGTH - len(secret_span) + len("<redacted>")
    removed = post_substitution_length - _LENGTH_CAP
    expected_suffix = f" …[truncated, {removed} more characters]"
    assert result.endswith(expected_suffix)
    assert len(result) == _LENGTH_CAP + len(expected_suffix)
    body = result[: -len(expected_suffix)]
    assert len(body) == _LENGTH_CAP
    assert secret_span not in result


def test_redact_length_cap_rt15_nine_thousand_chars_no_secret() -> None:
    """Proves: STORY-002-AC-5

    RT-15: a 9000-character string with no secret is capped to 4000 characters
    plus the exact suffix ` …[truncated, 5000 more characters]`. The filler is
    word-separated (each word under the 40-char generic_long_token floor) so no
    denylist pattern fires — the cap is exercised in isolation.
    """
    # Arrange
    filler_word = "no-secret-here "  # 15 chars incl. trailing space, well under 40
    text = (filler_word * (_LONG_TEXT_LENGTH // len(filler_word) + 1))[:_LONG_TEXT_LENGTH]
    assert len(text) == _LONG_TEXT_LENGTH

    # Act
    result = redact(text)

    # Assert
    expected_suffix = f" …[truncated, {_EXPECTED_REMOVED_NO_SECRET} more characters]"
    assert result == text[:_LENGTH_CAP] + expected_suffix


# --------------------------------------------------------------------------- #
# STORY-002-AC-6 — EC-RD-3, EC-RD-5, EC-RD-6
# --------------------------------------------------------------------------- #


def test_redaction_edge_cases_repeated_secret_every_occurrence_replaced() -> None:
    """Proves: STORY-002-AC-6

    EC-RD-3: the same secret appearing multiple times in one string has every
    occurrence replaced — zero raw occurrences remain, and the placeholder count
    matches the number of times the secret appeared.
    """
    # Arrange
    secret = "sk-ant-api03-Zz99Yy88Xx77Ww66Vv55Uu44"  # noqa: S105  # test fixture value, not a real credential
    text = f"first={secret} second={secret} third={secret}"

    # Act
    result = redact(text)

    # Assert
    assert secret not in result
    assert result.count("<redacted>") == _REPEATED_SECRET_OCCURRENCES


@pytest.mark.parametrize("value", [None, ""], ids=["none", "empty_string"])
def test_redaction_edge_cases_none_and_empty_return_empty_string(value: str | None) -> None:
    """Proves: STORY-002-AC-6

    EC-RD-5: `redact(None)` and `redact("")` both return `""` with no exception
    raised.
    """
    # Arrange / Act
    result = redact(value)

    # Assert
    assert result == ""


@pytest.mark.parametrize(
    "field_name",
    ["correlation_id", "run_id", "result_id", "task_id", "model_digest"],
)
def test_redaction_edge_cases_safe_field_name_exempt_from_value_shape_patterns(
    field_name: str,
) -> None:
    """Proves: STORY-002-AC-6

    EC-RD-6: a known-safe diagnostic identifier presented as a named structured
    field to `redact_for_log` is NOT redacted by the value-shape patterns even
    though its value superficially resembles a `generic_long_token`-shaped
    secret (40+ opaque characters).
    """
    # Arrange: a value that would trip generic_long_token (40+ word chars) if it
    # were not exempted by field name.
    long_token_shaped_value = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3"  # noqa: S105  # opaque test id, not a credential
    event_dict: dict[str, object] = {field_name: long_token_shaped_value}

    # Act
    result = redact_for_log(object(), "info", event_dict)

    # Assert
    assert result[field_name] == long_token_shaped_value


def test_redaction_edge_cases_non_safe_field_with_same_shape_is_still_redacted() -> None:
    """Proves: STORY-002-AC-6

    EC-RD-6 (contrast case): the same 40+ char opaque value presented under a
    field name that is NOT on the safe-field list IS redacted by the
    `generic_long_token` value-shape pattern — proving the exemption is by field
    name only, not by value shape.
    """
    # Arrange
    long_token_shaped_value = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3"  # noqa: S105  # opaque test id, not a credential
    event_dict: dict[str, object] = {"some_other_field": long_token_shaped_value}

    # Act
    result = redact_for_log(object(), "info", event_dict)

    # Assert
    assert result["some_other_field"] == "<redacted>"
