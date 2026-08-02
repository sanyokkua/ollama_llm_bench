"""Integration test for `__main__`'s worker-thread top-level exception hook (STORY-076).

Installs the real hooks via `_install_exception_hooks` and lets a genuine
`threading.Thread` target raise uncaught -- the standard library's own
`threading.excepthook` dispatch calls the installed hook, so this proves the whole
wiring, not just `_handle_worker_thread_exception` called in isolation.

Source of truth: `docs/v3_specification/08_Cross_Cutting/08-M_app_lifecycle.md` §8
(crash policy).
"""

from collections.abc import Iterator
import json
from pathlib import Path
import sys
import threading
import time

from PySide6.QtWidgets import QApplication
import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.__main__ import _AppHandleHolder, _install_exception_hooks
from ollama_llm_bench.adapters.clipboard import Clipboard
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.infra import configure_logging

_QUEUE_DRAIN_WAIT_S = 0.5
_WORKER_THREAD_NAME = "benchmark-worker"


@pytest.fixture(autouse=True)
def _restore_global_exception_hooks() -> Iterator[None]:
    """`_install_exception_hooks` mutates the process-global `sys.excepthook` and
    `threading.excepthook`; restore both after the test so this test's closures
    (holding test-local mocks) never linger for a later, unrelated test."""
    original_sys_hook = sys.excepthook
    original_threading_hook = threading.excepthook
    yield
    sys.excepthook = original_sys_hook
    threading.excepthook = original_threading_hook


def _read_app_log_lines(app_log_file: Path) -> list[dict[str, object]]:
    """Read and JSON-decode every record currently written to `app.log`."""
    if not app_log_file.exists():
        return []
    lines = [line for line in app_log_file.read_text(encoding="utf-8").splitlines() if line]
    return [json.loads(line) for line in lines]


def test_worker_thread_uncaught_exception_is_logged_and_app_stays_alive(
    tmp_path: Path, qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-076-AC-2

    Given a benchmark is executing on a background worker thread, when an uncaught
    exception reaches that thread, then the top-level worker hook logs it to
    `app.log` and the application stays running with a usable user interface -- no
    dialog, no `QApplication.exit`, no `sys.exit`, and the `QApplication` instance
    survives untouched.
    """
    # Arrange
    app_log_file = tmp_path / "logs" / "app" / "app.log"
    configure_logging(app_log_file=app_log_file)
    clipboard = mocker.Mock(spec=Clipboard)
    event_bus = mocker.Mock(spec=EventBus)
    handle_holder = _AppHandleHolder()
    _install_exception_hooks(clipboard=clipboard, event_bus=event_bus, handle_holder=handle_holder)
    qapp_exit_spy = mocker.patch.object(QApplication, "exit")
    sys_exit_spy = mocker.patch("ollama_llm_bench.__main__.sys.exit")

    def _raise_in_worker() -> None:
        raise ValueError("synthetic worker-thread boom")

    # Act
    worker = threading.Thread(target=_raise_in_worker, name=_WORKER_THREAD_NAME)
    worker.start()
    worker.join()
    time.sleep(_QUEUE_DRAIN_WAIT_S)
    app_records = _read_app_log_lines(app_log_file)

    # Assert -- an app.log record exists for the worker-thread exception.
    matching = [r for r in app_records if r.get("event") == "uncaught_worker_thread_exception"]
    assert len(matching) == 1
    assert matching[0]["level"] == "error"
    assert matching[0]["thread_name"] == _WORKER_THREAD_NAME
    assert matching[0]["exc_type"] == "ValueError"

    # Assert -- the application never exited and the QApplication instance survives.
    qapp_exit_spy.assert_not_called()
    sys_exit_spy.assert_not_called()
    assert QApplication.instance() is qapp


def test_worker_thread_system_exit_is_not_logged(
    tmp_path: Path, qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-076-AC-2

    Given a worker thread raises `SystemExit` -- the standard way a thread ends
    itself cleanly -- when the top-level worker hook receives it, then no `app.log`
    record is written for it, mirroring the standard library's own default
    `threading.excepthook`, which silently ignores `SystemExit` for the same reason.
    """
    # Arrange
    app_log_file = tmp_path / "logs" / "app" / "app.log"
    configure_logging(app_log_file=app_log_file)
    clipboard = mocker.Mock(spec=Clipboard)
    event_bus = mocker.Mock(spec=EventBus)
    handle_holder = _AppHandleHolder()
    _install_exception_hooks(clipboard=clipboard, event_bus=event_bus, handle_holder=handle_holder)

    def _exit_in_worker() -> None:
        raise SystemExit(0)

    # Act
    worker = threading.Thread(target=_exit_in_worker, name="worker-system-exit")
    worker.start()
    worker.join()
    time.sleep(_QUEUE_DRAIN_WAIT_S)

    # Assert -- no app.log record was written for the worker thread's SystemExit.
    app_records = _read_app_log_lines(app_log_file)
    matching = [r for r in app_records if r.get("event") == "uncaught_worker_thread_exception"]
    assert len(matching) == 0
