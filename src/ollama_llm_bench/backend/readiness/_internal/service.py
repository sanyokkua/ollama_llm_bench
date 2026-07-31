"""The concrete ``ReadinessService`` implementation.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§12; ``docs/v3_specification/11_Services_and_Algorithms/09_READINESS_PROBE.md`` §6, §9;
``docs/v3_specification/08_Cross_Cutting/08-I_edge_cases.md`` EC-RUN-13.

Lock discipline (load-bearing, do not change without re-reading the concurrency
standard): ``self._lock`` guards only the cached snapshot and the in-flight-batch
coalescing state — the two pieces of mutable state this service owns. It is never held
while calling out to the gate, the registry, a client, or the event bus, so a
synchronous event-bus subscriber calling back into this service can never re-enter the
lock. ``probe`` is a leaf unit: it never submits work to the ``TaskRunner`` and never
blocks on a ``Future``. ``probe_all`` is the dispatcher-thread orchestration: it is the
only method in this module that submits work to the ``TaskRunner`` and blocks on the
resulting ``Future``s (DD-38/DD-40). The shared ``TaskRunner`` is typed over ``object``
because one batch submits two different result shapes (``ProviderHealth`` leaf probes,
then one ``bool`` embedding-handshake unit); each submission site's own closure return
type still drives full ``mypy --strict`` checking, and ``.result()`` is cast back to its
known concrete type immediately.
"""

from collections.abc import Callable
from concurrent.futures import Future
import threading
import time
from typing import cast

import structlog

from ollama_llm_bench.backend.concurrency import CancellationToken, TaskRunner
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    GateLease,
    InferenceActivity,
    InferenceActivityContext,
    ProviderConfig,
    ProviderHealth,
    ProviderId,
    ReadinessState,
)
from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.events import (
    SIGNAL_APP_READINESS_CHANGED,
    AppReadinessChangedEvent,
    EventBus,
    ProviderHealthSummary,
)
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.readiness._internal.aggregation import aggregate
from ollama_llm_bench.backend.readiness._internal.embedding_probe import probe_embedding
from ollama_llm_bench.backend.readiness.protocols import (
    ReadinessEmbeddingSelector,
    ReadinessProviderRegistry,
)
from ollama_llm_bench.backend.settings import SettingsService
from ollama_llm_bench.backend.stores.inference_activity import InferenceActivityStore

__all__: list[str] = [
    "ReadinessServiceCollaborators",
    "ReadinessServiceImpl",
]

_logger = structlog.get_logger("app.readiness")

_GATE_WAIT_POLL_INTERVAL_S = 0.05
_GATE_WAIT_MAX_S = 5.0

_PROBE_TIMEOUT_MS_KEY = "provider.probe_timeout_ms"

_CHECKING_SNAPSHOT = AppReadinessSnapshot(
    overall=ReadinessState.CHECKING, per_provider=(), embedding_reachable=False
)


class ReadinessServiceCollaborators:
    """Groups the concrete service's constructor dependencies (<=4-parameter rule).

    A plain, private-implementation-detail bundle — not a cross-boundary DTO,
    so it is an ordinary class rather than a ``msgspec.Struct``; it never
    leaves this ``_internal`` package.
    """

    def __init__(  # noqa: PLR0913  # this class exists solely to bundle these seven
        # collaborators so ReadinessServiceImpl.__init__ itself takes one argument,
        # per the coding-style dependency-bundle exemption for >4-parameter factories
        self,
        *,
        registry: ReadinessProviderRegistry,
        embedding_selector: ReadinessEmbeddingSelector,
        settings: SettingsService,
        gate: InferenceActivityStore,
        event_bus: EventBus,
        task_runner: TaskRunner[object],
        clock: Clock,
    ) -> None:
        self.registry = registry
        self.embedding_selector = embedding_selector
        self.settings = settings
        self.gate = gate
        self.event_bus = event_bus
        self.task_runner = task_runner
        self.clock = clock


