"""``MainWindowViewModel`` -- the frozen shell view-model (STORY-053).

Source of truth: ``docs/v3_specification/01_Main_Window/implementation_structure.md`` §4.
Recomputed by ``MainWindowController`` on every subscribed event and applied to the shell
widget; never persisted, never crosses a service boundary.
"""

import msgspec

from ollama_llm_bench.backend.domain import ReadinessState

__all__: list[str] = ["MainWindowViewModel"]


class MainWindowViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Main Window shell's full displayed state, in one frozen snapshot.

    Attributes:
        window_title: The resolved title for the current run state.
        active_workspace: ``"benchmark"`` or ``"task_editor"``.
        settings_action_enabled: ``False`` while a run is non-terminal.
        running_pill_visible: ``True`` only while a run is non-terminal.
        running_pill_label: The effective run name; ``""`` when the pill is hidden.
        health_state: Drives the status-bar dot colour and label.
        health_tooltip: The pre-formatted per-provider readiness detail.
        health_dot_clickable: ``False`` while a run is non-terminal.
        toast_text: The current status-bar toast; ``""`` when none.
    """

    window_title: str
    active_workspace: str
    settings_action_enabled: bool
    running_pill_visible: bool
    running_pill_label: str
    health_state: ReadinessState
    health_tooltip: str
    health_dot_clickable: bool
    toast_text: str
