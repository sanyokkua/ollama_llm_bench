"""Tests proving STORY-020-AC-4: every ``google-genai`` SDK failure translates
to the application error taxonomy, with no ``google.genai``/``httpx``
exception type escaping and every attached message passed through
``redact()``.

Source of truth: ``docs/stories/story-020-gemini-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md``
§6.10.

Table-driven (Pattern B, ``acceptance-criteria-authoring`` skill): the
story's AC-4 table enumerates a finite set of SDK/transport conditions, each
mapping to one taxonomy leaf — the canonical shape for one
``@pytest.mark.parametrize`` test, never a loop over cases. Each case is a
genuine wire-stub scenario (real adapter, real ``google-genai`` SDK, real
HTTP response from ``pytest_httpserver``) — no monkeypatching of SDK
internals, per the provider-wire-stub convention.
"""

from collections.abc import Callable
from typing import NamedTuple

import pytest
from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.errors import (
    AppError,
    HttpConnectionError,
    ModelNotAvailableError,
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderRateLimitedError,
    ProviderServerError,
)
from ollama_llm_bench.backend.provider_gemini._internal.client_impl import GeminiClient
from ollama_llm_bench.backend.provider_gemini.tests.conftest import FakeClock, make_chat_request

_STREAM_PATH = "/v1beta/models/gemini-test-model:streamGenerateContent"
_LEAKED_CREDENTIAL_MARKER = "Authorization: Bearer AIzaSy-leaked-secret-fragment"


class _TranslationCase(NamedTuple):
    """Strictly private, colocated-test-only bundle for one AC-4 table row."""

    status: int
    expected_leaf: type[AppError]


_CASES = (
    _TranslationCase(status=401, expected_leaf=ProviderAuthError),
    _TranslationCase(status=403, expected_leaf=ProviderAuthError),
    _TranslationCase(status=404, expected_leaf=ModelNotAvailableError),
    _TranslationCase(status=429, expected_leaf=ProviderRateLimitedError),
    _TranslationCase(status=500, expected_leaf=ProviderServerError),
    _TranslationCase(status=400, expected_leaf=ProviderBadRequestError),
)


@pytest.mark.parametrize(
    "case",
    _CASES,
    ids=[
        "auth_401",
        "auth_403",
        "model_not_found_404",
        "rate_limited_429",
        "server_error_500",
        "bad_request_400",
    ],
)
def test_sdk_failure_translates_to_taxonomy_and_redacts(
    httpserver: HTTPServer,
    fake_clock: FakeClock,
    make_client: Callable[..., GeminiClient],
    case: _TranslationCase,
) -> None:
    """Proves: STORY-020-AC-4

    Each ``google-genai`` SDK failure translates to a taxonomy exception per
    the story's AC-4 table: no ``google.genai``/``httpx`` exception type
    escapes, and the message attached to the raised error has been passed
    through ``redact()`` (the leaked-credential marker never appears in the
    raised message).
    """
    # Arrange
    body = {"error": {"code": case.status, "message": f"boom {_LEAKED_CREDENTIAL_MARKER}"}}
    httpserver.expect_request(_STREAM_PATH, method="POST").respond_with_json(
        body, status=case.status
    )
    client = make_client()
    request = make_chat_request()
    token = CancellationToken(clock=fake_clock)

    # Act
    with pytest.raises(AppError) as exc_info:
        client.chat(request, token=token)

    # Assert
    raised = exc_info.value
    assert type(raised).__module__.startswith("ollama_llm_bench")
    assert isinstance(raised, case.expected_leaf)
    assert _LEAKED_CREDENTIAL_MARKER not in raised.message


def test_connection_refused_translates_to_http_connection_error(
    fake_clock: FakeClock, make_client: Callable[..., GeminiClient]
) -> None:
    """Proves: STORY-020-AC-4

    An untyped ``httpx`` transport failure (connection refused, no server
    listening at all) translates to ``HttpConnectionError`` with no raw
    ``httpx``/``google.genai`` exception type escaping.
    """
    # Arrange: port 1 is a reserved, always-refused port on every OS.
    client = make_client(base_url="http://127.0.0.1:1/")
    request = make_chat_request()
    token = CancellationToken(clock=fake_clock)

    # Act / Assert
    with pytest.raises(HttpConnectionError):
        client.chat(request, token=token)


def test_unenumerated_status_falls_through_catch_all(
    httpserver: HTTPServer, fake_clock: FakeClock, make_client: Callable[..., GeminiClient]
) -> None:
    """Proves: STORY-020-AC-4

    A status code the client's translation table does not special-case
    (neither 401/403, 404, 429, nor >= 500) still translates to a taxonomy
    leaf — the catch-all default (``ProviderBadRequestError``) — never
    letting a raw SDK exception escape.
    """
    # Arrange: 418 is not one of the AC-4 table's special-cased statuses.
    httpserver.expect_request(_STREAM_PATH, method="POST").respond_with_json(
        {"error": {"code": 418, "message": "boom"}}, status=418
    )
    client = make_client()
    request = make_chat_request()
    token = CancellationToken(clock=fake_clock)

    # Act / Assert
    with pytest.raises(ProviderBadRequestError):
        client.chat(request, token=token)
