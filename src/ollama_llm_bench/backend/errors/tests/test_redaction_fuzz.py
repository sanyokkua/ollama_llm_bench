"""Property test for STORY-093-AC-4: no generated secret survives either redaction surface.

Source of truth: ``docs/v3_specification/10_Domain_and_Data/08_REDACTION_PATTERNS.md``
§3 (the regex denylist), §4 (the never-log key-name list), §7 (the two-surface API), §8
(order of operations), §11 (edge cases EC-RD-2, EC-RD-6).

Where ``test_redaction.py`` pins the spec's enumerated cases RT-01..RT-19, this module
generates fresh secrets in each denylist shape and asserts the invariant that matters: the
generated value is *absent* from the output and the redaction marker is *present*.

Three deliberate scope decisions, each of which a naive property would fail on legitimately:

1. **Assert the generated value is gone -- not that "no pattern re-matches".** ``redact()``
   preserves the key name for patterns 7 and 8 (§3 Rules), so its own output
   ``Authorization: <redacted>`` still matches pattern 7 and ``api_key=<redacted>`` still
   matches pattern 8. Re-matching the denylist against the output is therefore not the
   invariant; substring absence is.
2. **No env-var-name-shaped values are generated.** §3's pattern-8 rule deliberately leaves
   ``api_key=ANTHROPIC_API_KEY`` intact -- an UPPER_SNAKE identifier is a variable *name*, not
   a secret. ``_ENV_VAR_NAME_SHAPED`` below mirrors that exception so the generator cannot
   assert against sanctioned behaviour.
3. **No secrets below the patterns' length floors.** EC-RD-2 records a short, unstructured
   secret as an *accepted residual risk*; generating one would assert something the
   specification explicitly disclaims.

Nothing here asserts about the ``run.*`` stream: it is deliberately un-redacted
(``backend/infra/_internal/run_context.py``), and ``redact_for_log`` is installed on ``app.*``
only (§7.2).

**Scope (STORY-093, D7).** This covers ``redact()`` on free text and ``redact_for_log`` on
*string-valued* fields. It does not plant secrets in nested ``list``/``dict`` values or in
non-``str`` values: ``_redact_field_value`` returns non-``str`` values unchanged, so those
bypass the denylist entirely. §7.2 step 2 says to serialise the record to a log line and regex
*that*; the implementation regexes each string value instead. That divergence is recorded as a
named residual risk on the R-013 row of ``docs/development/risk_mitigation_checklist.md`` and
is not fixed here.
"""

import re

from hypothesis import assume, given, settings, strategies as st
import pytest

from ollama_llm_bench.backend.errors.api import redact, redact_for_log

_REDACTED = "<redacted>"
"""The marker `redaction.REDACTED` emits (§7). Mirrored rather than imported: this module's
colocated tests import the public `api` surface only."""

_MAX_EXAMPLES = 200

# Mirrors `_ENV_VAR_NAME_RE` (§3 Rules, RT-13/RT-13a) so trap 2 above is enforced, not assumed.
_ENV_VAR_NAME_SHAPED = re.compile(r"^[\"']?[A-Z][A-Z0-9]*(_[A-Z0-9]+)+[\"']?$")

# Field names exempt from the value-shape patterns (§8, EC-RD-6) -- planting a secret in one of
# these is sanctioned passthrough, not a leak, so the generator must not produce them.
_SAFE_FIELD_NAMES = frozenset({"correlation_id", "run_id", "result_id", "task_id"})

# Never-log key names (§4). Excluded from the *generated* field name so each assertion below
# exercises one rule at a time; the never-log rule gets its own fixed field in the record.
_NEVER_LOG_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "access_token",
        "secret_key",
        "secret",
        "client_secret",
        "authorization",
        "auth",
        "bearer",
        "password",
        "passwd",
        "token",
        "x-api-key",
    }
)

_ALNUM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_URL_SAFE = f"{_ALNUM}_-"
_HEX = "0123456789abcdefABCDEF"
_BEARER_ALPHABET = f"{_ALNUM}._~+/-"

