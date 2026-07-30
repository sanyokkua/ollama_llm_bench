"""Concrete implementations of the ``08-E`` §7b UI adapter gateways (ADR-0014).

Houses one sub-feature package per widget under ``_internal/``, exposing one
``make_*_gateway`` factory per widget so no UI module ever holds a backend Store or
Service Protocol directly (D-R-06). Three of the seven gateways are implemented so far --
Main Window (STORY-105), New Benchmark (STORY-106), and Progress (STORY-107); the
remaining four land in later stories.
"""

from ollama_llm_bench.adapters.ui_gateways.api import (
    MainWindowGateway,
    ManualProviderProbeCommand,
    NewBenchmarkGateway,
    ProgressGateway,
    RunLogWriteStatus,
    make_main_window_gateway,
    make_new_benchmark_gateway,
    make_progress_gateway,
)

__all__: list[str] = [
    "MainWindowGateway",
    "ManualProviderProbeCommand",
    "NewBenchmarkGateway",
    "ProgressGateway",
    "RunLogWriteStatus",
    "make_main_window_gateway",
    "make_new_benchmark_gateway",
    "make_progress_gateway",
]
