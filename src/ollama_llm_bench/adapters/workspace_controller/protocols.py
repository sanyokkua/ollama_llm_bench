"""``WorkspaceController`` — the cross-module contract for workspace switching.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§19. Per ``protocol-first-interfaces``, this module owns the Protocol because it is the
declared public entry point a future ``ui/main_window`` story imports
(``01_MODULE_INVENTORY.md`` §5).
"""

from typing import Protocol

from ollama_llm_bench.adapters.workspace_controller.models import WorkspaceHint

__all__: list[str] = ["WorkspaceController"]


class WorkspaceController(Protocol):
    """Controls which of the two main-window workspaces is active."""

    def active(self) -> str:
        """Return the active workspace name: ``"benchmark"`` or ``"task_editor"``.

        Synchronous; never raises.
        """
        ...

    def switch_to(self, name: str, hint: WorkspaceHint | None = None) -> None:
        """Switch to the named workspace, applying the optional hint.

        Synchronous; never raises for a valid name.

        Args:
            name: The destination workspace — ``"benchmark"`` or
                ``"task_editor"``.
            hint: Optional guidance (pre-open paths / focus widget) applied
                after the switch completes.
        """
        ...