_AZURE_KEY_LENGTH = 32


def _chars(alphabet: str, minimum: int, maximum: int) -> st.SearchStrategy[str]:
    return st.text(alphabet=alphabet, min_size=minimum, max_size=maximum)


# One strategy per denylist pattern (§3, patterns 1-10), each comfortably above that
# pattern's length floor. Pattern 7 (`Authorization:`) is exercised by the templates below.
_BARE_SECRETS = st.one_of(
    _chars(_URL_SAFE, 24, 48).map(lambda s: f"sk-{s}"),  # 1: openai_key
    _chars(_URL_SAFE, 24, 48).map(lambda s: f"sk-ant-{s}"),  # 2: anthropic_key
    _chars(_URL_SAFE, 34, 56).map(lambda s: f"AIza{s}"),  # 3: google_key
    _chars(_ALNUM, 24, 40).map(lambda s: f"gho_{s}"),  # 4: github_token
    _chars(_HEX, _AZURE_KEY_LENGTH, _AZURE_KEY_LENGTH),  # 5: azure_key
    st.tuples(  # 9: jwt
        _chars(_URL_SAFE, 12, 24), _chars(_URL_SAFE, 12, 24), _chars(_URL_SAFE, 12, 24)
    ).map(lambda parts: "eyJ{}.{}.{}".format(*parts)),
    _chars(_ALNUM, 44, 72),  # 10: generic_long_token
)

# `Bearer <token>` (pattern 6) is matched as a unit: the bare token has no shape of its own,
# so it is generated together with its prefix and the whole span must vanish.
_BEARER_SECRETS = _chars(_BEARER_ALPHABET, 20, 48).map(lambda s: f"Bearer {s}")

# Each template surrounds the secret with non-word characters, so the `\b`-anchored patterns
# (azure_key, generic_long_token) see a word boundary regardless of the shape drawn.
_TEMPLATES = st.sampled_from(
    (
        "provider call failed: {secret} (will not retry)",
        "HTTP 401 unauthorized — {secret} rejected by the endpoint",
        "api_key={secret}",
        'client_secret="{secret}"',
        "Authorization: {secret}",
    )
)

_FIELD_NAMES = st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=3, max_size=16).filter(
    lambda name: (
        "digest" not in name
        and name not in _SAFE_FIELD_NAMES
        and name not in _NEVER_LOG_KEYS
        and name != "event"
    )
)


@pytest.mark.slow
@pytest.mark.property
@given(
    secret=st.one_of(_BARE_SECRETS, _BEARER_SECRETS),
    template=_TEMPLATES,
    field_name=_FIELD_NAMES,
)
@settings(max_examples=_MAX_EXAMPLES, deadline=None)
def test_no_denylist_pattern_survives_either_redaction_surface(
    secret: str, template: str, field_name: str
) -> None:
    """Proves: STORY-093-AC-4

    Covers: EC-RD-2, EC-RD-6

    For a value drawn from any denylist shape, neither redaction surface emits it: `redact()`
    at the adapter boundary (§7.1) and the `redact_for_log` processor on the `app.*` stream
    (§7.2) both replace it with the redaction marker.

    `deadline=None` is mandatory, not decorative: `tests/conftest.py`'s Hypothesis profiles
    cover the `tests/` tree only, so this colocated module runs under Hypothesis's *default*
    profile with a live 200 ms per-example deadline.
    """
    assume(not _ENV_VAR_NAME_SHAPED.match(secret))
    text = template.format(secret=secret)

    boundary_output = redact(text)
    assert secret not in boundary_output
    assert _REDACTED in boundary_output

    record = redact_for_log(
        None,
        "info",
        {"event": text, field_name: text, "api_key": secret},
    )

    for key in ("event", field_name):
        value = record[key]
        assert isinstance(value, str)
        assert secret not in value, f"secret survived redact_for_log in field {key!r}"
        assert _REDACTED in value

    # §4: a never-log key's value is replaced wholesale, whatever its shape -- this is the only
    # rule that catches a bare `Bearer` token stripped of its prefix.
    assert record["api_key"] == _REDACTED
