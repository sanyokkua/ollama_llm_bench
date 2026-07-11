"""Tests proving STORY-019-AC-4: every ``anthropic`` SDK failure translates to
the application error taxonomy, with no ``anthropic``/``httpx`` exception type
escaping and every attached message passed through ``redact()``.

Source of truth: ``docs/stories/story-019-anthropic-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md``
§6.10.

Table-driven (Pattern B, ``acceptance-criteria-authoring`` skill): the story's
AC-4 table enumerates a finite set of SDK/transport conditions, each mapping
to one taxonomy leaf — the canonical shape for one
``@pytest.mark.parametrize`` test, never a loop over cases. Each case is a
genuine wire-stub scenario (real adapter, real ``anthropic`` SDK, real HTTP
response from ``pytest_httpserver``) — no monkeypatching of SDK internals,
per the provider-wire-stub convention.
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
from ollama_llm_bench.backend.provider_anthropic._internal.client_impl import AnthropicClient
from ollama_llm_bench.backend.provider_anthropic.tests.conftest import FakeClock, make_chat_request

_LEAKED_CREDENTIAL_MARKER = "Authorization: Bearer sk-ant-api03-leaked-secret-fragment"


class _TranslationCase(NamedTuple):
    """Strictly private, colocated-test-only bundle for one AC-4 table row."""

    status: int
    error_type: str
    expected_leaf: type[AppError]


_CASES = (
    _TranslationCase(
        status=401, error_type="authentication_error", expected_leaf=ProviderAuthError
    ),
    _TranslationCase(status=403, error_type="permission_error", expected_leaf=ProviderAuthError),
    _TranslationCase(
        status=404, error_type="not_found_error", expected_leaf=ModelNotAvailableError
    ),
    _TranslationCase(
        status=429, error_type="rate_limit_error", expected_leaf=ProviderRateLimitedError
    ),
    _TranslationCase(status=500, error_type="api_error", expected_leaf=ProviderServerError),
    _TranslationCase(
        status=400, error_type="invalid_request_error", expected_leaf=ProviderBadRequestError
    ),
)


@pytest.mark.parametrize(
    "case",
    _CASES,
    ids=[
        "authentication_error_401",
        "permission_error_403",
        "not_found_error_404",
        "rate_limit_error_429",
        "server_error_500",
        "bad_request_400",
    ],
)
def test_sdk_failure_translates_to_taxonomy_and_redacts(
    httpserver: HTTPServer,
    fake_clock: FakeClock,
    make_client: Callable[..., AnthropicClient],
    case: _TranslationCase,
) -> None:
    """Proves: STORY-019-AC-4

    Each ``anthropic`` SDK failure translates to a taxonomy exception per the
    story's AC-4 table: no ``anthropic``/``httpx`` exception type escapes,
    and the message attached to the raised error has been passed through
    ``redact()`` (the leaked-credential marker never appears in the raised
    message).
    """
    # Arrange
    body = {
        "type": "error",
        "error": {
            "type": case.error_type,
            "message": f"boom {_LEAKED_CREDENTIAL_MARKER}",
        },
    }
    httpserver.expect_request("/v1/messages", method="POST").respond_with_json(
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
    fake_clock: FakeClock, make_client: Callable[..., AnthropicClient]
) -> None:
    """Proves: STORY-019-AC-4

    An untyped ``httpx`` transport failure (connection refused, no server
    listening at all) translates to ``HttpConnectionError`` with no raw
    ``httpx``/``anthropic`` exception type escaping.
    """
    # Arrange: port 1 is a reserved, always-refused port on every OS.
    client = make_client(base_url="http://127.0.0.1:1/")
    request = make_chat_request()
    token = CancellationToken(clock=fake_clock)

    # Act / Assert
    with pytest.raises(HttpConnectionError):
        client.chat(request, token=token)


def test_unenumerated_sdk_exception_falls_through_catch_all(
    httpserver: HTTPServer,
    fake_clock: FakeClock,
    make_client: Callable[..., AnthropicClient],
) -> None:
    """Proves: STORY-019-AC-4

    A malformed response body the SDK cannot parse into any of its typed
    error subclasses (a non-JSON body with a generic 4xx status the SDK
    still wraps in ``anthropic.APIStatusError``) still translates to a
    taxonomy leaf — the catch-all default — never letting a raw SDK
    exception escape.
    """
    # Arrange: an unusual 418 status the client's translation table does not
    # special-case; the SDK wraps it as a generic APIStatusError subtype.
    httpserver.expect_request("/v1/messages", method="POST").respond_with_data(
        "not json", status=418, content_type="text/plain"
    )
    client = make_client()
    request = make_chat_request()
    token = CancellationToken(clock=fake_clock)

    # Act / Assert
    with pytest.raises(AppError) as exc_info:
        client.chat(request, token=token)
    assert type(exc_info.value).__module__.startswith("ollama_llm_bench")
