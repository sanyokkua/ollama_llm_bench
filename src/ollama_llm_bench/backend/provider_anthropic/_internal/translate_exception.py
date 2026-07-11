"""Boundary translation: anthropic/httpx exceptions -> the application error taxonomy.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md`` §6.10. No ``anthropic.*``/``httpx.*`` exception type
may escape this module's caller.
"""

import anthropic
import httpx

from ollama_llm_bench.backend.domain import InferenceTestOutcome
from ollama_llm_bench.backend.errors import (
    ErrorContext,
    HttpConnectionError,
    HttpTimeoutError,
    ModelNotAvailableError,
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderRateLimitedError,
    ProviderServerError,
    redact,
)

__all__: list[str] = ["classify_test_inference_outcome", "translate_chat_exception"]

_MIN_SERVER_ERROR_STATUS = 500


def translate_chat_exception(exc: Exception, *, context: ErrorContext) -> Exception:
    """Map one anthropic/httpx exception to its taxonomy leaf, redacting the message.

    Table (§6.10, STORY-019-AC-4): ``anthropic.APITimeoutError`` and any bare
    ``httpx.TimeoutException`` (e.g. a mid-stream ``httpx.ReadTimeout`` the SDK's
    own chunk iterator does not wrap) -> ``HttpTimeoutError``;
    ``AuthenticationError``/``PermissionDeniedError`` -> ``ProviderAuthError``;
    ``NotFoundError`` -> ``ModelNotAvailableError``; ``RateLimitError`` ->
    ``ProviderRateLimitedError`` (carrying ``retry_after`` when the SDK exposes
    a ``Retry-After`` header); ``anthropic.APIConnectionError`` (note:
    ``APITimeoutError`` is itself an ``APIConnectionError`` subclass in this
    SDK, so it is checked first) and any other bare ``httpx`` transport
    failure -> ``HttpConnectionError``; ``InternalServerError`` or any other
    ``anthropic.APIStatusError`` with a 5xx status -> ``ProviderServerError``;
    any other ``anthropic.APIError`` or unenumerated exception ->
    ``ProviderBadRequestError`` (the safe, never-retried catch-all default).

    Args:
        exc: The raw SDK/transport exception caught at the call site.
        context: The redaction-safe diagnostic context to attach to the
            translated leaf.

    Returns:
        The taxonomy leaf to raise in place of ``exc``, its message already
        passed through ``redact()``.
    """
    message = redact(str(exc))
    if isinstance(exc, anthropic.APITimeoutError | httpx.TimeoutException):
        return HttpTimeoutError(message=message, context=context)
    if isinstance(exc, anthropic.APIStatusError):
        return _translate_status_error(exc, message=message, context=context)
    if isinstance(exc, anthropic.APIConnectionError | httpx.HTTPError):
        return HttpConnectionError(message=message, context=context)
    return ProviderBadRequestError(message=message, context=context)


def _translate_status_error(
    exc: anthropic.APIStatusError, *, message: str, context: ErrorContext
) -> Exception:
    """Translate a response-carrying (4xx/5xx) ``anthropic.APIStatusError`` subclass."""
    if isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return ProviderAuthError(message=message, context=context)
    if isinstance(exc, anthropic.NotFoundError):
        return ModelNotAvailableError(message=message, context=context)
    if isinstance(exc, anthropic.RateLimitError):
        return ProviderRateLimitedError(
            message=message, context=context, retry_after=_extract_retry_after(exc)
        )
    if (
        isinstance(exc, anthropic.InternalServerError)
        or exc.status_code >= _MIN_SERVER_ERROR_STATUS
    ):
        return ProviderServerError(message=message, context=context)
    return ProviderBadRequestError(message=message, context=context)


def _extract_retry_after(exc: anthropic.RateLimitError) -> float | None:
    """Read the ``Retry-After`` header from a rate-limit response, if present."""
    header = exc.response.headers.get("retry-after")
    if header is None:
        return None
    try:
        return float(header)
    except ValueError:
        return None


def classify_test_inference_outcome(exc: Exception) -> InferenceTestOutcome:
    """Map a chat exception to ``test_inference``'s outcome enum (§6.8.2).

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
