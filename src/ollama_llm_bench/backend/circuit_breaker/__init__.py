"""Provider Circuit Breaker — per-provider failure tripping and probe-recovery.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md``
and ``08_Cross_Cutting/08-E_interfaces_contracts.md`` §18.

Watches the stream of per-provider task outcomes the pipeline feeds it, trips a
provider out of the run after a configured number of consecutive
provider-attributable failures, and skips every remaining task against it for a
fixed cooldown window with no network call. Once the cooldown elapses the
breaker lazily moves to ``PROBING``, which still admits no benchmark task: the
pipeline issues a dedicated lightweight liveness call before each row against a
``PROBING`` provider (DD-71, ADR-0013) and reports its outcome back to this
breaker, closing it on success or re-tripping it for a fresh cooldown window on
failure. Run-scoped, per-provider, purely in-memory; holds no durable state and
is discarded when the run ends.
"""

from ollama_llm_bench.backend.circuit_breaker.api import make_circuit_breaker
from ollama_llm_bench.backend.circuit_breaker.models import CircuitState
from ollama_llm_bench.backend.circuit_breaker.protocols import ProviderCircuitBreaker

__all__: list[str] = [
    "CircuitState",
    "ProviderCircuitBreaker",
    "make_circuit_breaker",
]
