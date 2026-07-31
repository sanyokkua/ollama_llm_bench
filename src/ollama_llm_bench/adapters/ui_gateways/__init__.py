"""Concrete implementations of the ``08-E`` §7b UI adapter gateways (ADR-0014).

Houses one sub-feature package per widget under ``_internal/``, exposing one
``make_*_gateway`` factory per widget so no UI module ever holds a backend Store or
Service Protocol directly (D-R-06). Six of the seven gateways are implemented so far --
Main Window (STORY-105), New Benchmark (STORY-106), Progress (STORY-107), Result
(STORY-108), Resume (STORY-109), and Task Editor (STORY-111); the remaining one lands in
a later story.
"""

from ollama_llm_bench.adapters.ui_gateways.api import (
    ActiveRunTaskPaths,
    JudgeAnalysisGenerationOutcome,
    JudgeAnalysisGenerationResult,
    MainWindowGateway,
    ManualProviderProbeCommand,
    NewBenchmarkGateway,
    ProgressGateway,
    ResultGateway,
    ResumeGateway,
    RunLogWriteStatus,
    SettingsGateway,
    TaskEditorGateway,
    make_main_window_gateway,
    make_new_benchmark_gateway,
    make_progress_gateway,
    make_result_gateway,
    make_resume_gateway,
    make_settings_gateway,
    make_task_editor_gateway,
)

__all__: list[str] = [
    "ActiveRunTaskPaths",
    "JudgeAnalysisGenerationOutcome",
    "JudgeAnalysisGenerationResult",
    "MainWindowGateway",
    "ManualProviderProbeCommand",
    "NewBenchmarkGateway",
    "ProgressGateway",
    "ResultGateway",
    "ResumeGateway",
    "RunLogWriteStatus",
    "SettingsGateway",
    "TaskEditorGateway",
    "make_main_window_gateway",
    "make_new_benchmark_gateway",
    "make_progress_gateway",
    "make_result_gateway",
    "make_resume_gateway",
    "make_settings_gateway",
    "make_task_editor_gateway",
]
