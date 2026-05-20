"""LLM error classification for provider-agnostic warm-up retry logic and capability discovery."""

import logging
import re
from dataclasses import dataclass

import openai

logger = logging.getLogger(__name__)

_THINKING_RE = re.compile(r'(?i)"?[\w:.\-/]+"?\s+does\s+not\s+support\s+thinking')
_CONTEXT_LENGTH_RE = re.compile(r"(?i)context.*length|too\s+many\s+tokens")
_SERVER_ERROR_RE = re.compile(r"Error code: 5\d\d")


@dataclass(slots=True, frozen=True, kw_only=True)
class LlmErrorClassification:
    """Structured classification of an LLM API error.

    Attributes:
        is_retryable: True when the error is transient and the call should be retried.
        is_capability_signal: True when the error reveals a model capability limitation.
        capability_unsupported: The capability name that is unsupported, or None.
        http_status: HTTP status code if available, or None.
        structured_code: Provider-specific error code if available, or None.
        raw_message: Raw error message string.
        classification_reason: Short snake_case description of the classification path taken.
    """

    is_retryable: bool
    is_capability_signal: bool
    capability_unsupported: str | None
    http_status: int | None
    structured_code: str | None
    raw_message: str
    classification_reason: str


class LlmErrorClassifier:
    """Stateless classifier for LLM API errors.

    Translates openai SDK exceptions and pre-stringified error messages into
    structured LlmErrorClassification instances used to drive warm-up retry
    logic and capability discovery.  Both live exception and message-string
    paths apply the same capability-detection regexes so that warm-up results
    are consistent regardless of how the error surfaces.
    """

    def classify(self, exc: BaseException) -> LlmErrorClassification:
        """Classify a live exception raised by an openai SDK call.

        Args:
            exc: Exception to classify; non-openai exceptions are classified as unknown.

        Returns:
            LlmErrorClassification describing retryability and capability signals.
        """
        raw = str(exc)

        if isinstance(exc, openai.APITimeoutError):
            return LlmErrorClassification(
                is_retryable=True,
                is_capability_signal=False,
                capability_unsupported=None,
                http_status=None,
                structured_code=None,
                raw_message=raw,
                classification_reason="timeout",
            )

        if isinstance(exc, openai.APIConnectionError):
            return LlmErrorClassification(
                is_retryable=True,
                is_capability_signal=False,
                capability_unsupported=None,
                http_status=None,
                structured_code=None,
                raw_message=raw,
                classification_reason="connection_error",
            )

        if isinstance(exc, openai.RateLimitError):
            return LlmErrorClassification(
                is_retryable=True,
                is_capability_signal=False,
                capability_unsupported=None,
                http_status=429,
                structured_code=None,
                raw_message=raw,
                classification_reason="rate_limit_429",
            )

        if isinstance(exc, openai.InternalServerError):
            return LlmErrorClassification(
                is_retryable=True,
                is_capability_signal=False,
                capability_unsupported=None,
                http_status=getattr(exc, "status_code", None),
                structured_code=None,
                raw_message=raw,
                classification_reason="server_error_5xx",
            )

        if isinstance(exc, openai.BadRequestError):
            return self._classify_bad_request(raw)

        if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
            return LlmErrorClassification(
                is_retryable=False,
                is_capability_signal=False,
                capability_unsupported=None,
                http_status=getattr(exc, "status_code", None),
                structured_code=None,
                raw_message=raw,
                classification_reason="auth_error",
            )

        if isinstance(exc, openai.NotFoundError):
            return LlmErrorClassification(
                is_retryable=False,
                is_capability_signal=True,
                capability_unsupported="model",
                http_status=404,
                structured_code=None,
                raw_message=raw,
                classification_reason="not_found_404",
            )

        return LlmErrorClassification(
            is_retryable=False,
            is_capability_signal=False,
            capability_unsupported=None,
            http_status=None,
            structured_code=None,
            raw_message=raw,
            classification_reason="unknown",
        )

    def classify_from_message(self, msg: str) -> LlmErrorClassification:
        """Classify a pre-stringified error message from InferenceResponse.error_message.

        Args:
            msg: Error message string; empty string produces a non-retryable unknown result.

        Returns:
            LlmErrorClassification based on pattern matching against the message.
        """
        if not msg:
            return LlmErrorClassification(
                is_retryable=False,
                is_capability_signal=False,
                capability_unsupported=None,
                http_status=None,
                structured_code=None,
                raw_message=msg,
                classification_reason="empty_message",
            )

        if _THINKING_RE.search(msg):
            return LlmErrorClassification(
                is_retryable=False,
                is_capability_signal=True,
                capability_unsupported="thinking",
                http_status=400,
                structured_code=None,
                raw_message=msg,
                classification_reason="bad_request_thinking_unsupported",
            )

        if _CONTEXT_LENGTH_RE.search(msg):
            return LlmErrorClassification(
                is_retryable=False,
                is_capability_signal=True,
                capability_unsupported="context_length",
                http_status=400,
                structured_code=None,
                raw_message=msg,
                classification_reason="bad_request_context_length",
            )

        if _SERVER_ERROR_RE.search(msg):
            return LlmErrorClassification(
                is_retryable=True,
                is_capability_signal=False,
                capability_unsupported=None,
                http_status=None,
                structured_code=None,
                raw_message=msg,
                classification_reason="server_error_5xx_from_message",
            )

        if "Error code: 404" in msg:
            return LlmErrorClassification(
                is_retryable=False,
                is_capability_signal=True,
                capability_unsupported="model",
                http_status=404,
                structured_code=None,
                raw_message=msg,
                classification_reason="not_found_404",
            )

        if "Error code: 401" in msg or "Error code: 403" in msg:
            return LlmErrorClassification(
                is_retryable=False,
                is_capability_signal=False,
                capability_unsupported=None,
                http_status=None,
                structured_code=None,
                raw_message=msg,
                classification_reason="auth_error",
            )

        if "Error code: 4" in msg:
            logger.info("llm_error_classifier_unmatched_4xx", extra={"msg_prefix": msg[:120]})
            return LlmErrorClassification(
                is_retryable=False,
                is_capability_signal=False,
                capability_unsupported=None,
                http_status=None,
                structured_code=None,
                raw_message=msg,
                classification_reason="client_error_4xx",
            )

        return LlmErrorClassification(
            is_retryable=False,
            is_capability_signal=False,
            capability_unsupported=None,
            http_status=None,
            structured_code=None,
            raw_message=msg,
            classification_reason="unknown_from_message",
        )

    def _classify_bad_request(self, raw: str) -> LlmErrorClassification:
        """Classify a 400 BadRequest error by applying capability-signal regexes.

        Args:
            raw: Stringified exception message.

        Returns:
            LlmErrorClassification with appropriate capability signal if detected.
        """
        if _THINKING_RE.search(raw):
            return LlmErrorClassification(
                is_retryable=False,
                is_capability_signal=True,
                capability_unsupported="thinking",
                http_status=400,
                structured_code=None,
                raw_message=raw,
                classification_reason="bad_request_thinking_unsupported",
            )

        if _CONTEXT_LENGTH_RE.search(raw):
            return LlmErrorClassification(
                is_retryable=False,
                is_capability_signal=True,
                capability_unsupported="context_length",
                http_status=400,
                structured_code=None,
                raw_message=raw,
                classification_reason="bad_request_context_length",
            )

        return LlmErrorClassification(
            is_retryable=False,
            is_capability_signal=False,
            capability_unsupported=None,
            http_status=400,
            structured_code=None,
            raw_message=raw,
            classification_reason="bad_request_generic",
        )
