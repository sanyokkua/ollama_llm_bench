"""The ``Clock`` and ``PlatformDetector`` service contracts owned by this module.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§5 (Clock). This module declares pure interfaces only — no concrete implementation, no
threading/timing logic, and no OS probing.

``PlatformDetector`` is declared here as a narrow, structurally-typed Protocol carrying
only the single member (`app_data_root`) this module's path-resolution surface needs.
The real ``PlatformDetector`` Protocol and its OS-classification implementation are owned
by STORY-005 (``backend/platform/``); that future Protocol satisfies this one
structurally with zero coupling, because ``typing.Protocol`` matching is structural, not
nominal.
"""

from pathlib import Path
from typing import Protocol

from ollama_llm_bench.backend.domain.models import Iso8601Utc

__all__: list[str] = [
    "Clock",
    "PlatformDetector",
]


class Clock(Protocol):
    """Injectable time source. Synchronous; never blocks; never raises."""

    def now_utc(self) -> Iso8601Utc:
        """Return the current instant as an ISO-8601 UTC string.

        fast-synchronous; callable from any thread. Never raises.
        """
        ...

    def monotonic_ms(self) -> int:
        """Return a monotonic millisecond counter for measuring durations.

        The value has no calendar meaning; only differences between two calls
        are meaningful. fast-synchronous; callable from any thread. Never
        raises.
        """
        ...


class PlatformDetector(Protocol):
    """The narrow slice of the platform detector this module depends on.

    STORY-005 owns the real ``PlatformDetector`` Protocol (OS classification,
    permission handling, and the full application-data-directory lifecycle).
    This module needs only the resolved root directory, so it declares that
    single member here rather than importing STORY-005's Protocol — keeping
    this module's ``modules: [backend/infra/]`` front-matter accurate and this
    module independently testable against a fake today.
    """

    @property
    def app_data_root(self) -> Path:
        """The per-user application-data root directory, resolved per OS.

        fast-synchronous; callable from any thread. Never raises.
        """
        ...
