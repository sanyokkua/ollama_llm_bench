"""``CloseHandler`` -- the quit-confirmation sequence (STORY-053).

Source of truth: ``docs/v3_specification/01_Main_Window/description.md`` §8 and
``08_Cross_Cutting/08-M_app_lifecycle.md`` §7. Runs up to two confirmations in sequence --
the running-benchmark prompt, then the unsaved-buffer prompt -- and delegates to
``on_confirmed_quit`` once both resolve toward quitting.

**The bounded shutdown wait is non-blocking by construction.** No ``time.sleep`` and no
blocking ``Future.result()`` anywhere in this file. The wait for ``_run_stopped`` is
expressed as "first callback wins" between a ``QTimer.timeout`` signal and an
``EventBus``-delivered handler -- both run as ordinary queued callbacks on the GUI thread's
own event loop, so the loop keeps pumping and the event can actually arrive. This is the
GUI-thread analogue of the dispatcher-thread "never complete via a queued Qt signal" rule
(``concurrency-standard.md``) -- here the risk runs the other way: a *synchronous* blocking
wait on this thread would freeze the one thread that must stay alive to receive the event at
all.

**Modal ``exec()`` is the sanctioned exception.** ``QMessageBox.exec()`` blocks the calling
call frame, but it runs its own nested Qt event loop while doing so -- the standard Qt idiom
for a synchronous user decision. This is not the same hazard as the bounded-wait design
above avoids; do not conflate the two.
"""

from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox
import structlog

from ollama_llm_bench.adapters.notification_service import NotificationService
from ollama_llm_bench.backend.events import SIGNAL_RUN_STOPPED, EventBus, Subscription
from ollama_llm_bench.ui.main_window.protocols import MainWindowGateway

__all__: list[str] = ["CloseHandler"]

logger = structlog.get_logger(__name__)

_DEFAULT_SHUTDOWN_TIMEOUT_MS = 5000
_RUNNING_QUIT_TITLE = "Quit"
_RUNNING_QUIT_TEXT = "Stop the benchmark and quit?"
_UNSAVED_BUFFERS_TITLE = "Unsaved changes"


class CloseHandler:
    """Runs the running-benchmark and unsaved-buffer quit confirmations in sequence."""

    def __init__(  # noqa: PLR0913  # six distinct required collaborators per the approved
        # STORY-053 design (docs/stories/story-053-main-window-shell.md); each is an
        # independently-faked test seam, not groupable into one struct without losing that
        self,
        *,
        gateway: MainWindowGateway,
        event_bus: EventBus,
        notifications: NotificationService,
        dirty_buffer_count: Callable[[], int] = lambda: 0,
        on_confirmed_quit: Callable[[], None],
        shutdown_timeout_ms: int = _DEFAULT_SHUTDOWN_TIMEOUT_MS,
    ) -> None:
        """Store the collaborators the quit sequence coordinates.

        Args:
            gateway: Supplies ``is_run_active()`` (the quit decision) and
                ``shutdown(timeout_ms)`` (the graceful pipeline stop).
            event_bus: The bus the bounded shutdown wait subscribes
                ``_run_stopped`` on.
            notifications: Retained for parity with the controller's collaborator set;
                this handler itself raises no notification.
            dirty_buffer_count: Returns the Task Editor's current dirty-buffer count.
                Defaults to always-zero because the Task Editor does not exist yet
                (STORY-068 wires the real hook) -- additive, not a signature change a
                caller must adapt to.
            on_confirmed_quit: Invoked once every confirmation has resolved toward
                quitting.
            shutdown_timeout_ms: The bound on the wait for ``_run_stopped`` after a
                confirmed running-benchmark quit.
        """
        self._gateway = gateway
        self._event_bus = event_bus
        self._notifications = notifications
        self._dirty_buffer_count = dirty_buffer_count
        self._on_confirmed_quit = on_confirmed_quit
        self._shutdown_timeout_ms = shutdown_timeout_ms
        self._quit_settled = False
        self._subscription: Subscription | None = None
        self._timer: QTimer | None = None

    def request_close(self) -> None:
        """Run the quit sequence for one close (X) request (§8, EC-RUN-4, EC-WS-2)."""
        if self._gateway.is_run_active():
            logger.debug("quit_requested_with_active_run")
            if not self._confirm_running_benchmark_quit():
                logger.debug("quit_cancelled_at_running_benchmark_prompt")
                return
            self._begin_bounded_shutdown_wait()
            return
        logger.debug("quit_requested_no_active_run")
        self._proceed_to_buffer_check()

    def _begin_bounded_shutdown_wait(self) -> None:
        self._quit_settled = False
        self._gateway.shutdown(self._shutdown_timeout_ms)
        self._subscription = self._event_bus.subscribe(
            SIGNAL_RUN_STOPPED, self._on_stopped, owner=self
        )
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self._on_timeout)
        timer.start(self._shutdown_timeout_ms)
        self._timer = timer

    def _on_stopped(self, _event: object) -> None:
        logger.debug("shutdown_wait_settled_by_run_stopped")
        self._settle()

    def _on_timeout(self) -> None:
        logger.debug("shutdown_wait_settled_by_timeout")
        self._settle()

    def _settle(self) -> None:
        if self._quit_settled:
            return
        self._quit_settled = True
        if self._subscription is not None:
            self._subscription.cancel()
        if self._timer is not None:
            self._timer.stop()
        self._proceed_to_buffer_check()

    def _proceed_to_buffer_check(self) -> None:
        if self._dirty_buffer_count() > 0:
            logger.debug("quit_requested_with_dirty_buffers")
            outcome = self._confirm_unsaved_buffers()
            if outcome == "cancel":
                logger.debug("quit_cancelled_at_unsaved_buffers_prompt")
                return
        logger.debug("quit_confirmed")
        self._on_confirmed_quit()

    @staticmethod
    def _confirm_running_benchmark_quit() -> bool:
        box = QMessageBox()
        box.setWindowTitle(_RUNNING_QUIT_TITLE)
        box.setText(_RUNNING_QUIT_TEXT)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        confirm_button = box.addButton("Confirm", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(confirm_button)
        box.exec()
        return box.clickedButton() is confirm_button

    def _confirm_unsaved_buffers(self) -> str:
        box = QMessageBox()
        box.setWindowTitle(_UNSAVED_BUFFERS_TITLE)
        box.setText(f"Save changes to {self._dirty_buffer_count()} file(s)?")
        discard_button = box.addButton("Discard All", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        save_button = box.addButton("Save All", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(save_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save_button:
            return "save_all"
        if clicked is discard_button:
            return "discard_all"
        return "cancel"
