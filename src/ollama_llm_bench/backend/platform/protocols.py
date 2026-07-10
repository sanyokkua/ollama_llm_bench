"""The ``PlatformDetector`` service contract owned by this module.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-K_platform_specifics.md``
§2 (the platform detector and the platform profile). This module declares the pure
interface only — no concrete OS-probing logic; see ``_internal/`` for the
implementation.
"""

from typing import Protocol

from ollama_llm_bench.backend.platform.models import PlatformProfile

__all__: list[str] = [
    "PlatformDetector",
]


class PlatformDetector(Protocol):
    """Detects the host operating system and resolves its platform profile.

    Runs once at launch; the composition root caches the returned profile for the
    process lifetime. Synchronous; never raises — an unclassifiable host resolves
    to ``PlatformKind.UNKNOWN`` with Linux-convention fallbacks rather than raising.
    """

    def detect(self) -> PlatformProfile:
        """Classify the host and resolve its OS-appropriate platform profile.

        fast-synchronous; callable from any thread. Never raises.

        Returns:
            The immutable, fully-resolved ``PlatformProfile`` for this host.
        """
        ...
