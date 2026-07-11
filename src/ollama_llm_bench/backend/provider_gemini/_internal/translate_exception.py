"""Boundary translation: google-genai/httpx exceptions -> the application error taxonomy.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md`` §6.10. No ``google.genai.errors.*``/``httpx.*``
exception type may escape this module's caller.

Unlike the ``anthropic`` SDK, ``google-genai`` does not expose distinct
``AuthenticationError``/``NotFoundError``/``RateLimitError`` subclasses — its
``errors.APIError`` (and its two subclasses, ``ClientError``/``ServerError``,
which add no new fields) carry only an HTTP-status-shaped ``.code: int``.
Dispatch is therefore on ``.code`` directly, not ``isinstance`` branching —
confirmed against the installed SDK's ``errors.py``.
"""

from google.genai import errors as genai_errors
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

_HTTP_STATUS_UNAUTHORIZED = 401
_HTTP_STATUS_FORBIDDEN = 403
_HTTP_STATUS_NOT_FOUND = 404
_HTTP_STATUS_RATE_LIMITED = 429
_MIN_SERVER_ERROR_STATUS = 500


def translate_chat_exception(exc: Exception, *, context: ErrorContext) -> Exception:
    """Map one google-genai/httpx exception to its taxonomy leaf, redacting the message.

    Table (§6.10, STORY-020-AC-4): a bare ``httpx.TimeoutException`` (the SDK
    does not wrap transport-level timeouts) -> ``HttpTimeoutError``;
    ``genai_errors.APIError`` (including its ``ClientError``/``ServerError``
    subclasses) with ``.code`` 401 or 403 -> ``ProviderAuthError``; ``.code``
    404 -> ``ModelNotAvailableError``; ``.code`` 429 ->
    ``ProviderRateLimitedError``; ``.code`` >= 500 -> ``ProviderServerError``;
    any other ``.code`` -> ``ProviderBadRequestError``; any other bare
    ``httpx`` transport failure (connection refused, DNS failure) ->
    ``HttpConnectionError``; any other unenumerated exception ->
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
    if isinstance(exc, httpx.TimeoutException):
        return HttpTimeoutError(message=message, context=context)
    if isinstance(exc, genai_errors.APIError):
        return _translate_api_error(exc, message=message, context=context)
    if isinstance(exc, httpx.HTTPError):
        return HttpConnectionError(message=message, context=context)
    return ProviderBadRequestError(message=message, context=context)


def _translate_api_error(
    exc: genai_errors.APIError, *, message: str, context: ErrorContext
) -> Exception:
    """Translate a ``google.genai.errors.APIError`` by its ``.code`` (§6.10)."""
    if exc.code in (_HTTP_STATUS_UNAUTHORIZED, _HTTP_STATUS_FORBIDDEN):
        return ProviderAuthError(message=message, context=context)
    if exc.code == _HTTP_STATUS_NOT_FOUND:
        return ModelNotAvailableError(message=message, context=context)
    if exc.code == _HTTP_STATUS_RATE_LIMITED:
        return ProviderRateLimitedError(message=message, context=context, retry_after=None)
    if exc.code >= _MIN_SERVER_ERROR_STATUS:
        return ProviderServerError(message=message, context=context)
    return ProviderBadRequestError(message=message, context=context)


def classify_test_inference_outcome(exc: Exception) -> InferenceTestOutcome:
    """Map a chat exception to ``test_inference``'s outcome enum (§6.8.2).

    ``HttpTimeoutError`` -> ``TIMEOUT``; ``HttpConnectionError`` ->
    ``REACHABILITY_FAILED``; ``ProviderAuthError`` -> ``AUTH_FAILED``;
    ``ModelNotAvailableError`` -> ``MODEL_NOT_FOUND``; anything else
    (including ``TaskCancelledError``, which ``test_inference`` never lets
    escape per §6.8.2 step 8's "never raises" rule) -> ``PROVIDER_ERROR``.

    Args:
        exc: The exception raised by the canned-prompt ``chat`` call —
            already a taxonomy leaf, never a raw SDK type.

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
