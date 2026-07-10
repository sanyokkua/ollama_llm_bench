"""Platform Detector: host OS classification and OS-appropriate application-data paths.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-K_platform_specifics.md``.

Gives the application one authoritative, cached answer to "what OS is this, and where
does its data live", produced once at launch by ``make_platform_detector().detect()``,
so every later module reads a single immutable ``PlatformProfile`` instead of
re-detecting the host or hand-rolling its own OS branch.
"""

from ollama_llm_bench.backend.platform.api import create_app_data_dir, make_platform_detector
from ollama_llm_bench.backend.platform.models import PlatformKind, PlatformProfile
from ollama_llm_bench.backend.platform.protocols import PlatformDetector

__all__: list[str] = [
    "PlatformDetector",
    "PlatformKind",
    "PlatformProfile",
    "create_app_data_dir",
    "make_platform_detector",
]
