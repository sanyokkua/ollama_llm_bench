"""Concrete implementations of the ``08-E`` §7b UI adapter gateways (ADR-0014).

Houses one sub-feature package per widget under ``_internal/``, exposing one
``make_*_gateway`` factory per widget so no UI module ever holds a backend Store or
Service Protocol directly (D-R-06). Five of the seven gateways are implemented so far --
Main Window (STORY-105), New Benchmark (STORY-106), Progress (STORY-107), Result
(STORY-108), and Resume (STORY-109); the remaining two land in later stories.
"""

from ollama_llm_bench.adapters.ui_gateways.api import (
    JudgeAnalysisGenerationOutcome,
    JudgeAnalysisGenerationResult,
    MainWindowGateway,
    ManualProviderProbeCommand,
    NewBenchmarkGateway,
    ProgressGateway,
    ResultGateway,
    ResumeGateway,
    RunLogWriteStatus,
    make_main_window_gateway,
    make_new_benchmark_gateway,
    make_progress_gateway,
    make_result_gateway,
    make_resume_gateway,
)

__all__: list[str] = [
    "JudgeAnalysisGenerationOutcome",
    "JudgeAnalysisGenerationResult",
    "MainWindowGateway",
    "ManualProviderProbeCommand",
    "NewBenchmarkGateway",
    "ProgressGateway",
    "ResultGateway",
    "ResumeGateway",
    "RunLogWriteStatus",
    "make_main_window_gateway",
    "make_new_benchmark_gateway",
    "make_progress_gateway",
    "make_result_gateway",
    "make_resume_gateway",
]
