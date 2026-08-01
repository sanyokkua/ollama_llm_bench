"""A fake ``LLMClient`` for downstream tests — no network, no ``google-genai`` SDK.

``FakeGeminiClient`` is this module's own public fake (its
``chat``/``chat_stream`` honour the ``(request, *, token)`` signature from
STORY-021/ADR-0005), distinct from any narrower local double a consuming
module's own ``tests/conftest.py`` might define for its own purposes. Mirrors
``provider_anthropic/testing.py``, plus real ``embed``/``list_models`` canned
values — Gemini supports both (§6.9), unlike Anthropic.
"""

from collections.abc import Iterator

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import (
    ChatChunk,
    ChatRequest,
    ChatResponse,
    InferenceTestResult,
    ModelName,
    ProviderHealth,
)

__all__: list[str] = ["FakeChatStream", "FakeGeminiClient"]


class FakeChatStream:
    """A controllable ``ChatStream`` double: replays a canned chunk sequence."""

    def __init__(self, *, chunks: tuple[ChatChunk, ...], response: ChatResponse) -> None:
        """Construct a fake stream that replays ``chunks`` then ``response``.

        Args:
            chunks: The content chunks to yield, in order.
            response: The trailing response returned once exhausted.
        """
        self._iterator: Iterator[ChatChunk] = iter(chunks)
        self._response = response

    def __iter__(self) -> Iterator[ChatChunk]:
        """Return the chunk iterator itself."""
        return self

    def __next__(self) -> ChatChunk:
        """Return the next canned chunk, raising ``StopIteration`` once exhausted."""
        return next(self._iterator)

    def trailing_response(self) -> ChatResponse:
        """Return the canned trailing response."""
        return self._response


class FakeGeminiClient:
    """An in-memory ``LLMClient`` double with settable canned responses.

    Every method returns a caller-configured canned value; no network call
    and no ``google-genai`` SDK import occurs anywhere in this class.
    Satisfies ``LLMClient`` structurally — no inheritance is declared.
    """

    def __init__(self) -> None:
        self._chat_response: ChatResponse | None = None
        self._chat_chunks: tuple[ChatChunk, ...] = ()
        self._probe_health: ProviderHealth | None = None
        self._models: tuple[ModelName, ...] = ()
        self._test_inference_result: InferenceTestResult | None = None
        self._embed_vector: tuple[float, ...] = ()
        self.close_calls: int = 0

    def set_chat_response(
        self, response: ChatResponse, *, chunks: tuple[ChatChunk, ...] = ()
    ) -> None:
        """Configure the response ``chat``/``chat_stream`` return next."""
        self._chat_response = response
        self._chat_chunks = chunks

    def set_probe_health(self, health: ProviderHealth) -> None:
        """Configure the value ``probe_health`` returns next."""
        self._probe_health = health

    def set_models(self, models: tuple[ModelName, ...]) -> None:
        """Configure the value ``list_models`` returns next."""
        self._models = models

    def set_test_inference_result(self, result: InferenceTestResult) -> None:
        """Configure the value ``test_inference`` returns next."""
        self._test_inference_result = result

    def set_embed_vector(self, vector: tuple[float, ...]) -> None:
        """Configure the value ``embed`` returns next."""
        self._embed_vector = vector

    def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse:
        """Return the canned chat response configured via ``set_chat_response``."""
        del request, token
        assert self._chat_response is not None, "call set_chat_response() before chat()"  # noqa: S101
        return self._chat_response

    def chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> FakeChatStream:
        """Return a ``FakeChatStream`` replaying the configured canned chunks."""
        del request, token
        assert self._chat_response is not None, "call set_chat_response() before chat_stream()"  # noqa: S101
        return FakeChatStream(chunks=self._chat_chunks, response=self._chat_response)

    def embed(self, text: str) -> tuple[float, ...]:
        """Return the canned embedding vector configured via ``set_embed_vector``."""
        del text
        return self._embed_vector

    def list_models(self) -> tuple[ModelName, ...]:
        """Return the canned model catalog configured via ``set_models``."""
        return self._models

    def probe_health(self) -> ProviderHealth:
        """Return the canned health configured via ``set_probe_health``."""
        assert self._probe_health is not None, "call set_probe_health() before probe_health()"  # noqa: S101
        return self._probe_health

    def test_inference(self, model_name: ModelName) -> InferenceTestResult:
        """Return the canned result configured via ``set_test_inference_result``."""
        del model_name
        assert self._test_inference_result is not None, (  # noqa: S101
            "call set_test_inference_result() before test_inference()"
        )
        return self._test_inference_result

    def supports_streaming(self) -> bool:
        """Always ``True`` — mirrors the real client's capability."""
        return True

    def supports_reasoning_effort(self) -> bool:
        """Always ``False`` — mirrors the real client's conservative default."""
        return False

    def supports_thinking(self) -> bool:
        """Always ``False`` — mirrors the real client's conservative default."""
        return False

    def supports_embedding(self) -> bool:
        """Always ``True`` — mirrors the real client's unconditional answer (§6.9)."""
        return True

    def supports_discovery(self) -> bool:
        """Always ``True`` — mirrors the real client's pinned-SDK-build answer (§6.9.1)."""
        return True

    def close(self) -> None:
        """Record a close call; never raises."""
        self.close_calls += 1
