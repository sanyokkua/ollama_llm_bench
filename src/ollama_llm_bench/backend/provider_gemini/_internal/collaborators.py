"""Construction-time collaborator bundle for ``GeminiClient``.

A plain class, not a ``msgspec.Struct``: its fields are ``Protocol`` types
(``Clock``, ``EventBus``, ``InferenceActivityStore``) that are not
``@runtime_checkable``, so they cannot round-trip through
``msgspec.convert``'s runtime instance checks the way a genuine cross-boundary
DTO can. This bundle only ever exists in memory, constructed once by
``compose.py`` (or a test) and passed straight to ``make_gemini_client``; it
is never serialized. Mirrors ``provider_anthropic/_internal/collaborators.py``.
"""

import httpx

from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.infra import Clock
from ollama_llm_bench.backend.stores.inference_activity import InferenceActivityStore

__all__: list[str] = ["GeminiClientCollaborators"]


class GeminiClientCollaborators:
    """The services one ``GEMINI`` client instance depends on.

    ``event_bus`` is retained for the shared progress-emitter helper a later
    story wires in; this story's surface does not publish on it.
    """

    def __init__(
        self,
        *,
        clock: Clock,
        event_bus: EventBus,
        inference_activity_store: InferenceActivityStore,
        http_client: httpx.Client,
    ) -> None:
        """Construct the collaborator bundle.

        Args:
            clock: The injected time source for every duration measurement.
            event_bus: Unused by this story's surface; retained for the
                shared progress-emitter helper a later story wires in.
            inference_activity_store: The application-wide single-inference
                gate, acquired for the duration of ``test_inference``.
            http_client: The one synchronous HTTP client ``compose.py``
                constructs at composition time (STORY-077, Gap 1), reused for
                the reachability probe instead of a per-call client.
        """
        self.clock = clock
        self.event_bus = event_bus
        self.inference_activity_store = inference_activity_store
        self.http_client = http_client
