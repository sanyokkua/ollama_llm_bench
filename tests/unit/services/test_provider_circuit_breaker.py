"""Unit tests for ProviderCircuitBreaker — multi-provider sliding-window stuck detection."""

import threading
import time

from ollama_llm_bench.backend.services.provider_circuit_breaker import (
    HEALTHY,
    PROBING,
    TRIPPED,
    ProviderCircuitBreaker,
)

_PROVIDER_A = "provider_a"
_PROVIDER_B = "provider_b"
_MODEL_X = "model_x"
_MODEL_Y = "model_y"


def _make(
    *,
    threshold: int = 3,
    window_s: float = 600.0,
    probe_interval_s: float = 60.0,
) -> ProviderCircuitBreaker:
    return ProviderCircuitBreaker(
        failure_threshold=threshold,
        window_s=window_s,
        probe_interval_s=probe_interval_s,
    )


def _trip(cb: ProviderCircuitBreaker, provider_id: str, *, models: list[str], times_each: int = 1) -> None:
    """Record failures across the given models to drive the circuit to TRIPPED."""
    for _ in range(times_each):
        for model in models:
            cb.record_failure(provider_id, model_name=model, reason="timeout")


class TestHealthyState:
    def test_fresh_breaker_is_healthy(self) -> None:
        cb = _make()
        assert cb.state(_PROVIDER_A) == HEALTHY

    def test_fresh_breaker_allows_dispatch(self) -> None:
        cb = _make()
        assert cb.should_dispatch(_PROVIDER_A) is True

    def test_unknown_provider_is_healthy(self) -> None:
        cb = _make()
        assert cb.state("brand_new_provider") == HEALTHY


class TestTrippingLogic:
    def test_single_model_failures_do_not_trip(self) -> None:
        cb = _make(threshold=3)
        for _ in range(10):
            cb.record_failure(_PROVIDER_A, model_name=_MODEL_X, reason="timeout")
        assert cb.state(_PROVIDER_A) == HEALTHY
        assert cb.should_dispatch(_PROVIDER_A) is True

    def test_does_not_trip_before_threshold(self) -> None:
        cb = _make(threshold=4)
        # 3 failures across 2 models — one below threshold
        cb.record_failure(_PROVIDER_A, model_name=_MODEL_X, reason="timeout")
        cb.record_failure(_PROVIDER_A, model_name=_MODEL_Y, reason="timeout")
        cb.record_failure(_PROVIDER_A, model_name=_MODEL_X, reason="timeout")
        assert cb.state(_PROVIDER_A) == HEALTHY

    def test_trips_after_threshold_across_two_models(self) -> None:
        cb = _make(threshold=3)
        cb.record_failure(_PROVIDER_A, model_name=_MODEL_X, reason="timeout")
        cb.record_failure(_PROVIDER_A, model_name=_MODEL_Y, reason="timeout")
        cb.record_failure(_PROVIDER_A, model_name=_MODEL_X, reason="timeout")
        assert cb.state(_PROVIDER_A) == TRIPPED
        assert cb.should_dispatch(_PROVIDER_A) is False

    def test_tripped_provider_does_not_affect_other_provider(self) -> None:
        cb = _make(threshold=3)
        _trip(cb, _PROVIDER_A, models=[_MODEL_X, _MODEL_Y], times_each=2)
        assert cb.state(_PROVIDER_A) == TRIPPED
        assert cb.state(_PROVIDER_B) == HEALTHY
        assert cb.should_dispatch(_PROVIDER_B) is True


