"""The concrete ``TaskEditorGateway`` implementation (STORY-111).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.7 (``TaskEditorGateway``), §7b (UI adapter gateways, D-R-06), §4 (the threading
contract); ``docs/v3_specification/09_Task_Editor/implementation_structure.md`` §7
(dependency Protocols).
"""

from ollama_llm_bench.adapters.ui_gateways.protocols import ActiveRunTaskPaths
from ollama_llm_bench.backend.domain import SettingKey
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.settings import SettingsService
from ollama_llm_bench.backend.stores import RunRegistryStore, WorkspaceStore

__all__: list[str] = [
    "TaskEditorGatewayCollaborators",
    "_TaskEditorGateway",
]


class TaskEditorGatewayCollaborators:
    """Groups the concrete gateway's constructor dependencies (<=4-parameter rule).

    A plain, private-implementation-detail bundle -- not a cross-boundary DTO, so it
    is an ordinary class rather than a ``msgspec.Struct``; it never leaves this
    ``_internal`` package.
    """

    def __init__(
        self,
        *,
        app_settings: AppSettingsStore,
        settings: SettingsService,
        workspace_store: WorkspaceStore,
        run_registry: RunRegistryStore,
        active_run_task_paths: ActiveRunTaskPaths,
    ) -> None:
        self.app_settings = app_settings
        self.settings = settings
        self.workspace_store = workspace_store
        self.run_registry = run_registry
        self.active_run_task_paths = active_run_task_paths


class _TaskEditorGateway:
    """Adapter gateway for the Task Editor workspace, satisfying
    ``ui.task_editor.protocols.TaskEditorGateway`` structurally (D-R-06).

    Wraps ``AppSettingsStore``/``SettingsService`` (the workspace settings keys:
    ``task_editor.auto_format_on_save``, ``task_editor.warn_on_empty_grading_criteria``,
    ``task_editor.validation_debounce_ms``, ``ui.task_editor_last_folder``),
    ``WorkspaceStore`` (which workspace is currently showing), and
    ``RunRegistryStore``/``ActiveRunTaskPaths`` (the active run's task-file paths that
    drive the in-use marker). Construction is side-effect free -- it performs no
    backend read and no network call.
    """

    def __init__(self, *, collaborators: TaskEditorGatewayCollaborators) -> None:
        self._c = collaborators

    # -- workspace settings -------------------------------------------------------
    #
    # The read/write split mirrors every sibling gateway (`_internal/main_window/
    # gateway.py`). `SettingsService.get_str` floors to a default and can never
    # return `None` for "unset", but this method must return `None` when unset, so
    # the read goes through `AppSettingsStore.get_setting`. Writes still go through
    # `SettingsService.set` so the settings-changed event fires.

    def get_setting(self, key: SettingKey) -> str | None:
        """Read a workspace settings key, or ``None`` if unset."""
        return self._c.app_settings.get_setting(key)

    def set_setting(self, key: SettingKey, value: str) -> None:
        """Persist a workspace settings key through the settings service."""
        self._c.settings.set(key, value)

    # -- workspace state ------------------------------------------------------------

    def active_workspace(self) -> str:
        """Return the currently active workspace (``"benchmark"``/``"task_editor"``)."""
        return self._c.workspace_store.active_workspace()

    # -- the in-use marker ------------------------------------------------------------

    def active_run_task_paths(self) -> tuple[str, ...]:
        """Return the active run's task-file paths, or ``()`` when no run is active.

        Short-circuits on an idle run registry without ever calling
        ``ActiveRunTaskPaths.task_paths_for`` (STORY-111-AC-2).
        """
        run_id = self._c.run_registry.active_run_id()
        if run_id is None:
            return ()
        return self._c.active_run_task_paths.task_paths_for(run_id)
