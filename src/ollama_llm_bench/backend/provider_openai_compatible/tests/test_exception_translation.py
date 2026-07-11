"""Tests proving STORY-018-AC-5: every SDK/transport failure translates to the
application error taxonomy, with no raw ``openai``/``httpx`` exception type
escaping and every attached message passed through ``redact()``.

Source of truth: ``docs/stories/story-018-openai-compatible-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md`` §6.10.

Table-driven (Pattern B, ``acceptance-criteria-authoring`` skill): the story's AC-5
table enumerates a finite set of SDK/transport conditions, each mapping to one
taxonomy category — the canonical shape for one ``@pytest.mark.parametrize`` test,
never a loop over cases. Each case is a genuine wire-stub scenario (real adapter,
real ``openai`` SDK, real HTTP response from ``pytest_httpserver``) — no
monkeypatching of SDK internals, per the provider-wire-stub convention.
"""

from collections.abc import Callable
from typing import NamedTuple

import pytest
from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.errors import (
    AppError,
    HttpConnectionError,
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderRateLimitedError,
    ProviderServerError,
)
from ollama_llm_bench.backend.provider_openai_compatible._internal.client_impl import (
    OpenAICompatibleClient,
)
from ollama_llm_bench.backend.provider_openai_compatible.tests.conftest import (
    FakeClock,
    make_chat_request,
)

_LEAKED_CREDENTIAL_MARKER = "sk-abcdefghijklmnopqrstuvwxyz0123456789"


class _TranslationCase(NamedTuple):
    """Strictly private, colocated-test-only bundle for one AC-5 table row."""

    status: int
    body: dict[str, object]
    expected_leaf: type[AppError]


_CASES = (
    _TranslationCase(
        status=401,
        body={
            "error": {
                "message": f"Invalid API key: {_LEAKED_CREDENTIAL_MARKER}",
                "code": "invalid_api_key",
            }
        },
        expected_leaf=ProviderAuthError,
    ),
    _TranslationCase(
        status=400,
        body={"error": {"message": "bad request body", "code": "bad_request"}},
        expected_leaf=ProviderBadRequestError,
    ),
    _TranslationCase(
        status=429,
        body={"error": {"message": "rate limited", "code": "rate_limit_exceeded"}},
        expected_leaf=ProviderRateLimitedError,
    ),
    _TranslationCase(
        status=500,
        body={"error": {"message": "internal server error", "code": "server_error"}},
        expected_leaf=ProviderServerError,
    ),
)


@pytest.mark.parametrize(
    "case",
    _CASES,
    ids=["authentication_error", "bad_request_error", "rate_limit_error", "server_error_5xx"],
)
def test_sdk_failure_translates_to_taxonomy_and_redacts(
    httpserver: HTTPServer,
    fake_clock: FakeClock,
    make_client: Callable[..., OpenAICompatibleClient],
    case: _TranslationCase,
) -> None:
    """Proves: STORY-018-AC-5

    Each provider-side failure translates to a taxonomy exception per the
    story's AC-5 table: no ``openai``/``httpx`` exception type escapes, and
    the message attached to the raised error has been passed through
    ``redact()`` (the leaked-credential marker never appears in the raised
    message).
    """
    # Arrange
    httpserver.expect_request("/chat/completions", method="POST").respond_with_json(
        case.body, status=case.status
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
    fake_clock: FakeClock, make_client: Callable[..., OpenAICompatibleClient]
) -> None:
    """Proves: STORY-018-AC-5

    An untyped ``httpx`` transport failure (connection refused, no server
    listening at all) translates to ``HttpConnectionError`` with no raw
    ``httpx``/``openai`` exception type escaping.
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
    make_client: Callable[..., OpenAICompatibleClient],
) -> None:
    """Proves: STORY-018-AC-5

    A malformed response body the SDK cannot parse into any of its typed
    error subclasses (a non-JSON body with a generic 4xx status the SDK
    still wraps in ``openai.APIStatusError``) still translates to a taxonomy
    leaf — the catch-all default — never letting a raw SDK exception escape.
    """
    # Arrange: an unusual 418 status the client's translation table does not
    # special-case; the SDK wraps it as a generic APIStatusError subtype.
    httpserver.expect_request("/chat/completions", method="POST").respond_with_data(
        "not json", status=418, content_type="text/plain"
    )
    client = make_client()
    request = make_chat_request()
    token = CancellationToken(clock=fake_clock)

    # Act / Assert
    with pytest.raises(AppError) as exc_info:
        client.chat(request, token=token)
    assert type(exc_info.value).__module__.startswith("ollama_llm_bench")
