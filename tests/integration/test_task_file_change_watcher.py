"""Integration tests for the on-disk task-file change watcher (STORY-112).

Crosses a real filesystem boundary and a real Qt timer, so these live here rather
than in a colocated module test: each case writes real files under ``tmp_path`` and
waits on real poll ticks. The watcher is constructed with a deliberately short poll
interval so the suite stays well inside the integration tier's 30-second budget.
"""

import os
from pathlib import Path

from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.file_system_actions import make_file_change_watcher

_POLL_INTERVAL_MS = 25
_WAIT_TIMEOUT_MS = 3000
# Long enough to span several further poll ticks, so a spurious extra notification
# would have had ample opportunity to arrive.
_QUIET_PERIOD_MS = 300
_ONE_SECOND_NS = 1_000_000_000

_ORIGINAL_YAML = "tasks:\n  - task_id: t1\n    question: Q?\n"
_DIFFERENT_YAML = "tasks:\n  - task_id: t1\n    question: Q?\n  - task_id: t2\n    question: Q2?\n"


def _touch_without_changing_content(path: Path) -> None:
    """Rewrite ``path`` with its own current bytes and force its modification time
    forward, so only the content digest can distinguish this from a real edit."""
    content = path.read_bytes()
    path.write_bytes(content)
    moved_ns = path.stat().st_mtime_ns + _ONE_SECOND_NS
    os.utime(path, ns=(moved_ns, moved_ns))


def test_changed_content_notifies_the_watcher_once(qtbot: QtBot, tmp_path: Path) -> None:
    """Proves: STORY-112-AC-1

    Given a task file being watched, when its content on disk is replaced with
    different content, then the change callback is invoked exactly once with
    that file's path -- and stays at exactly one call across several further
    poll ticks.
    """
    # Arrange
    watched_path = tmp_path / "watched.yaml"
    watched_path.write_text(_ORIGINAL_YAML, encoding="utf-8")
    notified_paths: list[str] = []
    watcher = make_file_change_watcher(poll_interval_ms=_POLL_INTERVAL_MS)
    watcher.watch(str(watched_path), notified_paths.append)

    # Act
    watched_path.write_text(_DIFFERENT_YAML, encoding="utf-8")
    qtbot.waitUntil(lambda: len(notified_paths) >= 1, timeout=_WAIT_TIMEOUT_MS)
    qtbot.wait(_QUIET_PERIOD_MS)

    # Assert
    assert notified_paths == [str(watched_path)]


def test_content_preserving_rewrite_does_not_notify(qtbot: QtBot, tmp_path: Path) -> None:
    """Proves: STORY-112-AC-2

    Given a task file being watched, when it is rewritten with byte-identical
    content and its modification time moves forward, then the change callback is
    never invoked -- the watcher compares content, not timestamps.
    """
    # Arrange
    watched_path = tmp_path / "touched.yaml"
    watched_path.write_text(_ORIGINAL_YAML, encoding="utf-8")
    stamp_before_ns = watched_path.stat().st_mtime_ns
    notified_paths: list[str] = []
    watcher = make_file_change_watcher(poll_interval_ms=_POLL_INTERVAL_MS)
    watcher.watch(str(watched_path), notified_paths.append)

    # Act
    _touch_without_changing_content(watched_path)
    qtbot.wait(_QUIET_PERIOD_MS)

    # Assert -- the modification-time check guards the arrangement: without it
    # this could pass because nothing looked changed, never exercising the
    # content comparison that the specification actually requires.
    assert watched_path.stat().st_mtime_ns != stamp_before_ns
    assert notified_paths == []


def test_an_absent_watched_path_is_never_reported_as_a_change(qtbot: QtBot, tmp_path: Path) -> None:
    """A watched path that is missing or unreadable is skipped on every tick and
    never raises out of the watcher — the Task Editor treats a vanished file
    through its own state machine, not through an exception from this adapter
    (STORY-112 design constraints).
    """
    # Arrange
    deleted_path = tmp_path / "deleted.yaml"
    deleted_path.write_text(_ORIGINAL_YAML, encoding="utf-8")
    notified_paths: list[str] = []
    watcher = make_file_change_watcher(poll_interval_ms=_POLL_INTERVAL_MS)
    watcher.watch(str(deleted_path), notified_paths.append)
    watcher.watch(str(tmp_path / "never_created.yaml"), notified_paths.append)

    # Act
    deleted_path.unlink()
    qtbot.wait(_QUIET_PERIOD_MS)

    # Assert
    assert notified_paths == []


def test_cancel_is_idempotent_and_stops_notifications(qtbot: QtBot, tmp_path: Path) -> None:
    """Proves: STORY-112-AC-3

    Given a watch whose subscription has already been cancelled once, when
    ``cancel()`` is called a second time and the file's content is then changed
    on disk, then the second call raises nothing and the change callback is
    never invoked.
    """
    # Arrange -- a second, untouched watch keeps the shared poll timer running,
    # so the cancelled watch is proven absent from the poll set rather than
    # merely un-polled.
    cancelled_path = tmp_path / "cancelled.yaml"
    cancelled_path.write_text(_ORIGINAL_YAML, encoding="utf-8")
    still_watched_path = tmp_path / "still_watched.yaml"
    still_watched_path.write_text(_ORIGINAL_YAML, encoding="utf-8")
    notified_paths: list[str] = []
    watcher = make_file_change_watcher(poll_interval_ms=_POLL_INTERVAL_MS)
    watcher.watch(str(still_watched_path), notified_paths.append)
    subscription = watcher.watch(str(cancelled_path), notified_paths.append)
    subscription.cancel()

    # Act
    subscription.cancel()
    cancelled_path.write_text(_DIFFERENT_YAML, encoding="utf-8")
    qtbot.wait(_QUIET_PERIOD_MS)

    # Assert
    assert notified_paths == []
