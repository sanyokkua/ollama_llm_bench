"""Concrete implementations of the ``08-E`` §7b UI adapter gateways (ADR-0014).

Houses one sub-feature package per widget under ``_internal/``, exposing one
``make_*_gateway`` factory per widget so no UI module ever holds a backend Store or
Service Protocol directly (D-R-06). Only the Main Window gateway is implemented so
far (STORY-105); the remaining six gateways land in later stories.
"""

from ollama_llm_bench.adapters.ui_gateways.api import MainWindowGateway, make_main_window_gateway

__all__: list[str] = ["MainWindowGateway", "make_main_window_gateway"]
