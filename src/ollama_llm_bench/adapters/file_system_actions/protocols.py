"""``FileSystemActions`` Protocol (08-E §21c)."""

from typing import Protocol

__all__: list[str] = ["FileSystemActions"]


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
