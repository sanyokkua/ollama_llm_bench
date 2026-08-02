"""Process entry point: ``python -m ollama_llm_bench`` (STORY-076).

Parses the launch arguments, detects the host platform, configures the ``app.*``
logging stream, constructs the single ``QApplication``, installs the two top-level
crash-policy exception hooks, then hands off to the composition root
(:func:`ollama_llm_bench.compose.build_app`) and enters the one Qt event loop.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-M_app_lifecycle.md``
§2 (launch order of operations) and §8 (crash policy); ADR-0010 (the composition-root
and entry-point sequencing this file implements).

This file is exempt from the module public-surface (``api.py``/``models.py``/
``protocols.py``) convention and from the ``api.py`` icontract requirement — it is
the process entry point, not a feature module (``project-structure.md``).
"""

import argparse
from collections.abc import Sequence
import logging
from pathlib import Path
import sys
import threading
import traceback
from types import TracebackType
from typing import Final

import icontract.errors
import msgspec
from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication
import structlog

from ollama_llm_bench.adapters.clipboard import Clipboard, make_clipboard
from ollama_llm_bench.adapters.qt_event_bus import make_qt_event_bus_deliverer
from ollama_llm_bench.backend.errors import ProgrammerError
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.infra import app_log_path, configure_logging
from ollama_llm_bench.backend.platform import make_platform_detector
from ollama_llm_bench.compose import AppHandle, build_app
from ollama_llm_bench.ui.common_dialogs import (
    ErrorDialogPattern,
    ErrorDialogPayload,
    make_error_dialog,
)

__all__: list[str] = ["main"]

_LOG = structlog.get_logger("app.main")

# The launch arguments' friendly `--log-level` values, mapped onto the standard-library
# levels `configure_logging` accepts (backend/infra/api.py's precondition allows only
# DEBUG/INFO/WARNING/ERROR/CRITICAL). No `trace` choice: `08-M` §2 step 1 fixes only that
# a level override exists, not its value set, and this codebase has no custom TRACE level
# installed yet (that belongs to the Settings `logging.app_log_level` story, not this one).
_FRIENDLY_LOG_LEVELS: Final[dict[str, int]] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}

_FATAL_DIALOG_TITLE: Final[str] = "Unexpected Error"
_FATAL_DIALOG_MESSAGE: Final[str] = "An unexpected error occurred and the application must close."

# The set of exception types the crash policy treats as CRITICAL: `ProgrammerError`
# (this codebase's own must-crash root) and icontract's `ViolationError` (raised when
# an `@icontract.require`/`@icontract.ensure` contract on an `api.py` function is
# violated). `ViolationError` subclasses `AssertionError`, not `ProgrammerError` -- it
# is a distinct exception hierarchy the crash policy still groups as "never caught,
# crashes the process" (`16_Engineering_Standards/06_LOGGING_STANDARD.md`).
_CRITICAL_EXCEPTION_TYPES: Final[tuple[type[BaseException], ...]] = (
    ProgrammerError,
    icontract.errors.ViolationError,
)


class _FatalDialogGuard:
    """A mutable re-entrancy guard for the fatal crash dialog.

    ``_handle_ui_thread_exception`` runs a nested Qt event loop via the fatal
    dialog's ``.exec()``. If a second uncaught user-interface-thread exception is
    delivered while that loop is still running, this guard is what stops the hook
    from constructing and showing a second stacked ``FATAL`` modal
    (``07_Common_Dialogs/error_dialog.md`` EC-ERR-3: two Error dialogs are never
    visible at once) -- the second exception is still logged, just not dialoged.
    """

    def __init__(self) -> None:
        self._showing = False

    @property
    def is_showing(self) -> bool:
        """Whether a fatal dialog is currently being shown (its ``.exec()`` is active)."""
        return self._showing

    def begin(self) -> None:
        """Mark a fatal dialog as about to be shown, before calling ``.exec()``."""
        self._showing = True

    def end(self) -> None:
        """Clear the guard once the fatal dialog's ``.exec()`` has returned."""
        self._showing = False


