"""Configurable fakes for ``TaskEditorGateway``/``FileChangeWatcher``, for downstream
module tests (STORY-068)."""

from collections.abc import Callable

from ollama_llm_bench.backend.domain import SettingKey
from ollama_llm_bench.ui.task_editor.protocols import FileWatchSubscription

__all__: list[str] = ["FakeFileChangeWatcher", "FakeTaskEditorGateway"]


class _FakeWatchSubscription:
    def __init__(self, cancel_fn: Callable[[], None]) -> None:
        self._cancel_fn = cancel_fn
        self._cancelled = False

    def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        self._cancel_fn()


class FakeTaskEditorGateway:
    """An in-memory fake with externally settable settings, workspace, and
    in-use-run-paths state. No real persistence behind it."""

    def __init__(
        self,
        *,
        active_workspace: str = "task_editor",
        active_run_task_paths: tuple[str, ...] = (),
    ) -> None:
        self._settings: dict[str, str] = {}
        self._active_workspace = active_workspace
        self._active_run_task_paths = active_run_task_paths
        self.recorded_set_setting_calls: list[tuple[str, str]] = []

    def get_setting(self, key: SettingKey) -> str | None:
        return self._settings.get(key)

    def set_setting(self, key: SettingKey, value: str) -> None:
        self._settings[key] = value
        self.recorded_set_setting_calls.append((key, value))

    def active_workspace(self) -> str:
        return self._active_workspace

    def active_run_task_paths(self) -> tuple[str, ...]:
        return self._active_run_task_paths

    def set_active_workspace(self, workspace: str) -> None:
        """Test helper: force the next ``active_workspace()`` return value."""
        self._active_workspace = workspace

    def set_active_run_task_paths(self, paths: tuple[str, ...]) -> None:
        """Test helper: force the next ``active_run_task_paths()`` return value."""
        self._active_run_task_paths = paths


class FakeFileChangeWatcher:
    """An in-memory fake letting a test simulate an on-disk change for a watched path.

    No real filesystem watching behind it -- call ``trigger_change`` to invoke
    every ``on_changed`` callback registered for a path.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[str], None]]] = {}
        self.watched_paths: list[str] = []

    def watch(self, path: str, on_changed: Callable[[str], None]) -> FileWatchSubscription:
        self.watched_paths.append(path)
        self._handlers.setdefault(path, []).append(on_changed)

        def _cancel() -> None:
            self._handlers[path].remove(on_changed)

        return _FakeWatchSubscription(_cancel)

    def trigger_change(self, path: str) -> None:
        """Test helper: simulate an on-disk content change for ``path``."""
        for handler in list(self._handlers.get(path, [])):
            handler(path)

    def live_watch_count(self, path: str) -> int:
        """Test helper: how many uncancelled watches are registered for ``path``.

        Distinguishes a watch that was cancelled and re-registered (still one)
        from one that was re-registered while the stale watch leaked (two) --
        ``watched_paths`` alone cannot tell those apart because it only ever
        grows.
        """
        return len(self._handlers.get(path, []))
