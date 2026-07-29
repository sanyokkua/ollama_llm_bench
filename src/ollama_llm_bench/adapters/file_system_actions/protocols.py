"""``FileSystemActions`` Protocol (08-E §21c), plus the ``FileChangeWatcher``/
``FileWatchSubscription`` pair backing the Task Editor's on-disk change watch
(``09_Task_Editor/state_machine.md`` §8).

``FileChangeWatcher`` and ``FileWatchSubscription`` are **deliberate duplicates** of the
declarations in ``ui/task_editor/protocols.py``, which stays their source of truth for the
shape: the Task Editor owns them, but ``adapters/*`` may not import ``ui/*``
(``import-linter``), so ``api.py`` cannot annotate ``make_file_change_watcher``'s return type
with the UI module's copy. The concrete ``PollingFileChangeWatcher`` satisfies both
structurally, with no import in either direction -- the same seam ADR-0014 chose for the
seven UI gateways. Any change to the UI declaration must be mirrored here.
"""

from collections.abc import Callable
from typing import Protocol

__all__: list[str] = ["FileChangeWatcher", "FileSystemActions", "FileWatchSubscription"]


class FileSystemActions(Protocol):
    """File-manager integration."""

    def open_in_file_manager(self, path: str) -> None:
        """Reveal a file or folder in the OS file manager.

        fast-synchronous; must be called on the Qt main thread. When ``path``
        names a file, the file manager opens with that file selected where the
        platform supports selection (08-K §5); when it names a folder, the
        folder itself is opened.

        Args:
            path: The absolute filesystem path to reveal.

        Raises:
            OsAdapterError: ``path`` does not exist, or the file manager could
                not be launched.
        """
        ...

    def open_url(self, url: str) -> None:
        """Open ``url`` in the user's default browser.

        fast-synchronous; must be called on the Qt main thread. Backs the
        About dialog's ``Project on GitHub`` link (07_Common_Dialogs/
        about_dialog.md §6, EC-AB-7).

        Args:
            url: The absolute URL to open.

        Raises:
            OsAdapterError: The default browser could not be launched.
        """
        ...

    def run_log_exists(self, *, run_id: int, started_at: str) -> bool:
        """Return whether this run's log file currently exists on disk.

        fast-synchronous; must be called on the Qt main thread. Derives the
        log path the same way ``backend.log_file_writer.make_run_log_writer``
        will (``run_log_path(platform_detector, run_id=..., unix_ts=...)``),
        using ``unix_ts = int(datetime.fromisoformat(started_at).timestamp())``.
        This is the run-log naming convention this story (STORY-056)
        establishes; any later story wiring ``benchmark_pipeline`` to
        ``log_file_writer`` must derive ``unix_ts`` from the run's
        ``started_at`` the same way, or this check silently always returns
        ``False``.

        Args:
            run_id: The run's numeric id.
            started_at: The run's ``BenchmarkRun.started_at`` ISO-8601 UTC string.

        Returns:
            True if the run's log file exists at the derived path.
        """
        ...

    def run_log_path_str(self, *, run_id: int, started_at: str) -> str:
        """Return this run's log-file path (whether or not it exists), as a string.

        fast-synchronous; must be called on the Qt main thread. Shares the
        exact same derivation as ``run_log_exists`` so both methods agree on
        one single derivation site.

        Args:
            run_id: The run's numeric id.
            started_at: The run's ``BenchmarkRun.started_at`` ISO-8601 UTC string.

        Returns:
            The derived absolute log-file path, as a string.
        """
        ...

    def write_export_file(self, *, filename: str, content: str) -> str:
        """Write ``content`` atomically into the exports folder
        ``<app-data>/exports/`` (STORY-061 extension; 10_Domain_and_Data/
        05_EXPORT_FORMATS.md §11).

        fast-synchronous; must be called on the Qt main thread. Creates the
        exports folder on first use. Applies the numeric-suffix collision
        rule (§2.2) when ``filename`` already exists in the folder. Writes to
        a temporary file in the same folder and atomically renames it into
        place, so a failed write never leaves a partial file (EC-RES-5).

        Args:
            filename: The canonical export filename, already composed by the
                ``ExportFilenameHelper``.
            content: The full UTF-8 file content to write.

        Returns:
            The absolute path of the file actually written, after the
            collision-suffix rule is applied.

        Raises:
            OsAdapterError: The exports folder could not be created, or the
                write failed (permission denied, disk full).
        """
        ...

    def exports_folder_path(self) -> str:
        """Return the absolute exports-folder path ``<app-data>/exports/``
        (STORY-061 extension), creating it if it does not yet exist.

        fast-synchronous; must be called on the Qt main thread.

        Returns:
            The absolute exports-folder path, guaranteed to exist on return.

        Raises:
            OsAdapterError: The folder could not be created.
        """
        ...

    def write_text_file(self, *, path: str, content: str) -> None:
        """Write ``content`` atomically to an arbitrary, already-chosen
        ``path`` (STORY-061 extension) -- the indirect Save Picker export
        flow, where the user (and the OS dialog's own overwrite confirmation)
        already resolved the destination and any collision.

        fast-synchronous; must be called on the Qt main thread. Writes to a
        temporary file in the same folder and atomically renames it into
        place, so a failed write never leaves a partial file (EC-RES-5).

        Args:
            path: The absolute destination path chosen by the native picker.
            content: The full UTF-8 file content to write.

        Raises:
            OsAdapterError: The write failed (permission denied, disk full).
        """
        ...

    def write_export_file_bytes(self, *, filename: str, content: bytes) -> str:
        """Write raw ``content`` atomically into the exports folder
        ``<app-data>/exports/`` (STORY-064 extension; 10_Domain_and_Data/
        05_EXPORT_FORMATS.md §11) -- the binary counterpart of
        ``write_export_file``, used for the Charts tab's PNG export.

        fast-synchronous; must be called on the Qt main thread. Creates the
        exports folder on first use. Applies the identical numeric-suffix
        collision rule (§2.2) when ``filename`` already exists in the
        folder. Writes to a temporary file in the same folder and atomically
        renames it into place, so a failed write never leaves a partial file
        (EC-RES-5).

        Args:
            filename: The canonical export filename, already composed by the
                ``ExportFilenameHelper``.
            content: The full binary file content to write.

        Returns:
            The absolute path of the file actually written, after the
            collision-suffix rule is applied.

        Raises:
            OsAdapterError: The exports folder could not be created, or the
                write failed (permission denied, disk full).
        """
        ...

    def write_binary_file(self, *, path: str, content: bytes) -> None:
        """Write raw ``content`` atomically to an arbitrary, already-chosen
        ``path`` (STORY-064 extension) -- the binary counterpart of
        ``write_text_file``, used for the Charts tab's indirect Save Picker
        PNG export flow.

        fast-synchronous; must be called on the Qt main thread. Writes to a
        temporary file in the same folder and atomically renames it into
        place, so a failed write never leaves a partial file (EC-RES-5).

        Args:
            path: The absolute destination path chosen by the native picker.
            content: The full binary file content to write.

        Raises:
            OsAdapterError: The write failed (permission denied, disk full).
        """
        ...


class FileWatchSubscription(Protocol):
    """A handle to one active per-path file-change watch.

    Mirror of ``ui.task_editor.protocols.FileWatchSubscription`` -- see this
    module's docstring for why the declaration is duplicated.
    """

    def cancel(self) -> None:
        """Stop watching the path this subscription was created for.

        fast-synchronous; idempotent -- calling it more than once is a no-op.
        """
        ...


class FileChangeWatcher(Protocol):
    """Detects an open task file changing on disk while it is open in the editor
    (``09_Task_Editor/state_machine.md`` §8, EC-TE-06).

    Mirror of ``ui.task_editor.protocols.FileChangeWatcher`` -- see this module's
    docstring for why the declaration is duplicated.
    """

    def watch(self, path: str, on_changed: Callable[[str], None]) -> FileWatchSubscription:
        """Start watching ``path`` for on-disk content changes.

        fast-synchronous; callable from the GUI thread. ``on_changed`` is
        invoked with ``path`` only when the on-disk content actually differs
        from what was last read -- a touch that does not change content is
        ignored.

        Args:
            path: The absolute path of the open task file to watch.
            on_changed: Called with ``path`` when its on-disk content changes.

        Returns:
            A subscription handle for explicit early cancellation (e.g. on close).
        """
        ...
