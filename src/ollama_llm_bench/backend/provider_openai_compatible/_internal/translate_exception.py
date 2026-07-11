"""Boundary translation: openai/httpx exceptions -> the application error taxonomy.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md`` §6.10. No ``openai.*``/``httpx.*`` exception type may
escape this module's caller.
"""

import httpx
import openai

from ollama_llm_bench.backend.domain import InferenceTestOutcome
from ollama_llm_bench.backend.errors import (
    ErrorContext,
    HttpConnectionError,
    HttpTimeoutError,
    ModelNotAvailableError,
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderContentFilterError,
    ProviderContextLengthError,
    ProviderRateLimitedError,
    ProviderServerError,
    redact,
)

__all__: list[str] = ["classify_test_inference_outcome", "translate_chat_exception"]

_MIN_SERVER_ERROR_STATUS = 500

_CONTEXT_LENGTH_CODES = frozenset({"context_length_exceeded"})
_CONTENT_FILTER_CODES = frozenset({"content_filter", "content_policy_violation"})


def translate_chat_exception(exc: Exception, *, context: ErrorContext) -> Exception:
    """Map one openai/httpx exception to its taxonomy leaf, redacting the message.

    Table (§6.10): ``openai.APITimeoutError`` and any bare ``httpx.TimeoutException``
    (e.g. a mid-stream ``httpx.ReadTimeout`` the SDK's own chunk iterator does not
    wrap) -> ``HttpTimeoutError``; ``AuthenticationError``/``PermissionDeniedError``
    -> ``ProviderAuthError``; ``NotFoundError`` -> ``ModelNotAvailableError``;
    ``RateLimitError`` -> ``ProviderRateLimitedError`` (carrying ``retry_after``
    when the SDK exposes a ``Retry-After`` header); ``APIConnectionError`` and any
    other bare ``httpx`` transport failure -> ``HttpConnectionError``;
    ``BadRequestError``/``UnprocessableEntityError`` -> ``ProviderBadRequestError``,
    except when the body's ``code`` names a context-length or content-filter
    condition, which take the more specific leaf; ``InternalServerError``/
    ``APIStatusError`` with a 5xx status -> ``ProviderServerError``; any other
    ``openai.APIError`` or unenumerated exception -> ``ProviderBadRequestError``
    (the safe, never-retried catch-all default).

    Args:
        exc: The raw SDK/transport exception caught at the call site.
        context: The redaction-safe diagnostic context to attach to the
            translated leaf.

    Returns:
        The taxonomy leaf to raise in place of ``exc``, its message already
        passed through ``redact()``.
    """
    message = redact(str(exc))
    if isinstance(exc, openai.APITimeoutError | httpx.TimeoutException):
        return HttpTimeoutError(message=message, context=context)
    if isinstance(exc, openai.APIStatusError):
        return _translate_status_error(exc, message=message, context=context)
    if isinstance(exc, openai.APIConnectionError | httpx.HTTPError):
        return HttpConnectionError(message=message, context=context)
    return ProviderBadRequestError(message=message, context=context)


def _translate_status_error(
    exc: openai.APIStatusError, *, message: str, context: ErrorContext
) -> Exception:
    """Translate a response-carrying (4xx/5xx) ``openai.APIStatusError`` subclass."""
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return ProviderAuthError(message=message, context=context)
    if isinstance(exc, openai.NotFoundError):
        return ModelNotAvailableError(message=message, context=context)
    if isinstance(exc, openai.RateLimitError):
        return ProviderRateLimitedError(
            message=message, context=context, retry_after=_extract_retry_after(exc)
        )
    if isinstance(exc, openai.BadRequestError | openai.UnprocessableEntityError):
        return _classify_bad_request(exc, message=message, context=context)
    if isinstance(exc, openai.InternalServerError) or exc.status_code >= _MIN_SERVER_ERROR_STATUS:
        return ProviderServerError(message=message, context=context)
    return ProviderBadRequestError(message=message, context=context)


def _classify_bad_request(
    exc: openai.APIStatusError, *, message: str, context: ErrorContext
) -> Exception:
    """Refine a 400/422-class response into the more specific taxonomy leaf."""
    body_code = exc.code
    if body_code in _CONTEXT_LENGTH_CODES:
        return ProviderContextLengthError(message=message, context=context)
    if body_code in _CONTENT_FILTER_CODES:
        return ProviderContentFilterError(message=message, context=context)
    return ProviderBadRequestError(message=message, context=context)


def _extract_retry_after(exc: openai.RateLimitError) -> float | None:
    """Read the ``Retry-After`` header from a rate-limit response, if present."""
    header = exc.response.headers.get("retry-after")
    if header is None:
        return None
    try:
        return float(header)
    except ValueError:
        return None


def classify_test_inference_outcome(exc: Exception) -> InferenceTestOutcome:
    """Map a chat exception to ``test_inference``'s outcome enum (§6.8.2, AC-9).

    ``HttpTimeoutError`` -> ``TIMEOUT``; ``HttpConnectionError`` ->
    ``REACHABILITY_FAILED``; ``ProviderAuthError`` -> ``AUTH_FAILED``;
    ``ModelNotAvailableError`` -> ``MODEL_NOT_FOUND``; anything else (including
    ``TaskCancelledError``, which ``test_inference`` never lets escape per
    §6.8.2 step 8's "never raises" rule) -> ``PROVIDER_ERROR``.

    Args:
        exc: The exception raised by the canned-prompt ``chat`` call — already
            a taxonomy leaf, never a raw SDK type.

    Returns:
        The ``InferenceTestOutcome`` member corresponding to ``exc``.
    """
    if isinstance(exc, HttpTimeoutError):
        return InferenceTestOutcome.TIMEOUT
    if isinstance(exc, HttpConnectionError):
        return InferenceTestOutcome.REACHABILITY_FAILED
    if isinstance(exc, ProviderAuthError):
        return InferenceTestOutcome.AUTH_FAILED
    if isinstance(exc, ModelNotAvailableError):
        return InferenceTestOutcome.MODEL_NOT_FOUND
    return InferenceTestOutcome.PROVIDER_ERROR
