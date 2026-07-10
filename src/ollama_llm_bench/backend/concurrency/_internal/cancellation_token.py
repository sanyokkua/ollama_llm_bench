"""The concrete, two-level ``CancellationToken`` implementation (DD-39, DD-42).

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§5 (the ``CancellationToken``); ``docs/v3_specification/11_Services_and_Algorithms/
16_CONCURRENCY_MODEL.md`` §6.3 (the single ``CancellationToken``).

Cooperative, explicit, framework-agnostic cancellation backed by ``threading.Event``
(never ``asyncio.Event`` — there is no event loop anywhere in this application). One
instance is constructed per run via ``api.make_cancellation_token`` and threaded through
every unit of that run; it is never a process-wide singleton and never reused across
runs.

Lock discipline (load-bearing, do not change without re-reading the concurrency
standard): the level/reason pair is guarded by ``self._lock`` as a single atomic unit
(DD-42 — a torn read of a hard level with a stale soft reason must be impossible). The
hard-cancel hook list is guarded by a **separate** ``self._hooks_lock`` so that invoking a
hook — arbitrary caller-supplied code — can never deadlock against a concurrent
``cancel()`` or ``snapshot()`` call blocked on ``self._lock``. Hooks are invoked outside
both locks, each wrapped in its own ``try``/``except Exception`` so one misbehaving hook
never prevents the others from running and never prevents ``cancel()`` from returning to
its caller.
"""

from collections.abc import Callable
import contextlib
import threading

import structlog

from ollama_llm_bench.backend.domain.models import CancelLevel, CancelReason
from ollama_llm_bench.backend.errors import TaskCancelledError, redact
from ollama_llm_bench.backend.infra.protocols import Clock

__all__: list[str] = [
    "CancellationToken",
]

_logger = structlog.get_logger("app.concurrency")

_HardCancelHook = Callable[[], None]


