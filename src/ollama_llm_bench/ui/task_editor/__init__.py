"""Task Editor workspace (STORY-068): the editor toolbar, the Files pane, the Tasks
pane, the in-memory buffer model, and the ``TaskEditorViewModel`` the controller
computes. The Field-editor pane, the YAML preview, and Save/validation-cascade
wiring are STORY-069's scope.
"""

from ollama_llm_bench.ui.task_editor.api import make_task_editor_workspace
from ollama_llm_bench.ui.task_editor.models import (
    FieldControlKind,
    FieldRowViewModel,
    FileRowViewModel,
    TaskEditorCollaborators,
    TaskEditorViewModel,
    TaskEditorWorkspace,
    TaskRowViewModel,
    ToolbarViewModel,
    ValidationState,
)
from ollama_llm_bench.ui.task_editor.protocols import (
    FileChangeWatcher,
    FileWatchSubscription,
    TaskEditorGateway,
)

__all__: list[str] = [
    "FieldControlKind",
    "FieldRowViewModel",
    "FileChangeWatcher",
    "FileRowViewModel",
    "FileWatchSubscription",
    "TaskEditorCollaborators",
    "TaskEditorGateway",
    "TaskEditorViewModel",
    "TaskEditorWorkspace",
    "TaskRowViewModel",
    "ToolbarViewModel",
    "ValidationState",
    "make_task_editor_workspace",
]
