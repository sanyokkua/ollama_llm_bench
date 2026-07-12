"""Adaptive Timeout Service — per-(provider, model, role) timeout budgets and
per-role exclusion tracking.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md``
and ``08_Cross_Cutting/08-E_interfaces_contracts.md`` §17.

Computes a per-attempt timeout budget that starts at a configured minimum, escalates
toward a configured maximum across retries when calls time out, promotes a
last-known-good budget when a call succeeds, and excludes a model from one role after a
run of consecutive maximum-budget timeouts. INFERENCE, JUDGE, and RUN_ANALYSIS keep fully
independent buckets — JUDGE and RUN_ANALYSIS share parameter values (DD-65) but never
share state.
"""

from ollama_llm_bench.backend.adaptive_timeout.api import make_adaptive_timeout_service
from ollama_llm_bench.backend.adaptive_timeout.models import AdaptiveTimeoutModelState
from ollama_llm_bench.backend.adaptive_timeout.protocols import AdaptiveTimeoutService

__all__: list[str] = [
    "AdaptiveTimeoutModelState",
    "AdaptiveTimeoutService",
    "make_adaptive_timeout_service",
]
