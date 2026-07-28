"""Proves STORY-101-AC-1 — the breaker's state machine matches §6.2-§6.5 for every
legal transition. Also exercises STORY-101-AC-3's PROBING-admits-no-task invariant
via the `should_skip_is_idempotent` rule and the `probing_implies_no_admission`
invariant (the AC-3 proving test itself lives in `test_tripping.py`)."""

import math

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule
import pytest

from ollama_llm_bench.backend.circuit_breaker import (
    CircuitState,
    ProviderCircuitBreaker,
    make_circuit_breaker,
)
from ollama_llm_bench.backend.circuit_breaker.tests.conftest import FakeClock, build_snapshot

_PROVIDER = "p1"
_FAILURE_THRESHOLD = 3
_COOLDOWN_SECONDS = 60
_COOLDOWN_MS = _COOLDOWN_SECONDS * 1000


class _CircuitBreakerStateMachine(RuleBasedStateMachine):
    """Walks record_success/record_failure/clock-advance/query rules and checks
    §6.2-§6.5's state machine against an independently-tracked expected state."""

    breaker: ProviderCircuitBreaker
    clock: FakeClock

    def __init__(self) -> None:
        super().__init__()
        self.clock = FakeClock()
        snapshot = build_snapshot(
            failure_threshold=_FAILURE_THRESHOLD, cooldown_seconds=_COOLDOWN_SECONDS
        )
        self.breaker = make_circuit_breaker(snapshot=snapshot, clock=self.clock)
        self.expected_state = CircuitState.CLOSED
        self.expected_failures = 0
        self.expected_cooldown_started_ms: int | None = None

    def _sync_lazy_probe_transition(self) -> None:
        if self.expected_state is CircuitState.TRIPPED:
            assert self.expected_cooldown_started_ms is not None
            elapsed_ms = self.clock.monotonic_ms() - self.expected_cooldown_started_ms
            if elapsed_ms >= _COOLDOWN_MS:
                self.expected_state = CircuitState.PROBING

    @rule()
    def record_success(self) -> None:
        self._sync_lazy_probe_transition()
        self.breaker.record_success(_PROVIDER)
        if self.expected_state is CircuitState.PROBING:
            self.expected_state = CircuitState.CLOSED
            self.expected_failures = 0
            self.expected_cooldown_started_ms = None
        elif self.expected_state is CircuitState.CLOSED:
            self.expected_failures = 0
        # TRIPPED: no-op.

    @rule()
    def record_failure(self) -> None:
        self._sync_lazy_probe_transition()
        self.breaker.record_failure(_PROVIDER)
        if self.expected_state is CircuitState.CLOSED:
            self.expected_failures += 1
            if self.expected_failures >= _FAILURE_THRESHOLD:
                self.expected_state = CircuitState.TRIPPED
                self.expected_cooldown_started_ms = self.clock.monotonic_ms()
        elif self.expected_state is CircuitState.PROBING:
            self.expected_state = CircuitState.TRIPPED
            self.expected_cooldown_started_ms = self.clock.monotonic_ms()
        # TRIPPED: skipped-task bookkeeping, no-op.

    @rule(delta_ms=st.integers(min_value=0, max_value=_COOLDOWN_MS * 2))
    def advance_clock(self, delta_ms: int) -> None:
        self.clock.advance_monotonic_ms(delta_ms)

    @rule()
    def query_state(self) -> None:
        self._sync_lazy_probe_transition()
        assert self.breaker.state(_PROVIDER) == self.expected_state

    @rule()
    def query_should_skip(self) -> None:
        self._sync_lazy_probe_transition()
        expected_skip = self.expected_state is not CircuitState.CLOSED
        assert self.breaker.should_skip(_PROVIDER) == expected_skip

    @rule()
    def should_skip_is_idempotent(self) -> None:
        """STORY-101-AC-3: repeated `should_skip` queries with no intervening
        mutation return the same value every time, in every state — the
        property the old probe-slot design violated for PROBING."""
        self._sync_lazy_probe_transition()
        first = self.breaker.should_skip(_PROVIDER)
        second = self.breaker.should_skip(_PROVIDER)
        assert first == second

    @rule()
    def query_cooldown_remaining(self) -> None:
        self._sync_lazy_probe_transition()
        if self.expected_state is not CircuitState.TRIPPED:
            expected_remaining = None
        else:
            assert self.expected_cooldown_started_ms is not None
            elapsed_ms = self.clock.monotonic_ms() - self.expected_cooldown_started_ms
            expected_remaining = math.ceil((_COOLDOWN_MS - elapsed_ms) / 1000)
        assert self.breaker.cooldown_remaining_seconds(_PROVIDER) == expected_remaining

    @invariant()
    def state_matches_expected(self) -> None:
        self._sync_lazy_probe_transition()
        assert self.breaker.state(_PROVIDER) == self.expected_state

    @invariant()
    def probing_implies_no_admission(self) -> None:
        """STORY-101-AC-3: whenever the breaker is PROBING, `should_skip` must
        be `True` — PROBING never admits a benchmark task."""
        self._sync_lazy_probe_transition()
        if self.expected_state is CircuitState.PROBING:
            assert self.breaker.should_skip(_PROVIDER) is True


# Hypothesis builds `.TestCase` dynamically per state machine, so it is a runtime
# value, not a statically-known type -- mypy cannot check a class-body subclassing a
# dynamically-constructed base. Only one `unittest.TestCase` subclass is bound at
# module scope (this one) so pytest's default collector picks up exactly one case.
@pytest.mark.slow
class TestCircuitBreakerStateMachine(_CircuitBreakerStateMachine.TestCase):  # type: ignore[misc,valid-type]
    """Runs ``_CircuitBreakerStateMachine`` as a pytest-collected unittest.TestCase."""

    def runTest(self) -> None:
        """Proves: STORY-101-AC-1

        Walks every legal record_success/record_failure/clock-advance/query
        sequence and checks the resulting (state, should_skip,
        cooldown_remaining_seconds) against the §6.2-§6.5 state machine after
        every step. Also runs the `should_skip_is_idempotent` rule and the
        `probing_implies_no_admission` invariant proving STORY-101-AC-3:
        `should_skip` is a pure, side-effect-free function of state that
        always returns `True` while PROBING.
        """
        super().runTest()
