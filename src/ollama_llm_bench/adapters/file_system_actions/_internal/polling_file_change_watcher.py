"""Polling ``FileChangeWatcher`` for the Task Editor's open task files
(``09_Task_Editor/state_machine.md`` §8, STORY-112).

Polling rather than ``QFileSystemWatcher``: Qt's native watcher silently loses its
watch when the watched path is *replaced by rename* -- which is exactly how both the
application's own YAML save and a version-control checkout replace a task file. One
shared ``QTimer`` that stats every watched path each tick is immune to that, needs no
per-operating-system branch, and is deterministic under test. The cost is up to one
poll interval of latency before a change is reported.

``QTimer.timeout`` is delivered on the thread owning the timer, and the timer is
created on the Qt GUI thread (enforced by ``api.make_file_change_watcher``'s
contract), so ``on_changed`` reaches the Task Editor controller on the GUI thread with
no marshalling step.
"""

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
from pathlib import Path

from PySide6.QtCore import QObject, QTimer

type _FileStamp = tuple[int, int]
"""``(st_mtime_ns, st_size)`` -- the cheap change hint read on every tick."""


def _stamp_of(path: str) -> _FileStamp | None:
    """Return ``path``'s modification-time/size stamp, or ``None`` when it cannot
    be stat'ed (missing, or unreadable)."""
    try:
        stat_result = Path(path).stat()
    except OSError:
        return None
    return (stat_result.st_mtime_ns, stat_result.st_size)


def _digest_of(path: str) -> str | None:
    """Return the SHA-256 digest of ``path``'s current bytes, or ``None`` when it
    cannot be read."""
    try:
        content = Path(path).read_bytes()
    except OSError:
        return None
    return hashlib.sha256(content).hexdigest()


@dataclass(eq=False)
class _WatchEntry:
    """One registered watch: its callback plus the last content it was told about.

    A private ``@dataclass`` is permitted here because this type never leaves
    ``_internal/`` (``16_Engineering_Standards/03_CODING_STANDARDS.md``'s single
    ``@dataclass`` exception). ``eq=False`` keeps identity comparison, so two
    watches on the same path with the same callback stay distinguishable in the
    entry list.
    """

    path: str
    on_changed: Callable[[str], None]
    stamp: _FileStamp | None
    digest: str | None


class _PollingWatchSubscription:
    """Handle to one registered watch; ``cancel()`` is idempotent (STORY-112-AC-3)."""

    def __init__(self, *, on_cancel: Callable[[], None]) -> None:
        self._on_cancel = on_cancel
        self._is_cancelled = False

    def cancel(self) -> None:
        """Deregister this watch. A second call is a no-op, never an error."""
        if self._is_cancelled:
            return
        self._is_cancelled = True
        self._on_cancel()


class PollingFileChangeWatcher(QObject):
    """Reports an open task file whose on-disk *content* changed.

    Compares a content digest, never the modification time alone: the
    specification requires a save that rewrites a file with byte-identical
    content to raise no alarm at all (§8 -- "a touch that does not change content
    is ignored"). The modification-time/size stamp is only a cheap hint deciding
    whether re-reading the file this tick is worth it.
    """

    def __init__(self, *, poll_interval_ms: int) -> None:
        """Start the shared poll timer.

        Args:
            poll_interval_ms: How often every watched path is stat'ed. Trades
                notification latency against idle cost; tests drive it fast.
        """
        super().__init__()
        self._entries: list[_WatchEntry] = []
        self._timer = QTimer(self)
        self._timer.setInterval(poll_interval_ms)
        self._timer.timeout.connect(self._poll)

    def watch(self, path: str, on_changed: Callable[[str], None]) -> _PollingWatchSubscription:
        """Start watching ``path``, baselining against its content right now.

        A second ``watch()`` on an already-watched path registers an independent
        entry -- the Task Editor's re-baseline-after-save path cancels and
        re-watches, so entries are keyed by subscription identity, not by path.

        Args:
            path: The absolute path of the file to watch.
            on_changed: Called with ``path`` when its on-disk content differs
                from what this watcher last read.

        Returns:
            A subscription handle whose ``cancel()`` deregisters the watch.
        """
        entry = _WatchEntry(
            path=path, on_changed=on_changed, stamp=_stamp_of(path), digest=_digest_of(path)
        )
        self._entries.append(entry)
        if not self._timer.isActive():
            self._timer.start()
        return _PollingWatchSubscription(on_cancel=lambda: self._deregister(entry))

    def _deregister(self, entry: _WatchEntry) -> None:
        """Drop ``entry``, stopping the shared timer once nothing is watched."""
        if entry in self._entries:
            self._entries.remove(entry)
        if not self._entries:
            self._timer.stop()

    def _poll(self) -> None:
        """Check every watched path once. Iterates a copy so an ``on_changed``
        callback may cancel its own (or another) watch re-entrantly."""
        for entry in list(self._entries):
            self._poll_entry(entry)

    def _poll_entry(self, entry: _WatchEntry) -> None:
        """Report ``entry``'s path only when its content digest actually moved.

        A path that is missing or unreadable this tick is skipped entirely and
        never reported as a change -- the Task Editor treats absence through its
        own state machine, not through this adapter.
        """
        stamp = _stamp_of(entry.path)
        if stamp is None or stamp == entry.stamp:
            return
        digest = _digest_of(entry.path)
        if digest is None:
            return
        entry.stamp = stamp
        if digest == entry.digest:
            return
        # Store the new digest *before* calling back, so a slow or re-entrant
        # handler cannot cause the same change to be reported twice.
        entry.digest = digest
        entry.on_changed(entry.path)
