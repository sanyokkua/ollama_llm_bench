"""Concrete implementations of the ``08-E`` §7b UI adapter gateways (ADR-0014).

Houses one sub-feature package per widget under ``_internal/``, exposing one
``make_*_gateway`` factory per widget so no UI module ever holds a backend Store or
Service Protocol directly (D-R-06). Two of the seven gateways are implemented so far --
Main Window (STORY-105) and New Benchmark (STORY-106); the remaining five land in later
stories.
"""

from ollama_llm_bench.adapters.ui_gateways.api import (
    MainWindowGateway,
    NewBenchmarkGateway,
    make_main_window_gateway,
    make_new_benchmark_gateway,
)

__all__: list[str] = [
    "MainWindowGateway",
    "NewBenchmarkGateway",
    "make_main_window_gateway",
    "make_new_benchmark_gateway",
]
