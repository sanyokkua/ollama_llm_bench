"""``RetryPolicy`` — the retry primitive's value object.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/18_RETRY_POLICY.md``
§6.2 (per-category retry parameters).

``RetryPolicy`` is caller-constructed configuration, not boundary-decoded data: its
field validity (``attempts >= 1``, non-negative wait/budget values) is enforced by
``with_retry``'s ``icontract`` preconditions in ``api.py``, not by ``msgspec.Meta``
constraints here.
"""

import msgspec

__all__: list[str] = [
    "RetryPolicy",
]


class RetryPolicy(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The attempt/backoff/budget parameters for one retryable operation.

    Attributes:
        attempts: The maximum number of attempts, including the first.
        initial_wait: The backoff wait, in seconds, before the second attempt.
        max_wait: The cap applied to the computed backoff before jitter is added.
        jitter: The half-width, in seconds, of the uniform jitter band added to
            each computed backoff.
        total_budget: The cumulative elapsed-time ceiling, in seconds, across all
            attempts and waits.
    """

    attempts: int
    initial_wait: float
    max_wait: float
    jitter: float
    total_budget: float
