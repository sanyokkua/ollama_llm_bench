"""The transient-only retry primitive with bounded exponential backoff.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/18_RETRY_POLICY.md``
§6.1 (the retry filter), §6.2 (per-category retry parameters), §6.3 (backoff
computation), §6.4 (honouring a provider retry-after), §6.5 (respecting cancellation).

Gives a momentary, transient failure a bounded number of further attempts with
exponential backoff and jitter, while guaranteeing a non-transient failure surfaces on
its first occurrence and that a pause or stop is honoured between attempts. This is the
single retry primitive the provider adapters and the persistence layer wrap their
blocking calls in — see ``with_retry`` and ``default_transient_policy``.
"""

from ollama_llm_bench.backend.retry.api import default_transient_policy, with_retry
from ollama_llm_bench.backend.retry.models import RetryPolicy

__all__: list[str] = [
    "RetryPolicy",
    "default_transient_policy",
    "with_retry",
]