class CancellationToken:
    """Cooperative, two-level, thread-safe cancellation handle (DD-39).

    Qt-free, asyncio-free. Levels are monotonic: ``NONE -> SOFT -> HARD``, never
    downgraded. Controller/UI code (any thread, typically the GUI thread) calls
    ``cancel(reason=..., hard=...)``; backend worker code calls
    ``raise_if_cancelled()`` at safe checkpoints. The LLM client polls
    ``is_hard_cancelled`` at chunk boundaries and registers a hard-cancel abort
    hook around each in-flight streaming call.
    """

    def __init__(self, *, clock: Clock) -> None:
        """Construct a fresh, uncancelled token for exactly one run.

        Each token is single-use: construct one here for each new run,
        thread it through every unit of that run, and never reuse or share
        it across runs — it is never a process-wide singleton.

        Args:
            clock: The injected time source used to timestamp hard-cancel
                hook bookkeeping. Never called for enforcement in this
                story — enforcing ``provider.hard_cancel_max_ms`` belongs to
                a later dispatcher story.
        """
        self._clock = clock
        self._lock = threading.Lock()
        self._hooks_lock = threading.Lock()
        self._event = threading.Event()  # set on ANY cancellation (soft or hard)
        self._hard_event = threading.Event()  # set on HARD cancellation only
        self._reason: CancelReason | None = None
        self._hard_cancel_started_monotonic_ms: int | None = None
        self._hard_hooks: list[_HardCancelHook] = []

    def cancel(self, *, reason: CancelReason, hard: bool = False) -> None:
        """Request cancellation at the given level, upgrading soft to hard only.

        Thread-safe from any thread. The level is monotonic: calling this with
        ``hard=False`` after a prior ``hard=True`` call leaves the level at
        ``HARD``. The first recorded reason wins, except that a HARD upgrade
        overrides a previously recorded soft reason (DD-42).

        Args:
            reason: The closed-enum reason driving this cancellation request.
            hard: Whether this is a hard (prompt-abort) cancellation, as
                opposed to a soft (work-preserving) one.
        """
        hooks: tuple[_HardCancelHook, ...] = ()
        with self._lock:
            upgraded = hard and not self._hard_event.is_set()
            if self._reason is None or upgraded:
                self._reason = reason
            self._event.set()
            if upgraded:
                self._hard_cancel_started_monotonic_ms = self._clock.monotonic_ms()
                self._hard_event.set()
        if upgraded:
            with self._hooks_lock:
                hooks = tuple(self._hard_hooks)
        for hook in hooks:
            _invoke_hook_quietly(hook)

    @property
    def is_cancelled(self) -> bool:
        """Whether cancellation has been requested at any level (SOFT or HARD)."""
        return self._event.is_set()

    @property
    def is_hard_cancelled(self) -> bool:
        """Whether cancellation has been requested at the HARD level."""
        return self._hard_event.is_set()

    def raise_if_cancelled(self) -> None:
        """Raise at a safe checkpoint if this token has been cancelled.

        Reads the flag and the reason under the same lock ``cancel()`` writes
        them under, so the pair is never observed torn.

        Raises:
            TaskCancelledError: This token has been cancelled (soft or hard);
                carries the recorded ``CancelReason``.
        """
        with self._lock:
            if not self._event.is_set():
                return
            reason = self._reason
        message = f"cancelled: {reason.value if reason is not None else 'unknown'}"
        raise TaskCancelledError(message=redact(message), context=None)

    def wait(self, timeout: float | None = None) -> bool:
        """Block up to ``timeout`` seconds, returning early once cancelled.

        Args:
            timeout: The maximum time to wait, in seconds, or ``None`` to
                wait indefinitely.

        Returns:
            ``True`` if the token was cancelled (at either level) before the
            timeout elapsed, ``False`` if the timeout elapsed first.
        """
        return self._event.wait(timeout)

    def snapshot(self) -> tuple[CancelLevel, CancelReason | None]:
        """Atomically read the ``(level, reason)`` pair under one lock (DD-42).

        The dispatcher's outcome derivation uses exactly one snapshot per
        halt; a torn read (a hard level paired with a stale soft reason) is
        impossible because both fields are written together under
        ``self._lock`` in ``cancel()``.

        Returns:
            ``(CancelLevel.NONE, None)`` if never cancelled; otherwise the
            current level paired with its recorded reason.
        """
        with self._lock:
            if self._hard_event.is_set():
                return (CancelLevel.HARD, self._reason)
            if self._event.is_set():
                return (CancelLevel.SOFT, self._reason)
            return (CancelLevel.NONE, None)

    def add_hard_cancel_hook(self, hook: _HardCancelHook) -> None:
        """Register an abort hook invoked exactly once on the first hard cancel.

        If the token is already hard-cancelled, ``hook`` is invoked
        immediately instead of being registered, so a call registering after
        the hard cancel already happened still runs its cleanup.

        Args:
            hook: A zero-argument, idempotent, non-raising-by-contract
                callable that aborts the caller's in-flight operation. Any
                exception it raises is caught and logged, never propagated.
        """
        if self.is_hard_cancelled:
            _invoke_hook_quietly(hook)
            return
        with self._hooks_lock:
            self._hard_hooks.append(hook)

    def remove_hard_cancel_hook(self, hook: _HardCancelHook) -> None:
        """Unregister a previously registered hard-cancel abort hook.

        Safe to call from any thread, typically from the protected
        ``finally`` block of the in-flight call the hook was guarding.
        Removing a hook that is not registered (already invoked, or never
        registered) is a silent no-op.

        Args:
            hook: The exact callable previously passed to
                ``add_hard_cancel_hook``.
        """
        with self._hooks_lock, contextlib.suppress(ValueError):
            self._hard_hooks.remove(hook)


def _invoke_hook_quietly(hook: _HardCancelHook) -> None:
    """Invoke a hard-cancel hook, catching and logging any exception it raises.

    Ensures one misbehaving hook never prevents the others from running and
    never prevents ``cancel()`` from returning to its caller.
    """
    try:
        hook()
    except Exception:
        _logger.exception("hard_cancel_hook_failed")