class ReadinessServiceImpl:
    """Aggregates provider and embedding health into one readiness snapshot.

    ``snapshot()`` never probes. ``probe()`` is a blocking leaf unit run on
    a ``TaskRunner`` worker thread. ``probe_all()`` is the dispatcher-thread
    orchestration that fans the per-provider reachability handshakes out to
    the shared ``TaskRunner`` concurrently, joins them, then runs the single
    handshake-only embedding probe serially, aggregates, and emits
    ``_app_readiness_changed`` only on a real change. Overlapping
    ``probe_all`` calls coalesce onto one shared in-flight batch.
    ``record_embedding_capability_result()`` lets ``SettingsGateway``'s
    billable Test-Embedding check (STORY-110) feed its stronger signal into
    this same cached snapshot/emission path, so a later ``snapshot()`` read
    (e.g. the New Benchmark widget's ``GRADED``-mode gate) reflects it.
    """

    def __init__(self, *, collaborators: ReadinessServiceCollaborators) -> None:
        self._registry = collaborators.registry
        self._embedding_selector = collaborators.embedding_selector
        self._settings = collaborators.settings
        self._gate = collaborators.gate
        self._event_bus = collaborators.event_bus
        self._task_runner = collaborators.task_runner
        self._clock = collaborators.clock
        self._lock = threading.Lock()
        self._cached_snapshot: AppReadinessSnapshot = _CHECKING_SNAPSHOT
        self._in_flight: Future[AppReadinessSnapshot] | None = None

    def snapshot(self) -> AppReadinessSnapshot:
        """Return the cached snapshot. fast-synchronous; never probes; never raises."""
        with self._lock:
            return self._cached_snapshot

    def probe(self, provider_id: ProviderId) -> ProviderHealth:
        """Probe one provider. Blocking leaf unit; never raises (STORY-016-AC-7)."""
        lease = self._acquire_gate_with_one_deferral(provider_id=provider_id)
        if lease is None:
            return self._deferred_health(provider_id)
        try:
            return self._probe_one(provider_id)
        finally:
            self._gate.release(lease)

    def probe_all(self) -> AppReadinessSnapshot:
        """Orchestrate one probe batch on the dispatcher thread; coalesce overlaps."""
        future = self._join_or_start_batch()
        return future.result()

    def record_embedding_capability_result(self, *, reachable: bool) -> None:
        """Record a billable ``embed()`` capability-check outcome (STORY-110).

        fast-synchronous; never raises. Recomputes ``overall`` from the
        cached snapshot's per-provider health plus ``reachable`` through the
        same ``aggregate`` fold ``probe_all`` uses, then caches and
        conditionally emits through the same ``_store_and_maybe_emit`` path
        -- there is exactly one emission code path in this service.
        """
        with self._lock:
            current = self._cached_snapshot
        new_snapshot = aggregate(current.per_provider, embedding_ok=reachable)
        self._store_and_maybe_emit(new_snapshot)

    # -- coalescing (§6.6) --------------------------------------------------------

    def _join_or_start_batch(self) -> Future[AppReadinessSnapshot]:
        """Return the shared in-flight batch, starting a fresh one if none runs."""
        with self._lock:
            if self._in_flight is not None:
                return self._in_flight
            batch: Future[AppReadinessSnapshot] = Future()
            self._in_flight = batch
        self._run_batch(batch)
        return batch

    def _run_batch(self, batch: Future[AppReadinessSnapshot]) -> None:
        """Run exactly one probe batch and settle ``batch``, clearing the in-flight slot."""
        try:
            result = self._probe_all_once()
        except BaseException as exc:  # noqa: BLE001  # captured on the Future, never swallowed
            with self._lock:
                self._in_flight = None
            batch.set_exception(exc)
            return
        with self._lock:
            self._in_flight = None
        batch.set_result(result)

    # -- the batch itself (§6.4) --------------------------------------------------

    def _probe_all_once(self) -> AppReadinessSnapshot:
        """Run one genuinely fresh probe batch: gate, fan-out, embed, aggregate, emit."""
        lease = self._acquire_gate_with_one_deferral(provider_id=None)
        if lease is None:
            return self.snapshot()
        try:
            return self._run_batch_under_gate()
        finally:
            self._gate.release(lease)

    def _run_batch_under_gate(self) -> AppReadinessSnapshot:
        """The dispatcher-thread fan-out/join/embed/aggregate sequence (DD-38/DD-40)."""
        providers = self._registry.list_enabled()
        token = CancellationToken(clock=self._clock)
        timeout_s = self._probe_timeout_seconds()
        health_results = self._fan_out_health_probes(providers, token, timeout_s)
        embedding_ok = self._run_embedding_unit(health_results, token, timeout_s)
        new_snapshot = aggregate(health_results, embedding_ok=embedding_ok)
        self._store_and_maybe_emit(new_snapshot)
        return new_snapshot

    def _probe_timeout_seconds(self) -> float:
        """Read ``provider.probe_timeout_ms`` and convert it to seconds for ``Future.result``."""
        return self._settings.get_int(_PROBE_TIMEOUT_MS_KEY) / 1000.0

    def _fan_out_health_probes(
        self,
        providers: tuple[ProviderConfig, ...],
        token: CancellationToken,
        timeout_s: float,
    ) -> tuple[ProviderHealth, ...]:
        """Submit one reachability leaf unit per provider and join every ``Future``."""
        futures: list[tuple[ProviderId, Future[object]]] = [
            (
                provider.provider_id,
                self._task_runner.submit(self._make_probe_unit(provider.provider_id), token=token),
            )
            for provider in providers
        ]
        return tuple(
            self._await_health_result(provider_id, future, timeout_s)
            for provider_id, future in futures
        )

    def _await_health_result(
        self, provider_id: ProviderId, future: Future[object], timeout_s: float
    ) -> ProviderHealth:
        """Join one leaf probe's ``Future``, collapsing a timeout to unreachable data."""
        try:
            return cast("ProviderHealth", future.result(timeout=timeout_s))
        except TimeoutError:
            return self._timed_out_health(provider_id)

    def _timed_out_health(self, provider_id: ProviderId) -> ProviderHealth:
        """The reported outcome when a leaf probe exceeds ``provider.probe_timeout_ms``."""
        return ProviderHealth(
            provider_id=provider_id,
            reachable=False,
            discovery_supported=False,
            model_count=None,
            last_probe_ms=0,
            last_error="probe exceeded the configured timeout",
            probed_at=self._clock.monotonic_ms(),
        )

    def _make_probe_unit(self, provider_id: ProviderId) -> Callable[[], ProviderHealth]:
        """Build the zero-argument reachability-probe unit for one provider."""

        def _probe_unit() -> ProviderHealth:
            return self._probe_one(provider_id)

        return _probe_unit

    def _run_embedding_unit(
        self,
        health_results: tuple[ProviderHealth, ...],
        token: CancellationToken,
        timeout_s: float,
    ) -> bool:
        """Submit the single, serial, handshake-only embedding-probe unit."""

        def _embedding_unit() -> bool:
            return probe_embedding(
                selector=self._embedding_selector,
                registry=self._registry,
                batch_health=health_results,
            )

        future = self._task_runner.submit(_embedding_unit, token=token)
        try:
            return cast("bool", future.result(timeout=timeout_s))
        except TimeoutError:
            return False

    # -- one-provider probe (§6.2) -------------------------------------------------

    def _probe_one(self, provider_id: ProviderId) -> ProviderHealth:
        """Registry lookup then ``LLMClient.probe_health()``; never raises."""
        try:
            client = self._registry.get_client(provider_id)
        except ConfigurationError:
            return ProviderHealth(
                provider_id=provider_id,
                reachable=False,
                discovery_supported=False,
                model_count=None,
                last_probe_ms=0,
                last_error="missing environment variable",
                probed_at=self._clock.monotonic_ms(),
            )
        try:
            return client.probe_health()
        except Exception as exc:  # noqa: BLE001  # collapsed to unreachable data, per §5/§8
            _logger.warning(
                "readiness_probe_health_check_failed",
                provider_id=provider_id,
                error=str(exc),
            )
            return ProviderHealth(
                provider_id=provider_id,
                reachable=False,
                discovery_supported=False,
                model_count=None,
                last_probe_ms=0,
                last_error="probe failed unexpectedly",
                probed_at=self._clock.monotonic_ms(),
            )

    def _deferred_health(self, provider_id: ProviderId) -> ProviderHealth:
        """The reported outcome for a probe deferred by a held gate (EC-RUN-13)."""
        _logger.info("readiness_probe_deferred", provider_id=provider_id)
        return ProviderHealth(
            provider_id=provider_id,
            reachable=False,
            discovery_supported=False,
            model_count=None,
            last_probe_ms=0,
            last_error="Checking deferred — run in progress",
            probed_at=self._clock.monotonic_ms(),
        )

    # -- the single-inference gate (§9, EC-RUN-13) ---------------------------------

    def _acquire_gate_with_one_deferral(
        self, *, provider_id: ProviderId | None
    ) -> GateLease | None:
        """Try the gate; on refusal wait for ``IDLE`` once, then try exactly once more.

        Never queues indefinitely (EC-RUN-13): a request refused twice —
        including after waiting for the gate to go idle — is reported as
        deferred, not retried further.
        """
        lease = self._try_acquire(provider_id)
        if lease is not None:
            return lease
        _logger.info("readiness_probe_deferred_waiting_for_idle", provider_id=provider_id)
        if not self._wait_for_idle():
            return None
        return self._try_acquire(provider_id)

    def _try_acquire(self, provider_id: ProviderId | None) -> GateLease | None:
        context = InferenceActivityContext(
            activity=InferenceActivity.READINESS_PROBE,
            started_at=self._clock.monotonic_ms(),
            provider_id=provider_id,
        )
        return self._gate.try_acquire(InferenceActivity.READINESS_PROBE, context)

    def _wait_for_idle(self) -> bool:
        """Poll the gate for ``IDLE`` up to ``_GATE_WAIT_MAX_S``; return whether it went idle."""
        deadline = time.monotonic() + _GATE_WAIT_MAX_S
        while time.monotonic() < deadline:
            if not self._gate.is_busy():
                return True
            time.sleep(_GATE_WAIT_POLL_INTERVAL_S)
        return not self._gate.is_busy()

    # -- change detection + event emission ------------------------------------------

    def _store_and_maybe_emit(self, new_snapshot: AppReadinessSnapshot) -> None:
        """Cache ``new_snapshot`` and emit ``_app_readiness_changed`` iff it changed."""
        with self._lock:
            changed = new_snapshot != self._cached_snapshot
            self._cached_snapshot = new_snapshot
        if changed:
            self._emit_readiness_changed(new_snapshot)

    def _emit_readiness_changed(self, new_snapshot: AppReadinessSnapshot) -> None:
        """Publish ``_app_readiness_changed`` for a genuinely changed snapshot."""
        summaries = tuple(
            ProviderHealthSummary(
                provider_id=health.provider_id,
                reachable=health.reachable,
                discovery_supported=health.discovery_supported,
                model_count=health.model_count,
                last_error=health.last_error,
            )
            for health in new_snapshot.per_provider
        )
        self._event_bus.emit(
            SIGNAL_APP_READINESS_CHANGED,
            AppReadinessChangedEvent(
                overall=new_snapshot.overall,
                per_provider=summaries,
                embedding_reachable=new_snapshot.embedding_reachable,
                checked_at=self._clock.now_utc(),
            ),
        )
