"""``TaskEditorGateway`` and ``FileChangeWatcher`` -- ``ui/task_editor/``'s locally
declared Protocols (D-R-06).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.7 for ``TaskEditorGateway``, declared here with the exact method signatures.
``FileChangeWatcher`` has no existing Protocol anywhere else in the codebase (verified
by repository grep before writing this file) -- it is declared here, scoped to exactly
what this workspace's controller needs to flip an open file to the reload-pending badge
state (``09_Task_Editor/state_machine.md`` §8): register a per-path watch and be told
when that path's on-disk content changes. The real adapter-layer implementation is
deferred to Phase 11; this story's own tests use ``testing.FakeFileChangeWatcher``.
"""

from collections.abc import Callable
from typing import Protocol

from ollama_llm_bench.backend.domain import SettingKey

__all__: list[str] = ["FileChangeWatcher", "FileWatchSubscription", "TaskEditorGateway"]


class TaskEditorGateway(Protocol):
    """Adapter gateway for the Task Editor workspace (D-R-06).

    Wraps ``SettingsStore`` (workspace settings keys), ``WorkspaceStore`` (current
    workspace state), and ``RunRegistryStore`` (active run's task paths for the
    in-use marker) -- the controller never holds any of those three directly.
    """

    def get_setting(self, key: SettingKey) -> str | None:
        """Read a workspace settings key.

        fast-synchronous; callable from the GUI thread. Keys: ``task_editor.
        auto_format_on_save``, ``task_editor.warn_on_empty_grading_criteria``,
        ``task_editor.validation_debounce_ms``, ``ui.task_editor_last_folder``.

        Args:
            key: The settings key to read.

        Returns:
            The persisted value, or ``None`` when unset.
        """
        ...

    def set_setting(self, key: SettingKey, value: str) -> None:
        """Persist a workspace settings key (e.g. ``ui.task_editor_last_folder``).

        fast-synchronous; callable from the GUI thread.

        Args:
            key: The settings key to write.
            value: The new value.
        """
        ...

    def active_workspace(self) -> str:
        """Read the current active workspace (``"benchmark"``/``"task_editor"``).

        fast-synchronous; callable from the GUI thread.

        Returns:
            The active workspace identifier.
        """
        ...

    def active_run_task_paths(self) -> tuple[str, ...]:
        """Read the active run's task file paths for the in-use marker (AC-4).

        fast-synchronous; callable from the GUI thread.

        Returns:
            The absolute paths of every task file backing the currently
            executing run, or ``()`` when no run is active.
        """
        ...


class FileWatchSubscription(Protocol):
    """A handle to one active per-path file-change watch."""

    def cancel(self) -> None:
        """Stop watching the path this subscription was created for.

        fast-synchronous; idempotent -- calling it more than once is a no-op.
        """
        ...


class FileChangeWatcher(Protocol):
    """Detects an open task file changing on disk while it is open in the editor
    (``09_Task_Editor/state_machine.md`` §8, EC-TE-06)."""

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