class TestProbingState:
    def test_transitions_to_probing_after_cooldown(self) -> None:
        cb = _make(threshold=3, probe_interval_s=0.02)
        _trip(cb, _PROVIDER_A, models=[_MODEL_X, _MODEL_Y], times_each=2)
        assert cb.state(_PROVIDER_A) == TRIPPED
        time.sleep(0.2)
        assert cb.state(_PROVIDER_A) == PROBING

    def test_probing_allows_dispatch(self) -> None:
        cb = _make(threshold=3, probe_interval_s=0.02)
        _trip(cb, _PROVIDER_A, models=[_MODEL_X, _MODEL_Y], times_each=2)
        time.sleep(0.2)
        assert cb.should_dispatch(_PROVIDER_A) is True

    def test_success_from_probing_returns_to_healthy(self) -> None:
        cb = _make(threshold=3, probe_interval_s=0.02)
        _trip(cb, _PROVIDER_A, models=[_MODEL_X, _MODEL_Y], times_each=2)
        time.sleep(0.2)
        cb.record_success(_PROVIDER_A)
        assert cb.state(_PROVIDER_A) == HEALTHY

    def test_failure_from_probing_stays_tripped(self) -> None:
        cb = _make(threshold=3, probe_interval_s=0.02)
        _trip(cb, _PROVIDER_A, models=[_MODEL_X, _MODEL_Y], times_each=2)
        time.sleep(0.2)
        # A further failure while in the probe window resets the last_failure_time,
        # causing the probe window to restart → back to TRIPPED view.
        cb.record_failure(_PROVIDER_A, model_name=_MODEL_X, reason="timeout")
        assert cb.state(_PROVIDER_A) == TRIPPED


class TestRecordSuccess:
    def test_success_resets_to_healthy(self) -> None:
        cb = _make(threshold=3)
        _trip(cb, _PROVIDER_A, models=[_MODEL_X, _MODEL_Y], times_each=2)
        cb.record_success(_PROVIDER_A)
        assert cb.state(_PROVIDER_A) == HEALTHY
        assert cb.should_dispatch(_PROVIDER_A) is True

    def test_success_on_healthy_stays_healthy(self) -> None:
        cb = _make()
        cb.record_success(_PROVIDER_A)
        assert cb.state(_PROVIDER_A) == HEALTHY


class TestWindowPurging:
    def test_stale_failures_not_counted(self) -> None:
        cb = _make(threshold=3, window_s=0.02)
        cb.record_failure(_PROVIDER_A, model_name=_MODEL_X, reason="timeout")
        cb.record_failure(_PROVIDER_A, model_name=_MODEL_Y, reason="timeout")
        time.sleep(0.2)
        # New failure — but old ones are purged, window has only 1 entry
        cb.record_failure(_PROVIDER_A, model_name=_MODEL_X, reason="timeout")
        assert cb.state(_PROVIDER_A) == HEALTHY

    def test_within_window_failures_trip(self) -> None:
        cb = _make(threshold=3, window_s=10.0)
        _trip(cb, _PROVIDER_A, models=[_MODEL_X, _MODEL_Y], times_each=2)
        assert cb.state(_PROVIDER_A) == TRIPPED


class TestReset:
    def test_reset_clears_tripped_state(self) -> None:
        cb = _make(threshold=3)
        _trip(cb, _PROVIDER_A, models=[_MODEL_X, _MODEL_Y], times_each=2)
        cb.reset(_PROVIDER_A)
        assert cb.state(_PROVIDER_A) == HEALTHY
        assert cb.should_dispatch(_PROVIDER_A) is True

    def test_reset_on_healthy_is_noop(self) -> None:
        cb = _make()
        cb.reset(_PROVIDER_A)
        assert cb.state(_PROVIDER_A) == HEALTHY


class TestThreadSafety:
    def test_concurrent_record_failure_and_success_no_exception(self) -> None:
        cb = _make(threshold=5)
        errors: list[Exception] = []

        def record_failures() -> None:
            try:
                for _ in range(100):
                    cb.record_failure(_PROVIDER_A, model_name=_MODEL_X, reason="timeout")
                    cb.record_failure(_PROVIDER_A, model_name=_MODEL_Y, reason="conn")
            except Exception as exc:
                errors.append(exc)

        def record_successes() -> None:
            try:
                for _ in range(100):
                    cb.record_success(_PROVIDER_A)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=record_failures) for _ in range(4)]
        threads += [threading.Thread(target=record_successes) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Exceptions raised: {errors}"