class _CrashDialogCollaborators(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The UI-thread exception hook's dependency bundle (coding-style.md's
    4-parameter rule -- keeps ``_handle_ui_thread_exception`` at 4 parameters
    alongside the three positional exception-info arguments it must accept to
    match ``sys.excepthook``'s call shape)."""

    clipboard: Clipboard
    event_bus: EventBus
    handle_holder: "_AppHandleHolder"
    dialog_guard: _FatalDialogGuard = msgspec.field(default_factory=_FatalDialogGuard)


class _AppHandleHolder:
    """A mutable single-slot holder for the composition root's ``AppHandle``.

    ``main()`` constructs this before the exception hooks are installed and before
    ``build_app`` runs, and fills it once ``build_app`` returns. The UI-thread
    exception hook reads it through this holder — never a module-level global
    (banned by ``coding-style.md``) — so a crash during composition, before an
    ``AppHandle`` exists, can still be told there is nothing to shut down yet.
    """

    def __init__(self) -> None:
        self._handle: AppHandle | None = None

    @property
    def handle(self) -> AppHandle | None:
        """The composed ``AppHandle``, or ``None`` before ``build_app`` has returned."""
        return self._handle

    def set_handle(self, handle: AppHandle) -> None:
        """Store the ``AppHandle`` once ``build_app`` returns successfully.

        Args:
            handle: The composition root's returned handle.
        """
        self._handle = handle


def _parse_launch_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the two supported launch arguments (``08-M_app_lifecycle.md`` §2 step 1).

    An invalid argument makes ``argparse`` print a usage message to the standard
    error stream and raise ``SystemExit(2)`` — satisfying the lifecycle contract's
    "invalid arguments abort launch with a message on the standard error stream"
    without this module adding its own error path.

    Args:
        argv: The argument vector to parse (excluding the program name), or
            ``None`` to parse ``sys.argv[1:]`` — the normal
            ``python -m ollama_llm_bench`` / console-script invocation.

    Returns:
        The parsed namespace, carrying ``log_level`` (the resolved standard-library
        logging level, defaulting to ``logging.INFO``) and ``dataset_path`` (the
        optional dataset-directory override, or ``None`` when not supplied).
    """
    parser = argparse.ArgumentParser(prog="ollama-llm-bench")
    parser.add_argument(
        "--log-level",
        choices=sorted(_FRIENDLY_LOG_LEVELS),
        default="info",
        help="Override the application log's minimum level for this launch.",
    )
    parser.add_argument(
        "--dataset-path",
        type=Path,
        default=None,
        help=(
            "Override the default task-file dataset directory for this launch "
            "(parsed only; not yet applied -- reserved for a future story)."
        ),
    )
    args = parser.parse_args(argv)
    args.log_level = _FRIENDLY_LOG_LEVELS[args.log_level]
    return args


def _handle_ui_thread_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
    *,
    collaborators: _CrashDialogCollaborators,
) -> None:
    """Log, show the fatal Error dialog, close the database, and exit (EC-M-8).

    Standalone and independently callable — not reachable only through a real
    uncaught exception — so it can be exercised directly by a test. Never raises:
    a failure inside this hook must not leave the crash unhandled.

    Re-entrancy: if a second uncaught user-interface-thread exception is delivered
    while this hook's fatal dialog is already showing (its ``.exec()`` runs a nested
    Qt event loop, so this hook can be re-entered before the first call returns),
    the second exception is logged the same way but no second stacked ``FATAL``
    modal is constructed (``07_Common_Dialogs/error_dialog.md`` EC-ERR-3).

    Args:
        exc_type: The uncaught exception's type.
        exc_value: The uncaught exception instance.
        exc_traceback: The uncaught exception's traceback, if any.
        collaborators: The clipboard, event bus, ``AppHandle`` holder, and fatal-
            dialog re-entrancy guard this hook depends on (coding-style.md's
            4-parameter rule).
    """
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    event_name = "uncaught_ui_thread_exception"
    if isinstance(exc_value, _CRITICAL_EXCEPTION_TYPES):
        _LOG.critical(event_name, exc_type=exc_type.__name__, traceback=tb_text)
    else:
        _LOG.error(event_name, exc_type=exc_type.__name__, traceback=tb_text)

    if collaborators.dialog_guard.is_showing:
        return

    def _quit() -> None:
        handle = collaborators.handle_holder.handle
        if handle is not None:
            handle.shutdown()
        instance = QApplication.instance()
        if instance is not None:
            instance.exit(1)

    payload = ErrorDialogPayload(
        title=_FATAL_DIALOG_TITLE,
        message=_FATAL_DIALOG_MESSAGE,
        detail=f"{exc_type.__name__}: {exc_value}\n\n{tb_text}",
        pattern=ErrorDialogPattern.FATAL,
        quit_callback=_quit,
    )
    dialog = make_error_dialog(
        payload=payload, clipboard=collaborators.clipboard, event_bus=collaborators.event_bus
    )
    collaborators.dialog_guard.begin()
    try:
        dialog.exec()
    finally:
        collaborators.dialog_guard.end()


def _handle_worker_thread_exception(args: threading.ExceptHookArgs) -> None:
    """Log an uncaught worker-thread exception; the application stays running.

    Standalone and independently callable for direct testing. Shows no dialog,
    performs no database operation, and never raises — one failed background
    worker must not take down the whole session (``08-M_app_lifecycle.md`` §8).

    A ``SystemExit`` is not logged: it is how a thread is expected to be able to
    end itself cleanly, and the standard library's own default
    ``threading.excepthook`` silently ignores it for the same reason (see
    ``Lib/threading.py``'s module-level ``excepthook``).

    Args:
        args: The failing thread's exception info, as ``threading.excepthook``
            supplies it.
    """
    if args.exc_type is SystemExit:
        return

    tb_text = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    thread_name = args.thread.name if args.thread is not None else "unknown"
    event_name = "uncaught_worker_thread_exception"
    if isinstance(args.exc_value, _CRITICAL_EXCEPTION_TYPES):
        _LOG.critical(
            event_name, thread_name=thread_name, exc_type=args.exc_type.__name__, traceback=tb_text
        )
    else:
        _LOG.error(
            event_name, thread_name=thread_name, exc_type=args.exc_type.__name__, traceback=tb_text
        )


def _install_exception_hooks(
    *, clipboard: Clipboard, event_bus: EventBus, handle_holder: _AppHandleHolder
) -> None:
    """Install the crash-policy hooks for both execution threads (ADR-0010, EC-M-8).

    Installed before ``build_app`` runs, so a composition-time crash on the GUI
    thread is caught the same way a later runtime crash would be
    (``08-M_app_lifecycle.md`` §8).

    Args:
        clipboard: Backs the UI-thread hook's error dialog Copy Details button.
        event_bus: Backs the UI-thread hook's error dialog Copy Details toast.
        handle_holder: The single-slot holder the UI-thread hook reads to decide
            whether an ``AppHandle`` exists yet to shut down.
    """

    collaborators = _CrashDialogCollaborators(
        clipboard=clipboard, event_bus=event_bus, handle_holder=handle_holder
    )

    def _ui_thread_hook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        _handle_ui_thread_exception(exc_type, exc_value, exc_traceback, collaborators=collaborators)

    sys.excepthook = _ui_thread_hook
    threading.excepthook = _handle_worker_thread_exception


def main(argv: Sequence[str] | None = None) -> None:
    """Launch the application: parse arguments, compose the object graph, run Qt.

    Implements ``08-M_app_lifecycle.md`` §2 steps 1-2 directly (argument parsing,
    platform detection), configures logging (step 3) before any worker or dialog
    can exist, then defers the remaining ordered launch steps to
    :func:`ollama_llm_bench.compose.build_app` per ADR-0010.

    Args:
        argv: The argument vector to parse (excluding the program name), or
            ``None`` to parse ``sys.argv[1:]`` — the normal
            ``python -m ollama_llm_bench`` / console-script invocation.
    """
    args = _parse_launch_arguments(argv)
    profile = make_platform_detector().detect()
    configure_logging(app_log_file=app_log_path(profile), level=args.log_level)

    app = QApplication(sys.argv[:1])
    clipboard = make_clipboard()
    event_bus = make_qt_event_bus_deliverer()
    handle_holder = _AppHandleHolder()
    _install_exception_hooks(clipboard=clipboard, event_bus=event_bus, handle_holder=handle_holder)

    handle = build_app(app=app, loop=QEventLoop())
    handle_holder.set_handle(handle)
    handle.window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
