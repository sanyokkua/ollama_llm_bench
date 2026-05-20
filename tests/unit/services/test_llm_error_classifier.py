"""Unit tests for LlmErrorClassifier — error classification and retryability logic."""

from unittest.mock import MagicMock

import openai
import pytest

from ollama_llm_bench.backend.services.llm_error_classifier import LlmErrorClassifier


def _make_openai_exc(cls: type, *, status_code: int = 400, message: str = "error") -> openai.OpenAIError:
    """Construct a minimal openai SDK exception suitable for testing."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.headers = {}
    exc = cls(message, response=mock_response, body=None)
    return exc


@pytest.fixture
def classifier() -> LlmErrorClassifier:
    return LlmErrorClassifier()


# ---------------------------------------------------------------------------
# classify() — live exception path
# ---------------------------------------------------------------------------


def test_classify_api_connection_error_is_retryable(classifier: LlmErrorClassifier) -> None:
    exc = openai.APIConnectionError(request=MagicMock())

    result = classifier.classify(exc)

    assert result.is_retryable is True
    assert result.is_capability_signal is False
    assert result.capability_unsupported is None
    assert result.classification_reason == "connection_error"


def test_classify_api_timeout_error_is_retryable(classifier: LlmErrorClassifier) -> None:
    exc = openai.APITimeoutError(request=MagicMock())

    result = classifier.classify(exc)

    assert result.is_retryable is True
    assert result.is_capability_signal is False
    assert result.classification_reason == "timeout"


def test_classify_rate_limit_error_is_retryable(classifier: LlmErrorClassifier) -> None:
    exc = _make_openai_exc(openai.RateLimitError, status_code=429, message="rate limited")

    result = classifier.classify(exc)

    assert result.is_retryable is True
    assert result.http_status == 429
    assert result.classification_reason == "rate_limit_429"


def test_classify_internal_server_error_500_is_retryable(classifier: LlmErrorClassifier) -> None:
    exc = _make_openai_exc(openai.InternalServerError, status_code=500, message="internal server error")

    result = classifier.classify(exc)

    assert result.is_retryable is True
    assert result.is_capability_signal is False
    assert result.classification_reason == "server_error_5xx"


def test_classify_internal_server_error_503_is_retryable(classifier: LlmErrorClassifier) -> None:
    exc = _make_openai_exc(openai.InternalServerError, status_code=503, message="service unavailable")

    result = classifier.classify(exc)

    assert result.is_retryable is True
    assert result.classification_reason == "server_error_5xx"


def test_classify_bad_request_thinking_unsupported(classifier: LlmErrorClassifier) -> None:
    exc = _make_openai_exc(
        openai.BadRequestError,
        status_code=400,
        message="gemma3:1b-it-q4_K_M does not support thinking",
    )

    result = classifier.classify(exc)

    assert result.is_retryable is False
    assert result.is_capability_signal is True
    assert result.capability_unsupported == "thinking"
    assert result.http_status == 400
    assert result.classification_reason == "bad_request_thinking_unsupported"


def test_classify_bad_request_context_length(classifier: LlmErrorClassifier) -> None:
    exc = _make_openai_exc(
        openai.BadRequestError,
        status_code=400,
        message="context length exceeded: too many tokens in input",
    )

    result = classifier.classify(exc)

    assert result.is_retryable is False
    assert result.is_capability_signal is True
    assert result.capability_unsupported == "context_length"
    assert result.classification_reason == "bad_request_context_length"


def test_classify_bad_request_generic_not_capability(classifier: LlmErrorClassifier) -> None:
    exc = _make_openai_exc(
        openai.BadRequestError,
        status_code=400,
        message="invalid parameter: temperature must be between 0 and 2",
    )

    result = classifier.classify(exc)

    assert result.is_retryable is False
    assert result.is_capability_signal is False
    assert result.capability_unsupported is None
    assert result.classification_reason == "bad_request_generic"


def test_classify_authentication_error_not_retryable(classifier: LlmErrorClassifier) -> None:
    exc = _make_openai_exc(openai.AuthenticationError, status_code=401, message="invalid api key")

    result = classifier.classify(exc)

    assert result.is_retryable is False
    assert result.is_capability_signal is False
    assert result.classification_reason == "auth_error"


def test_classify_permission_denied_error_not_retryable(classifier: LlmErrorClassifier) -> None:
    exc = _make_openai_exc(openai.PermissionDeniedError, status_code=403, message="forbidden")

    result = classifier.classify(exc)

    assert result.is_retryable is False
    assert result.classification_reason == "auth_error"


def test_classify_not_found_error_model_signal(classifier: LlmErrorClassifier) -> None:
    exc = _make_openai_exc(openai.NotFoundError, status_code=404, message="model not found")

    result = classifier.classify(exc)

    assert result.is_retryable is False
    assert result.is_capability_signal is True
    assert result.capability_unsupported == "model"
    assert result.http_status == 404
    assert result.classification_reason == "not_found_404"


def test_classify_unknown_exception_not_retryable(classifier: LlmErrorClassifier) -> None:
    exc = ValueError("some unexpected error")

    result = classifier.classify(exc)

    assert result.is_retryable is False
    assert result.is_capability_signal is False
    assert result.classification_reason == "unknown"


# ---------------------------------------------------------------------------
# classify_from_message() — pre-stringified message path
# ---------------------------------------------------------------------------


def test_classify_from_message_server_error_prefix_is_retryable(classifier: LlmErrorClassifier) -> None:
    msg = "Error code: 503 — Service Unavailable"

    result = classifier.classify_from_message(msg)

    assert result.is_retryable is True
    assert result.classification_reason == "server_error_5xx_from_message"


def test_classify_from_message_thinking_unsupported(classifier: LlmErrorClassifier) -> None:
    msg = "gemma3:1b-it-q4_K_M does not support thinking"

    result = classifier.classify_from_message(msg)

    assert result.is_capability_signal is True
    assert result.capability_unsupported == "thinking"
    assert result.is_retryable is False
    assert result.classification_reason == "bad_request_thinking_unsupported"


def test_classify_from_message_auth_error(classifier: LlmErrorClassifier) -> None:
    msg = "Error code: 401 — Unauthorized"

    result = classifier.classify_from_message(msg)

    assert result.is_retryable is False
    assert result.classification_reason == "auth_error"


def test_classify_from_message_empty_string_not_retryable(classifier: LlmErrorClassifier) -> None:
    result = classifier.classify_from_message("")

    assert result.is_retryable is False
    assert result.is_capability_signal is False
    assert result.capability_unsupported is None
    assert result.classification_reason == "empty_message"


def test_classify_from_message_context_length(classifier: LlmErrorClassifier) -> None:
    msg = "context length exceeded: too many tokens in the prompt"

    result = classifier.classify_from_message(msg)

    assert result.is_capability_signal is True
    assert result.capability_unsupported == "context_length"
    assert result.is_retryable is False


def test_classify_from_message_not_found(classifier: LlmErrorClassifier) -> None:
    msg = "Error code: 404 — model not found"

    result = classifier.classify_from_message(msg)

    assert result.is_retryable is False
    assert result.is_capability_signal is True
    assert result.capability_unsupported == "model"
    assert result.classification_reason == "not_found_404"
