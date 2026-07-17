"""Local Protocol scoping this widget's registry-read dependency (D-R-06; 08-E §9).

Declared locally rather than importing ``backend.provider_registry.ProviderRegistry``
directly: ``ui/*`` may import ``backend.domain``/``backend.errors``/``backend.events``/
``backend.stores``/``backend.settings`` only (``project-structure.md``), never a backend
service module such as ``backend.provider_registry`` — and a UI module must never hold a
backend service Protocol directly (D-R-06). Any object satisfying the real
``ProviderRegistry`` Protocol already satisfies this narrower, locally-scoped one
structurally, with no adapter shim required.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import ProviderConfig

__all__: list[str] = ["ProviderListSource"]


class ProviderListSource(Protocol):
    """The one method this widget needs to read the enabled-provider catalog."""

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        """Return the enabled providers in display order.

        fast-synchronous; never raises.
        """
        ...
