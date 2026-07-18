"""An in-memory ``WorkspaceController`` test double."""

from ollama_llm_bench.adapters.workspace_controller.models import WorkspaceHint

__all__: list[str] = ["FakeWorkspaceController"]


class FakeWorkspaceController:
    """A ``WorkspaceController`` fake recording every ``switch_to`` call."""

    def __init__(self) -> None:
        self._active = "benchmark"
        self.recorded_switches: list[tuple[str, WorkspaceHint | None]] = []

    def active(self) -> str:
        return self._active

    def switch_to(self, name: str, hint: WorkspaceHint | None = None) -> None:
        self._active = name
        self.recorded_switches.append((name, hint))
