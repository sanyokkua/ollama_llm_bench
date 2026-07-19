"""``RunRow`` and the collaborator bundle for ``ui/resume_benchmark/`` (STORY-056).

Source of truth: ``docs/v3_specification/03_Resume_Benchmark_Widget/description.md``
§3.3 (run table), §4.3 (status badge). ``RunRow`` carries every gating boolean the
view and context menu need pre-derived -- neither ever re-derives gating from a
raw ``BenchmarkRun``/``BenchmarkResult``.
"""

import msgspec

from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.adapters.native_pickers import NativePickers
from ollama_llm_bench.backend.domain import RunId
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.ui.resume_benchmark.protocols import ResumeGateway
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager

__all__: list[str] = ["ResumeBenchmarkCollaborators", "RunRow"]


class RunRow(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One row of the Resume run table -- pre-derived; never re-derived by
    view/menu (STORY-056)."""

    run_id: RunId
    effective_name: str
    mode_label: str
    started_at_display: str
    started_at_sort_key: str
    status_badge_label: str
    status_badge_status: str
    tasks_completed: int
    tasks_total: int
    is_resumable: bool
    is_executing: bool
    has_analysis: bool
    log_file_exists: bool


class ResumeBenchmarkCollaborators(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Dependency bundle for ``make_resume_benchmark_widget`` (coding-style.md's
    4-parameter hard maximum)."""

    gateway: ResumeGateway
    event_bus: EventBus
    native_pickers: NativePickers
    file_system_actions: FileSystemActions
    theme_manager: ThemeManager | None = None
    platform_kind: PlatformKind = PlatformKind.UNKNOWN
