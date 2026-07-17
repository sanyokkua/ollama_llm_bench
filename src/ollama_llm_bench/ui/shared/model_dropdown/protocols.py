"""Local Protocol scoping this widget's off-GUI-thread model-fetch dependency (08-E §10).

Declared locally, not importing ``backend.provider_registry``/``LLMClient`` directly:
``ui/*`` may import ``backend.domain``/``backend.errors``/``backend.events``/
``backend.stores``/``backend.settings`` only (``project-structure.md``) — never
``backend.provider_registry`` or ``backend.concurrency`` — and a UI module must never hold a
backend service Protocol directly (D-R-06). ``LLMClient.list_models()`` is a blocking network
call (08-E §10); this widget holds no ``TaskRunner`` itself and delegates all off-GUI-thread
scheduling and thread marshalling to the consumer's adapter implementation of this Protocol —
matching the Gateway pattern's own stated purpose (protocol-first-interfaces skill: "the single
place the Qt-specific concerns live: thread marshalling").
"""

from collections.abc import Callable
from typing import Protocol

from ollama_llm_bench.backend.domain import ModelName, ProviderId

__all__: list[str] = ["ModelFetcher"]


class ModelFetcher(Protocol):
    """Fetches a provider's model list off the GUI thread, delivering the result via callback."""

    def fetch_models(
        self,
        provider_id: ProviderId,
        *,
        on_success: Callable[[ProviderId, tuple[ModelName, ...]], None],
        on_error: Callable[[ProviderId, Exception], None],
    ) -> None:
        """Fetch `provider_id`'s models off the GUI thread.

        Returns immediately. Exactly one of `on_success`/`on_error` is called back, on the
        GUI thread, once the fetch settles.
        """
        ...
